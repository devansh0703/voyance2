---
name: voyance-maritime
description: Build, retrain, extend, or debug the Voyance open-source maritime voyage-intelligence platform (AIS + ERA5 quantile ETA, drift monitoring, dashboards). Use when working in /home/devansh/voyance or on maritime AIS/ETA data tasks.
version: 1.0.0
---

# Voyance Maritime

Operational knowledge for the Voyance platform (https://github.com/devansh0703/voyance).
Read this before touching the pipeline; every quirk below cost real debugging time.

## What the product is

AIS-grounded ETA with weather-conditioned uncertainty: XGBoost CUDA quantile models
(P10/P50/P90) trained on NOAA MarineCadastre AIS joined to Open-Meteo ERA5, served by
FastAPI, dashboards in MapLibre/globe.gl/ECharts. Serving scope: cargo + tanker +
passenger vessels (tug/fishing loitering is not an ETA problem).

## Pipeline commands (run from the repo root)

```bash
make data      # fetch 21 daily AIS parquets (Jan/Apr/Jul 08–14) + voyages + weather
make train     # XGBoost CUDA quantiles + LightGBM CPU benchmark + CQR calibration
make drift     # Evidently monthly-slice reports + machine-readable alerts
make web-data  # export JSON bundles for the dashboards (web/public/data)
make web       # bun build → web/dist (served statically by the API)
make api       # uvicorn backend.main:app on :8000
```

## Data facts

- **Daily point parquets only for modeling**: `data/raw/ais-YYYY-MM-DD.parquet` has real
  per-point timestamps + SOG. The monthly *tracks* (`ais-track-*.parquet`) are
  MultiLineStrings WITHOUT per-vertex timestamps — good for map visuals, useless for
  ETA targets.
- NOAA daily files contain receiver-noise positions outside US waters; the builder
  filters to lat 14–72, lon −180…−60. Do not remove this filter: the longest-voyage
  showcase fills with French/Fiji noise without it.
- AIS vessel types kept: 60–89 (passenger/cargo/tanker) + 30/31/32/52/53 in the raw
  samples; the MODEL trains on groups cargo/tanker/passenger only.
- Ports: UN/LOCODE `code-list.csv`, function contains `1`. **Must cluster within 20 km
  before buffer matching** (raw gazetteer has several entries per harbor; without
  clustering, nearest-port flicker shreds port visits into 0-duration slivers).

## Hard-won gotchas

1. **Timestamps are int64 milliseconds.** Hours = diff / 3.6e6 (NOT 3.6e12 — that was
   the silent zero-voyage bug). Minutes = diff / 6e4.
2. **pyarrow geometry column**: cast `binary → large_binary` BEFORE `.take()` or you
   hit "offset overflow while concatenating arrays".
3. **shapely 2.x**: `get_coordinates` returns ONLY the coordinate array; per-geometry
   counts come from `get_num_coordinates` (it does not return indices).
4. **LightGBM 4.7 sklearn API ignores `quantile_alpha`** — pass `alpha=` or all three
   "quantile" models come out identical (coverage exactly 0.0 is the tell).
5. **Trees cannot divide.** Feed them `remaining_distance_nm / speed` ratios
   (hours_at_current_speed, hours_at_type_speed, hours_at_sog6) or the GBM loses to a
   one-parameter speed prior.
6. **Categorical codes are positional.** Train/test/serving must share one fixed level
   list (models/categoricals.json); separate `astype('category')` calls misalign
   silently when a level is missing from one split.
7. **XGBoost CUDA**: `device="cuda"`, objective `reg:quantileerror`, wheels ship GPU
   support (xgboost ≥ 3). Calibrate intervals with CQR (models/conformal_q.json);
   clamp served P10 at ≥ 0.1 h.
8. **Open-Meteo batching**: ≤ 100 cells per call (414 on larger URLs), full-month
   range counts as ~2 quota calls per cell per API; cache every response to
   `data/interim/weather/` (reruns skip). Handle 429 with 120 s sleeps.
9. **pkill self-kill**: `pkill -f <pattern>` kills your own shell when the pattern text
   appears anywhere in your command line (e.g., `pkill -f 'uvicorn backend'` + a
   restart of `uvicorn backend.main:app` in the same compound command). Use the
   `[b]racket` trick AND never combine kill+start in one call.
10. **Owner process rules**: no foreground `sleep` — launch long jobs `nohup … & disown`
    with logs in `logs/`, then keep working and poll the log between tool calls. Never
    put project artifacts in /tmp or swap.

## Serving contract

`POST /v1/predict` needs lat/lon/dest, vessel_type_group, sog, sog_median_6h,
distance_traveled_nm, elapsed_h, month, hour, optional weather + ports. The backend
computes the three physics ratios and port "-1" (unknown) buckets itself — keep
`models/type_speeds.json`, `models/categoricals.json`, `models/conformal_q.json` in
sync with the trainer.

## Verification

- `pytest tests/` (no network) covers geometry, ports, Beaufort, PSI.
- `reports/eval.json` is the single source of truth for every number the website
  shows; `pipeline/export_web_data.py` copies it into `web/public/data/`. If a JSON
  is missing the UI must say "pipeline not run" — never fabricate numbers.
- After any model change: `make train && make drift && make web-data && (cd web &&
  bun run build)` then restart uvicorn and re-screenshot the dashboard.
