# Data & Service Attribution

Voyance is built entirely on open data and open tooling. We are grateful; these are the sources and their licenses.

## Data sources

| Source | What we use | License | Link |
|---|---|---|---|
| NOAA Office for Coastal Management / MarineCadastre | U.S. AIS broadcast points (daily GeoParquet, 2024) and monthly vessel tracks | CC0 1.0 Universal | https://hub.marinecadastre.gov · https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ |
| U.S. Coast Guard Navigation Center | Raw AIS feed underlying the above (acknowledged by NOAA) | public | https://www.navcen.uscg.gov/ |
| Open-Meteo | Historical Weather API (ERA5 reanalysis: 10 m wind, gusts, precipitation, temperature, humidity) and Marine API (ERA5 wave height/period/direction, swell) | CC BY 4.0 (data), API free for non-commercial use | https://open-meteo.com |
| UN/LOCODE (UNECE) | Port gazetteer (function code 1 = port), coordinates | open (UNECE terms) | https://unece.org/trade/cefact/UNLOCODE-Download · mirror: https://github.com/datasets/un-locode |

Citation for AIS data (per NOAA):
> Martin, Daniel R., Jesse Brass, Matthew Dornback, and Jeremy Fontenault. 2026.
> Nationwide Automatic Identification System 2024. NOAA Office for Coastal Management.

## Model & method lineage

| Component | What it is | License |
|---|---|---|
| LightGBM | Quantile gradient-boosted trees (P10/P50/P90 ETA) | MIT |
| scikit-learn | HistGradientBoosting baseline, metrics | BSD-3 |
| Evidently | Data-drift + regression-performance reports | Apache-2.0 |
| shapely / pyarrow | WKB geometry decoding / columnar IO | BSD / Apache-2.0 |
| FastAPI + Uvicorn | Serving layer | MIT |
| MapLibre GL JS | 2-D voyage map | BSD-3 |
| globe.gl / three-globe | 3-D traffic globe | MIT |
| Apache ECharts | Statistical panels | Apache-2.0 |
| Framer Motion | UI motion | MIT |

## Key research the approach follows

- Saber et al. 2025 — High-accuracy vessel ETA prediction in seaports, hybrid ML (Baltic AIS).
- Noman et al. 2025 — Multi-model learning for vessel ETA (inland waterways).
- Cheng et al. 2026 — BiLSTM+attention vessel ETA (MDPI JMSE).
- Chen et al. 2026 — Bayesian-optimized deep ETA (MDPI).
- "Open-Source Drift Detection Tools in Action" (2024), arXiv:2404.18673 — basis for choosing Evidently.

## Non-commercial note

Open-Meteo's free tier is licensed for non-commercial use. If you operate Voyance
commercially, obtain an Open-Meteo API key (or another reanalysis source) and keep
the CC BY 4.0 attribution.
