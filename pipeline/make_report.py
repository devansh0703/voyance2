"""Assemble reports/voyance-report.md from real pipeline artifacts, for make-pdf."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

e = json.loads((REPORTS / "eval.json").read_text())
d = json.loads((REPORTS / "drift_summary.json").read_text())
b = e["benchmark"]


def mae(x):
    return f"{x['mae_h']:.2f} h"


rows = "\n".join([
    f"| XGBoost quantile (served) | RTX 4060 GPU · CUDA | {mae(b['xgboost_gpu_p50'])} | {b['xgboost_gpu_p50']['mape']*100:.1f}% |",
    f"| LightGBM quantile | 14-thread CPU | {mae(b['lightgbm_cpu_p50'])} | {b['lightgbm_cpu_p50']['mape']*100:.1f}% |",
    f"| Speed-prior baseline | — | {mae(b['speed_prior_baseline'])} | {b['speed_prior_baseline']['mape']*100:.1f}% |",
])

drift_rows = "\n".join([
    f"| {w['slice']} | {w['n']:,} | {w['mae_h']:.2f} | "
    f"{w.get('mae_ratio_vs_test_overall') or '—'} | "
    f"{(', '.join(f['feature'] + ' (' + str(f['psi']) + ')' for f in w['drifted_features']) or '—')} | "
    f"{'ALERT' if w['alert'] else 'ok'} |"
    for w in d["weeks"]
])

top_regions = e["breakdown_p50"]["region"]
region_rows = "\n".join(
    f"| {k.replace('_', ' ')} | {v['mae_h']:.2f} | {v['n']:,} |"
    for k, v in sorted(top_regions.items(), key=lambda kv: -kv[1]["n"])[:8]
)

imp_rows = "\n".join(
    f"| {f['feature']} | {f['gain']:,} |" for f in e["feature_importance"][:12]
)

doc = f"""# Voyance — Evaluation & Drift Report

**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ·
**Model:** {e['model']} · **Hardware:** {e.get('hardware', '—')}
**Scope:** {e.get('scope', '—')}

## 1. Summary

Voyance is an open-source maritime voyage-intelligence platform grown from idealab
idea #586938, pivoted per the owner to ship the model itself. This report is generated
directly from pipeline artifacts; no number is hand-entered.

- Training months: {', '.join(e['trained_on'])} · Test month: {', '.join(e['test_on'])}
- Rows: {e['train_rows']:,} train / {e['test_rows']:,} test (voyage-disjoint CQR holdout inside train)
- P50 test MAE: **{e['global']['p50']['mae_h']:.2f} h** vs speed-prior baseline {e['global']['baseline_speed_prior']['mae_h']:.2f} h
- P10–P90 empirical coverage: **{e['coverage_p10_p90']*100:.1f}%** (nominal 80%) after a
  conformal adjustment of ±{e.get('conformal_adjustment_h', 0):.2f} h (CQR, Romano et al. 2019)

## 2. Benchmark (same split, same features)

| Model | Hardware | Test MAE | MAPE |
|---|---|---|---|
{rows}

## 3. Error decomposition (P50, test month)

### By sea region

| Region | MAE (h) | Samples |
|---|---|---|
{region_rows}

Full breakdowns — Beaufort wind class, vessel type group, distance-to-go bucket — are
in `reports/eval.json` and rendered live on the dashboard.

### Feature importance (gain, top 12)

| Feature | Gain |
|---|---|
{imp_rows}

## 4. Drift monitoring

Baseline feature distribution: {d['baseline']}. Reference MAE: {d.get('reference_mae_h', 0):.2f} h.
Alert rule: any feature PSI > 0.2 or MAE ratio > 1.25.

| Slice | Rows | MAE (h) | MAE ratio | Drifted features (PSI) | Alert |
|---|---|---|---|---|---|
{drift_rows}

HTML reports: `reports/drift/` (Evidently). Machine-readable alerts: `GET /v1/drift`.

## 5. Method

Voyages are segmented from NOAA MarineCadastre daily AIS broadcast points by 15 km
UN/LOCODE port buffers (20 km clustering of adjacent gazetteer entries), with
receiver-noise plausibility filters (US-waters bounding box, per-fix implied speed
< 90 kn, per-voyage implied speed < 40 kn). Samples ≥ 1 h apart and ≥ 8 NM from the
destination join hourly ERA5 reanalysis (wind, gusts, precipitation, temperature,
humidity) and ERA5 wave data (height, period, direction, swell) on a 0.5° grid via
Open-Meteo (CC BY 4.0). The target is remaining time to arrival at the destination
port. Temporal split: train Jan+Apr 2024, test Jul 2024.

## 6. Limitations

US-waters AIS only; voyages cannot span the downloaded week boundaries; ERA5 smooths
local weather; port queues are partially visible; tug/fishing vessels excluded by
design. Not a certified navigation aid. Full list: `reports/model-card.md`.

## 7. Provenance

NOAA MarineCadastre AIS (CC0) · Open-Meteo ERA5 (CC BY 4.0) · UN/LOCODE (UNECE) ·
LightGBM/XGBoost/Evidently (MIT/Apache-2.0). Attribution: `docs/ATTRIBUTION.md`.
"""

out = REPORTS / "voyance-report.md"
out.write_text(doc)
print(f"wrote {out}")
