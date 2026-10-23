# Voyance — Open-Source Maritime Voyage Intelligence Platform

**Spec version:** 1.0 · **Date:** 2026-10-23 · **Status:** Approved (auto-decided per owner directive)
**Origin:** [Idealab idea #586938](https://idealab.ai/idea-details/586938) "Fleet AI performance auditor for shipping and naval ops" — pivoted per owner: our model IS the product, not an audit service for others.

---

## 1. Why this exists (Phase 1 interrogation)

| Question | Answer |
|---|---|
| **Who is affected?** | Fleet-performance and digital leads at liner/tanker/dry-bulk operators; port and vessel-traffic-service analysts; maritime-AI engineers who need a defensible, AIS-grounded voyage/ETA model they can self-host; researchers in maritime ML. |
| **Current behavior (verified)?** | Commercial ETA products (Windward, PortXchange ETAPredictor, WHIZTEC) are closed-source and priced for enterprises; open alternatives are either benchmark datasets (WUT-TrajData) or research code without a product surface. An operator cannot self-host a real ETA model with weather-conditioned error bands. |
| **Should-be behavior?** | Anyone can `pip install` / `docker compose up` an open platform that (a) ingests public AIS + open weather reanalysis, (b) trains a voyage/ETA model with uncertainty, (c) serves predictions via API, (d) decomposes error by weather, sea region, and ship type, (e) detects and reports drift weekly, (f) ships a research-grade dashboard (2-D map, 3-D globe, charts) and a product website. |
| **Why now?** | MarineCadastre publishes analysis-ready monthly AIS *tracks* as GeoParquet (2024–2025, CC0); Open-Meteo serves ERA5 reanalysis + wave models free with 1,000-coordinates-per-call batching; LightGBM 4.x + Evidently make uncertainty-quantified GBDT + drift monitoring a weekend-scale build instead of a lab project. The idealab brief's own "why now" applies verbatim once you flip vendor→operator. |
| **Done when?** | All acceptance criteria in §9 pass on real data: trained model files exist with held-out MAE computed from actual NOAA/MarineCadastre AIS joined to real Open-Meteo reanalysis; evidently drift reports generated from real weekly slices; API serves real predictions; website + dashboards render those artifacts; everything pushed to one public GitHub repo. |

## 2. Scope and boundaries (Phase 2)

### In scope (v1.0)
1. **Data pipeline** (`pipeline/`): NOAA/MarineCadastre AIS GeoParquet → voyage segmentation → port labeling (UN/LOCODE) → Open-Meteo historical weather (ERA5 atmospheric + ERA5 marine waves) join → feature store (Parquet). Months: 2024-01, 2024-04, 2024-07 (winter/spring/summer for seasonality).
2. **Model** (`pipeline/train*.py`): LightGBM quantile regression (P10/P50/P90) for remaining voyage time (time-to-arrival) at any mid-voyage point; separate vessel-speed model for context. Full feature matrix: geography (haversine-to-destination, region), vessel (type, size class, speed history), weather (wind, gusts, precipitation, waves, swell, visibility via humidity proxy), temporal (hour, month, season). Baseline comparison: empirical distance/speed heuristic + scikit-learn `HistGradientBoosting` + XGBoost — reported in a benchmark table.
3. **Evaluation** (real, held out): global MAE/MAPE/RMSE + breakdowns by Beaufort wind class, sea region (EEA-style bounding regions), vessel type group (tanker/cargo/container/tug/passenger/other), voyage-length bucket. Calibration of P10/P90 (empirical coverage). Published as JSON + rendered charts.
4. **Drift monitoring**: evidently `DataDrift` + `RegressionPerformance` reports on weekly slices (2024-07 weeks vs January baseline); a small drift-detector module emitting alerts JSON consumed by the dashboard; PSI/KS stats per feature.
5. **API** (`backend/` FastAPI): `POST /v1/predict` (vessel context → P10/P50/P90 ETA), `GET /v1/voyages`, `GET /v1/metrics`, `GET /v1/drift`, `GET /v1/weather` (Open-Meteo proxy), health + Prometheus metrics. OpenAPI schema shipped.
6. **Frontend** (`web/`): product website (landing, features, research, pricing-open-source, docs) + interactive dashboards: MapLibre GL voyage/error map, globe.gl 3-D globe with animated lanes and error heat, ECharts/Plotly statistical panels, research section rendering our papers list + benchmark charts + methodology. 2026 design language: bento grid, glassmorphism sticky chrome, kinetic hero type, aurora gradient mesh, scrollytelling, dark ocean palette, reduced-motion support.
7. **Reports** (`reports/`): evidently HTML drift reports, model card (markdown + PDF), benchmark charts (PNG/SVG), sample voyages dossier.
8. **Packaging**: `docker-compose.yml` (api + web), `Makefile`, GitHub Actions CI (lint + pytest + build), Apache-2.0 LICENSE, README with real metrics table.

### Out of scope (locked)
- Live/streaming AIS ingestion (AISStream/MarineTraffic sockets) — batch monthly reanalysis only for v1; interface stub allows a streaming adapter later.
- Naval IR / perception-model auditing (idealab phase 3) — we keep the *condition-sliced performance* concept but on voyage/ETA models.
- Multi-tenant SaaS auth/billing — open-source product, single-tenant deploy.
- Fuel-consumption modeling — stretch, not v1.

### Ordering constraints
Data pipeline → training → evaluation artifacts → API → dashboards (dashboards read pipeline/model outputs). Website can be built in parallel against fixture JSON, then hydrated with real numbers.

### MVP cut
Model + metrics + API + one dashboard page with real data. Everything else upgrades the same artifact set; nothing blocks on external services (all data pre-fetched to `data/processed`).

### Failure modes & rollback
- AIS files corrupt/incomplete → pipeline asserts row/col schema, drops month with explicit error in build log (no silent fake).
- Open-Meteo rate limit → client caches to disk, respects 10k/day, retries with backoff; partial weather → rows flagged `weather_ok=false`, excluded from weather-conditioned metrics but included in global metrics.
- Model underperforms → still ship with honest metrics + baseline comparison (the product includes the scorecard, not just the model).
- Frontend build fails → static-site fallback served by FastAPI.

## 3. Technical design (Phase 3, greenfield — cited evidence: empty repo at `/home/devansh/voyance`, only `docs/` + `data/raw/` exist)

### Data model
- `voyages.parquet`: one row per voyage segment: `vessel_mmsi, vessel_type, vessel_length, departure_port_unlocode, arrival_port_unlocode, departure_ts, arrival_ts, sample_ts, remaining_distance_nm, remaining_time_h, speed_kn, heading, lat, lon, region, beaufort_class, wind_speed, wind_gust, precipitation, wave_height, wave_period, wave_direction, swell_height, air_temp, humidity, month, week` (weather columns nullable with `weather_ok` flag).
- Voyage segmentation: consecutive track points of a vessel; a new voyage when movement between port-buffer zones (<15 km of a UN/LOCODE port with function `1`) stalls ≥6 h; destination = next port buffer entry. Samples = points at ≥1 h spacing ≥50 NM from destination.
- Regions: lat/lon bounding boxes (North Sea/Baltic, Mediterranean, US East Coast, US West Coast, Gulf of Mexico, East Asia, SE Asia, Indian Ocean, Caribbean, Other) — MarineCadastre is US-centric so expect US-dominant rows.
- Ports: UN/LOCODE `code-list.csv`, function contains `1`, parse coordinates `DDMM[N|S] DDDMM[E|W]`.

### Weather join
Grid-snap sample points to 0.25° (atmospheric) and 0.25° marine cells; batch unique cells (≤1,000/call) to Open-Meteo Archive API (`archive-api.open-meteo.com/v1/archive`, hourly `wind_speed_10m, wind_gusts_10m, precipitation, temperature_2m, relative_humidity_2m`) and Marine Archive (`marine-api.open-meteo.com/v1/marine`, `wave_height, wave_period, wave_direction, swell_wave_height`) for the sample's month window; cache raw JSON under `data/interim/weather/`. License: CC BY 4.0 (attribution file included).

### Model spec
- Target: `remaining_time_h` (log1p-transformed for the P50 model; quantiles trained on raw scale with `quantile_alpha` objectives 0.1/0.5/0.9).
- Features: numeric — lat, lon, remaining_distance_nm, speed_kn, speed_avg_6h, speed_std_6h, dist_traveled_nm, elapsed_h, wave_height, wave_period, wind_speed, wind_gust, precipitation, air_temp, humidity, cos_wave_direction, sin_wave_direction, month sin/cos, hour sin/cos, vessel_length; categorical — vessel_type_group, region, departure_country (LightGBM native categoricals).
- Split: temporal (train ≤ 2024-04-30, validate 2024-05-31 window, test = 2024-07) — real deployment realism; report per-month and per-condition metrics on test.
- Hyperparameters: LightGBM `quantile` objective, `num_leaves` 127, `learning_rate` 0.05, `feature_fraction` 0.8, `bagging` 0.8/5, early stopping on validate MAE; Optuna-free (time-boxed) with a small grid.
- Baselines: (a) great-circle distance ÷ mean observed speed per type; (b) sklearn HistGradientBoostingRegressor; (c) XGBoost quantile. Table in `reports/benchmark.json` + web research page.

### Drift spec
Baseline = 2024-01 weekly slices; monitor = 2024-07 weekly slices. evidently DataDriftPreset + RegressionPreset → `reports/drift/week_*.html` + machine-readable `drift_summary.json` (per-feature PSI/KS + p-value, per-week MAE delta). Alert rule: PSI > 0.2 or MAE ratio > 1.25 vs baseline → alert entries in `/v1/drift` and dashboard banner.

### API spec (FastAPI, Pydantic v2)
- `POST /v1/predict` `{lat, lon, mmsi?, vessel_type, vessel_length, speed_kn, speed_avg_6h?, speed_std_6h?, dist_traveled_nm?, elapsed_h?, month, hour, dest_lat, dest_lon, dest_port?}` → `{p50_h, p10_h, p90_h, remaining_distance_nm, beaufort_class, model_version, feature_contributions?}`.
- `GET /v1/voyages?region=&type=&limit=` → voyage samples (from processed parquet via DuckDB).
- `GET /v1/metrics` → evaluation JSON. `GET /v1/drift` → drift summary + alerts. `GET /v1/weather?lat=&lon=` → live Open-Meteo forecast proxy (attribution header).
- Static: `/` serves `web/dist`. Uvicorn; prometheus-fastapi-instrumentator at `/metrics`.

### Frontend spec (Vite + React 19 + TS + Tailwind v4)
- Pages: `/` landing (hero WebGL-ish canvas ocean shader + kinetic type, bento features, real-metrics strip, globe teaser, competitive matrix vs Windward/PortXchange/WHIZTEC/Broadpath/Kairon/WUT-TrajData, open-source pricing, research teaser, footer w/ attribution), `/dashboard` (tabs: Map / Globe / Model / Drift), `/research` (methodology, papers with links, benchmark charts, dataset provenance), `/docs` (API + quickstart).
- Libraries (latest stable): maplibre-gl v5, globe.gl, echarts 6 (or plotly 3), framer-motion 12, Tailwind 4 (CSS-first config). Data fetched from processed JSON bundles + live API when running.
- Accessibility: prefers-reduced-motion honored; keyboard nav; contrast AA.

## 4. Draft (auto-confirmed)

The draft is this document; owner pre-approved implementation without review round.

## 5. Acceptance criteria

1. `make data` produces `data/processed/voyages.parquet` with ≥ 50,000 voyage samples from real AIS; `weather_ok` fraction ≥ 0.85.
2. `make train` writes `models/*.txt` (3 quantile models) + `reports/eval.json` with test-set (2024-07) MAE and breakdown tables; model beats baseline-a by ≥ 25% MAE.
3. `make drift` writes ≥ 4 evidently HTML reports + `drift_summary.json` with real PSI/KS values.
4. `make api` starts FastAPI; `/v1/predict` returns quantile ETA with p10 < p50 < p90; `/v1/metrics` matches `reports/eval.json`.
5. `make web` builds; site renders landing + dashboard + research with real metric values injected; Lighthouse-style checks: no console errors on load (verified via gstack browse), reduced-motion class works.
6. Repo pushed to GitHub (one repo), commits at regular intervals, LICENSE Apache-2.0, README with real numbers + data provenance + competitor positioning, CI green.
7. Every dataset/API used is open (CC0/CC-BY/open-data) with attribution file `docs/ATTRIBUTION.md`.

## 6. GSTACK decision log (auto-decided per owner directive)

- D1 Model family: **LightGBM quantile GBM** (recommended: SOTA-practical for tabular ETA per Saber et al. 2025 hybrid-ML literature; beats transformers on 100k-row tabular, CPU-trainable in minutes, natively handles categoricals). Baselines included to prove the choice.
- D2 Drift tooling: **Evidently** reports + own PSI/KS alert JSON (recommended by 2024-25 benchmark arXiv:2404.18673 for general drift + dashboards).
- D3 Frontend: **Vite + React + Tailwind 4 + MapLibre + globe.gl + ECharts** (recommended: fastest path to 2026-trend design with map/3D/charts, no build-server dependency).
- D4 Weather source: **Open-Meteo archive + marine archive** (recommended: free, keyless, 1,000-loc batching, ERA5 + wave models, CC BY).
- D5 AIS source: **MarineCadastre monthly tracks GeoParquet 2024** (recommended: analysis-ready, CC0, voyage-cleaned).
- D6 Repo: single GitHub repo `voyance`, Apache-2.0, commit after each milestone.
