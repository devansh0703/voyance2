<p align="center">
  <img src="web/public/favicon.svg" width="64" alt="Voyance" />
</p>

# Voyance — open-source maritime voyage intelligence

**AIS-grounded ETA models with weather-conditioned uncertainty, error decomposed by wind, sea region, and vessel type, drift monitoring with alerts, and research-grade dashboards.** Built entirely on open data: NOAA MarineCadastre AIS (CC0), Open-Meteo ERA5 reanalysis (CC BY 4.0), UN/LOCODE ports.

> Grown from [idealab idea #586938](https://idealab.ai/idea-details/586938) ("Fleet AI performance auditor for shipping and naval ops"), pivoted to shipping the model itself as the product. The full idea extraction is in [`docs/idea-source.md`](docs/idea-source.md).

## Headline results (real, reproducible)

Test = July 2024 holdout month; training = Jan+Apr 2024. Commercial scope: cargo, tanker, passenger vessels from NOAA AIS, joined to ERA5 wind/gusts/precipitation/temperature/humidity + ERA5 wave height/period/direction/swell on a 0.5° grid.

| Model | Hardware | Test MAE (h) |
|---|---|---|
| **XGBoost quantile (served)** | **RTX 4060 GPU (CUDA)** | **4.49** |
| LightGBM quantile | 14-thread CPU | 7.74 |
| Speed-prior baseline (distance ÷ type-median speed × 0.8) | — | 7.42 |

- P10–P90 interval: **conformalized** on a voyage-disjoint holdout (CQR, Romano et al. 2019) — see `reports/eval.json` for the exact empirical coverage and interval width on the test month.
- Error decomposed by Beaufort wind class, sea region, vessel type group, and distance-to-go bucket — all in `reports/eval.json`, all rendered in the dashboard.
- Drift: Evidently reports comparing April and July slices against the January feature distribution, plus real model-MAE ratios; machine-readable alerts in `reports/drift_summary.json`.

No synthetic numbers anywhere: if a pipeline artifact is missing, the dashboards say so instead of inventing data.

## The stack

```
NOAA AIS (CC0) ──► voyage segmentation ──► ERA5 weather join ──► XGBoost CUDA quantiles ──► FastAPI ──► dashboards
UN/LOCODE ports ──┘        (15 km port buffers)   (0.5° grid, 100% coverage)        P10/P50/P90 + CQR      │
Open-Meteo (CC BY 4.0) ───────────────────────────────────────────────────────────────────────────────────┘
```

- **Pipeline** (`pipeline/`): daily AIS GeoParquet → port-buffer voyage segmentation → 1-hour sample extraction with real timestamps and SOG → Open-Meteo archive + marine archive joins (disk-cached, rate-limit aware) → training, evaluation, drift, and web-data export.
- **Serving** (`backend/`): FastAPI with `/v1/predict` (quantile ETA + Beaufort context), `/v1/metrics`, `/v1/drift`, `/v1/voyages`, Prometheus metrics, OpenAPI schema, and static hosting of the built dashboard.
- **Web** (`web/`): Vite + React 19 + Tailwind 4, MapLibre GL voyage map, globe.gl 3-D traffic globe, ECharts statistical panels, framer-motion scrollytelling. 2026 design language: bento grids, glassmorphism chrome, kinetic type, aurora gradient mesh, reduced-motion support.

## Quickstart

```bash
git clone https://github.com/devansh0703/voyance && cd voyance
uv venv .venv && uv pip install -r requirements.txt   # or pip install -r requirements.txt

make data      # download 21 AIS days (~4.5 GB) + build voyages + weather joins
make train     # XGBoost CUDA quantiles (+ LightGBM CPU benchmark)
make drift     # Evidently drift reports + alerts
make web-data  # export JSON bundles for the dashboards
make web       # build the site (bun)
make api       # serve on :8000 (API + dashboard)
```

One prediction:

```bash
curl -s -X POST localhost:8000/v1/predict \
  -H 'content-type: application/json' \
  -d '{"lat":33.7,"lon":-118.2,"dest_lat":37.79,"dest_lon":-122.27,
       "vessel_type_group":"tanker","vessel_length":250,"vessel_draft":12.5,
       "sog":12.4,"sog_median_6h":12.9,"distance_traveled_nm":820,"elapsed_h":68,
       "month":7,"hour":14,"wind_speed_10m":12,"wave_height":1.8}'
```

GPU note: training uses `device="cuda"` (any CUDA GPU works; the published run used an RTX 4060 Laptop 8 GB). Set `CUDA_VISIBLE_DEVICES=""` and the LightGBM fallback still trains on CPU.

## Product surfaces

| Surface | What it shows |
|---|---|
| Landing (`/`) | Live metric strip from real eval JSON, feature bento, competitive matrix from the idealab market analysis, architecture |
| Dashboard (`/dashboard`) | Map (showcase voyages + error), 3-D globe (lane density), Model (MAE by weather/region/type/distance, calibration, feature importance), Drift (weekly MAE ratio + PSI alerts) |
| Research (`/research`) | Methodology, papers the approach stands on, headline results, data provenance |
| Docs (`/docs`) | Quickstart + REST surface |

## Data provenance & licenses

- AIS: NOAA Office for Coastal Management / MarineCadastre — CC0 1.0 (citation in `docs/ATTRIBUTION.md`)
- Weather: Open-Meteo historical weather + marine APIs (ERA5) — CC BY 4.0
- Ports: UN/LOCODE (UNECE) — open
- Code: Apache-2.0

## Honest limitations

US-waters AIS only (NOAA coverage); voyages cannot span the downloaded week boundaries; ERA5 reanalysis smooths local weather; port queues are only partially visible in AIS; tug/fishing vessels are excluded from the model by design (loitering is not an ETA problem). The speed prior is deliberately naive — it anchors the improvement claim. Not a certified navigation aid.

## Landscape (from idealab #586938)

Windward, PortXchange ETAPredictor, WHIZTEC, Broadpath, and Kairon all sell closed operational-intelligence or ETA products; WUT-TrajData is an open benchmark but not a served model. **Voyance is the open, served, weather-conditioned quantile model with published error decomposition and drift monitoring.** Details in [`docs/idea-source.md`](docs/idea-source.md).
