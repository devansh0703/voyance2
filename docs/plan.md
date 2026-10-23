# Voyance II — Implementation Plan (v2.0)

**Status:** executing · **Window:** 1 hour · **Owner directives honored:** GPU training, no subagents, no-sleep/no-tmp workflow, GSTACK full suite, live keyless data only for live features.

## Goal
Fork Voyance (v1 = batch AIS/ETA platform) into Voyance II: a **live maritime intelligence terminal** with real-time AIS, collision analytics, tracking filters, spatial/queueing/fuel analytics, and a dense terminal-editorial UI — replacing the gradient-heavy v1 aesthetic.

## Workstreams

### W1 — Live data layer (keyless only)
Digitraffic Finland AIS (vessels + metadata, 20 s TTL), Open-Meteo forecast + marine, NOAA NWS point forecasts, NDBC realtime buoys (9 stations), USGS quakes, OBIS/GBIF occurrences, ETOPO1 bathymetry via ERDDAP, Marine Regions MPAs via WFS. Disk-cached with per-source TTLs; every upstream failure degrades to "—" not fake data.

### W2 — Algorithms (libraries first; domain equations hand-written where they are formulas, not algorithms)
- Tracking: EKF + UKF (filterpy), cubic splines (scipy), Douglas-Peucker (shapely), Fréchet (shapely), Vincenty (pyproj), haversine (haversine lib)
- Collision: DCPA/TCPA solver, Goodwin-Stanton domain ellipses, fuzzy CRI (standard COLREG-domain formulas)
- Clustering/indexing: H3 hexbins, HDBSCAN anchorages, IsolationForest + GMM + Mahalanobis anomaly ensemble (sklearn)
- Sequences: Gaussian HMM regimes (hmmlearn), Markov transition matrices
- Graphs: maritime port graph, Dijkstra + A* (networkx)
- Fuel/CO2: ITTC-1978 Cf, Townsin-Glover added resistance, IMO C-factors
- Record linkage: Levenshtein + Jaro-Winkler (rapidfuzz) over the clustered port table
- Queues: Little's Law (L=λW), M/M/c Erlang-C
- Outliers: z-score, IQR — surfaced in a data-quality health strip

### W3 — GPU training additions (owner directive)
- Random-forest runtime regressor via XGBoost `num_parallel_tree=100, device=cuda`
- Anomaly ensemble + HMM artifacts saved to models/ for the live API
- v1 quantile models remain the served ETA (already GPU)

### W4 — UI (de-slop)
Terminal-editorial system per research: flat near-black, hairline rules, JetBrains Mono data type, single amber accent, dense tables, zero gradients/glass/glow. New pages: /live (fleet register, live map with heading vectors, collision watch, weather stack, health strip, ticker), /analytics (H3 heatmap, anchorage queues, A* router, fuel/CO2 calculator, anomaly gauge, depth profiles, HMM regimes, biodiversity chips).

### W5 — GSTACK
office-hours, plan-eng/design/devex reviews on this plan, qa, review, ship, landing-report, retro.

## Risks
- Upstream availability (Digitraffic rate limits) → TTL cache + graceful "—"
- GPU contention with v1 artifacts → single training job at a time
- Time box → library-first implementation, no hand-rolled algorithms
