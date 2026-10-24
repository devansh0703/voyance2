#!/usr/bin/env bash
# Voyance II — one-command startup.
# Boots: Python venv → artifacts check → (optional) web build → FastAPI on :8010
# serving the API, dashboards, live feeds, and the AI analyst.
#
# Usage:
#   ./start.sh              # start everything (builds web bundle if missing)
#   ./start.sh --fresh      # also retrain models + recompute analytics (GPU)
#   ./start.sh --port 8000  # custom port
set -euo pipefail
cd "$(dirname "$0")"

PORT=8010
FRESH=0
for arg in "$@"; do
  case "$arg" in
    --fresh) FRESH=1 ;;
    --port)  : ;; # consumed below
    [0-9]*)  PORT="$arg" ;;
  esac
done

# bashrc is NOT parsed by uvicorn; the AI provider chain reads keys from it directly,
# but exporting here lets any subprocess see them too.
for VAR in OPENCODE_API_KEY GROQ_API_KEY OPENROUTER_API_KEY; do
  if [ -z "${!VAR:-}" ] && grep -qE "^export ${VAR}=" ~/.bashrc 2>/dev/null; then
    export "$VAR=$(grep -E "^export ${VAR}=" ~/.bashrc | tail -1 | sed "s/^export ${VAR}=//; s/^\"\(.*\)\"$/\1/")"
  fi
done

echo "── Voyance II ────────────────────────────────────────────"

# 1 · Python environment
if [ ! -x .venv/bin/python ]; then
  echo "› creating .venv (uv)…"
  uv venv .venv --python 3.12
  uv pip install --python .venv/bin/python -r requirements.txt pytest
fi
PY=.venv/bin/python

# 2 · Core artifacts: models + dashboard data. Missing → pipeline can build them.
NEED_TRAIN=0; NEED_DATA=0; NEED_WEBDATA=0
[ -f models/eta-p50.json ]              || NEED_TRAIN=1
[ -f models/anomaly_ensemble.pkl ]      || NEED_TRAIN=1
[ -f data/interim/features-2024-07.parquet ] || NEED_DATA=1
[ -f web/public/data/stats.json ]       || NEED_WEBDATA=1
[ "$FRESH" = 1 ] && { NEED_TRAIN=1; NEED_WEBDATA=1; }

if [ "$NEED_DATA" = 1 ]; then
  echo "› raw AIS + voyages missing — running the data pipeline (downloads NOAA days; resumable)…"
  "$PY" pipeline/fetch_data.sh 2>/dev/null || bash pipeline/fetch_data.sh
  for M in 2024-01 2024-04 2024-07; do
    [ -f "data/interim/features-$M.parquet" ] || \
      { "$PY" pipeline/build_voyages.py --month "$M" --days 08-14; "$PY" pipeline/weather.py "$M"; }
  done
fi

if [ "$NEED_TRAIN" = 1 ]; then
  echo "› training (GPU when CUDA is present)…"
  CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0} "$PY" pipeline/train.py
  "$PY" pipeline/train_v2.py
  "$PY" pipeline/drift.py
fi

[ -f models/maritime_graph.pkl ] || "$PY" pipeline/precompute_v2.py
[ "$NEED_WEBDATA" = 1 ] && { echo "› exporting dashboard bundles…"; "$PY" pipeline/export_web_data.py; }

# 3 · Web bundle (served statically by the API)
if [ ! -f web/dist/index.html ] || [ web/src -nt web/dist/index.html ]; then
  if command -v bun >/dev/null; then
    echo "› building web bundle (bun)…"
    (cd web && bun install --silent && bun run build)
  else
    echo "› bun not found — using existing web/dist (fetch a fresh build with: cd web && bun run build)"
  fi
fi

# 4 · Serve
echo "──────────────────────────────────────────────────────────"
echo "  API + dashboards : http://127.0.0.1:${PORT}"
echo "  Live terminal    : http://127.0.0.1:${PORT}/live"
echo "  Prediction       : http://127.0.0.1:${PORT}/predict"
echo "  Analytics        : http://127.0.0.1:${PORT}/analytics"
echo "  AI providers     : http://127.0.0.1:${PORT}/v2/ai/providers"
echo "──────────────────────────────────────────────────────────"
exec "$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT"
