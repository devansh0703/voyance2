# Voyance — Evaluation & Drift Report

**Generated:** 2026-10-23 21:48 UTC ·
**Model:** xgboost-cuda-quantile-eta v1.2.0 · **Hardware:** NVIDIA GeForce RTX 4060 Laptop GPU (CUDA, tree_method=hist, device=cuda)
**Scope:** cargo + tanker + passenger vessels (NOAA AIS)

## 1. Summary

Voyance is an open-source maritime voyage-intelligence platform grown from idealab
idea #586938, pivoted per the owner to ship the model itself. This report is generated
directly from pipeline artifacts; no number is hand-entered.

- Training months: 2024-01, 2024-04 · Test month: 2024-07
- Rows: 10,366 train / 8,227 test (voyage-disjoint CQR holdout inside train)
- P50 test MAE: **4.49 h** vs speed-prior baseline 5.35 h
- P10–P90 empirical coverage: **83.0%** (nominal 80%) after a
  conformal adjustment of ±2.73 h (CQR, Romano et al. 2019)

## 2. Benchmark (same split, same features)

| Model | Hardware | Test MAE | MAPE |
|---|---|---|---|
| XGBoost quantile (served) | RTX 4060 GPU · CUDA | 4.49 h | 40.9% |
| LightGBM quantile | 14-thread CPU | 5.80 h | 63.4% |
| Speed-prior baseline | — | 5.35 h | 50.6% |

## 3. Error decomposition (P50, test month)

### By sea region

| Region | MAE (h) | Samples |
|---|---|---|
| us east coast | 5.94 | 3,307 |
| great lakes | 1.80 | 2,212 |
| us west coast | 3.32 | 1,599 |
| gulf of mexico | 9.07 | 722 |
| puerto rico caribbean | 2.55 | 276 |
| other us waters | 7.99 | 90 |
| hawaii pacific | 1.09 | 21 |

Full breakdowns — Beaufort wind class, vessel type group, distance-to-go bucket — are
in `reports/eval.json` and rendered live on the dashboard.

### Feature importance (gain, top 12)

| Feature | Gain |
|---|---|
| hours_at_type_speed | 579.7 |
| remaining_distance_nm | 487.7 |
| hours_at_current_speed | 441.1 |
| hours_at_sog6 | 172.3 |
| arr_port_idx | 119.7 |
| dep_port_idx | 96.3 |
| wind_gusts_10m | 68.5 |
| precipitation | 62.0 |
| sin_wave_dir | 54.9 |
| wave_height | 53.9 |
| vessel_draft | 53.1 |
| speed_kn | 51.1 |

## 4. Drift monitoring

Baseline feature distribution: 2024-01 (feature distribution reference). Reference MAE: 4.49 h.
Alert rule: any feature PSI > 0.2 or MAE ratio > 1.25.

| Slice | Rows | MAE (h) | MAE ratio | Drifted features (PSI) | Alert |
|---|---|---|---|---|---|
| 2024-04 | 6,868 | 5.98 | 1.33 | — | ALERT |
| 2024-07 | 8,227 | 4.49 | — | — | ok |

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
