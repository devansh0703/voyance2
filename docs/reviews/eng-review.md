# Engineering Review — Voyance II plan (plan-eng-review)
**Verdict: APPROVE WITH CHANGES (3 blocking, 4 advisory)**

## Blocking
1. **EKF/UKF dt semantics** — `dts` are unix seconds; first `f.predict()` uses dt from index 1 — correct, but UKF reassigns `f.fx` inside the loop after `predict` — the FIRST predict uses the default identity fx. Fix: set fx before construction via closure over dt per step (use `UnscentedKalmanFilter.predict(fx=...)` argument). → FIXED in implementation: pass dt to predict and set fx at call time.
2. **DCPA/TCPA local frame bug risk** — `_lla_to_en(lat1, lon1, lat1, lon1)` uses (lat1,lon1) as both origin AND point → p1 is (0,0) by construction; correct relative geometry but fragile. Enforce origin = contact A and document.
3. **Digitraffic polling quota** — 20 s TTL is fine for one server, but the /live page polls every 20 s per OPEN BROWSER TAB. Add server-side shared TTL (present: module-level `_CACHE`) and a 5-tab client backoff note. (Accepted: single-operator deployment.)

## Advisory
4. Anomaly ensemble trained on Jan+Apr rows: lat/lon dominate Mahalanobis; normalize by region or expect geographic bias in composite score. Documented on the gauge.
5. HMM state naming by mean order is heuristic; drift/maneuver/transit labels are descriptive only.
6. `etopo_depth_track` nearest-neighbor fill is not bilinear despite the name — renamed comment; keep NN for the 1° grid (error ≪ contour width).
7. Maritime graph 600 nm cap excludes transpacific routes — stated limitation, not a bug.

## Tests added
- pytest: kinematics (DCPA head-on = 0, TCPA None for parallel), fuzzy CRI monotonicity, name_similarity, littles/MMC, H3 bin count.
