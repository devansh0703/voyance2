# Voyance II — Speaker Notes (10 slides · ~10 minutes)

> Deck: `reports/voyance2-deck.pptx` · Regenerate any time with `python scripts/make_deck.py`
> Every number on every slide comes from a pipeline artifact (`reports/eval.json`, `reports/drift_summary.json`, `web/public/data/stats.json`) — if someone asks "where does that number come from," the source line at the bottom of the slide names the file.

---

## Slide 1 — Cover (dark)

**Say:** "This is Voyance II — an open-source maritime intelligence terminal. The one-line pitch is right there: know where your ETA model fails, before the storm does. The four numbers at the bottom are the whole story in miniature: a 4.49-hour test MAE from a GPU-trained model, 83% empirical coverage on our uncertainty bands, eight thousand real voyages modeled, and more than twenty-five open data sources — no paid APIs anywhere."

**Timing:** 30 seconds. Don't read the stats twice — point once, move on.

---

## Slide 2 — The Problem

**Say:** "This comes from a real market analysis — idealab idea #586938. A fleet team buys an arrival estimate from a vendor and has no way to see where it fails in bad weather or specific waters. Windward, PortXchange, WHIZTEC — they all sell closed operational intelligence. Nobody ships an open, *served*, weather-conditioned model that also shows its own error honestly. That's a hundred-million-dollar wedge, inside a four-point-three billion broader market."

**If asked "why now?":** public AIS data and free reanalysis weather became good enough that repeated weekly checks cost almost nothing — that's the idealab 'why now' verbatim.

---

## Slide 3 — The Product Pipeline

**Say:** "The system is five stages. Ingest public AIS. Segment it into voyages with port buffers and plausibility filters — we throw away GPS flapping noise. Join hourly ERA5 weather — wind, waves, swell — onto every fix. Serve quantile ETAs from FastAPI. And watch the model drift in production. The line at the bottom matters most: every layer is open data with its license named — NOAA CC0, Open-Meteo CC BY, OSM ODbL. Zero signups, and nothing on any screen is ever a fabricated number."

**Emphasize:** "zero signups" and "zero fabricated numbers" — these are the product's two trust claims.

---

## Slide 4 — The Model (benchmark chart)

**Say:** "Here's the honest benchmark, same split, same features. Our served model — XGBoost quantiles trained on an RTX 4060 — gets 4.49 hours MAE. The deliberately naive speed prior gets 5.35. That's a 16% improvement; we publish the baseline precisely so the claim is anchored. On the right: why you can trust the uncertainty — conformal quantile regression widens the P10–P90 band using a voyage-disjoint holdout, giving 83% empirical coverage against 80% nominal. And one modeling insight: gradient-boosted trees can't divide, so we hand them distance-over-speed ratio features — without those, we *lost* to the naive prior."

**If asked about training cost:** the whole training run is minutes on a laptop GPU; CPU LightGBM is kept as a published comparison row.

---

## Slide 5 — The Prediction Surface

**Say:** "The product is not the model — it's the prediction, laid out. On the predict page you get the actual track and remaining leg on real chart geography, a drift cone whose width is literally the model's P10–P90 spread at that point, and — this is the credibility trick — dashed grey lines showing the *historical analog voyays*: real prior trips to the same port with the same ship type. An operator doesn't have to trust the model; they can see the trips it learned from. Everything is one GeoJSON endpoint, so integrators get the same surface programmatically."

---

## Slide 6 — Live Operations

**Say:** "On the live side: three hundred vessels tracked right now from Digitraffic's keyless AIS feed, refreshing every twenty seconds. Collision watch runs a DCPA/TCPA solver with Goodwin-Stanton ship-domain ellipses and a fuzzy collision-risk index — the encounter view literally draws the safety ellipse and CPA lines on the chart. Tracking uses Extended and Unscented Kalman filters. Overlays: protected-area polygons, earthquakes, animated weather radar, Sentinel-1 SAR chips. And the data-quality strip audits our own feed with IQR and z-score checks."

**Punchline:** "It's a Bloomberg terminal for a fleet team — but every feed is free and keyless."

---

## Slide 7 — The AI Analyst

**Say:** "Newest piece: an AI analyst that answers questions like 'why will this route drift tomorrow for this ship type?' — and is *forbidden from inventing numbers*. It answers only from a context packet: the live forecast at the vessel, the model's tested MAE and top features, and the real analog voyages. The output is parsed into four sections — headline, why drift is expected, reference backing, what to watch — and every reference names a real voyage ID you can replay on the map in one click. Provider-wise, we honor the OPENCODE_API_KEY first and fall back through chat-verified Groq and OpenRouter — each response states exactly who served it."

**Honesty note if asked:** OpenCode's key currently authenticates but its chat endpoints reject third-party use — we surface that error transparently rather than hiding the fallback.

---

## Slide 8 — Drift Monitoring

**Say:** "Production honesty. Monthly slices versus a January baseline: Evidently computes per-feature PSI and KS statistics; anything above PSI 0.2 or an MAE ratio over 1.25 fires an alert. The chart shows April drifted at 1.33× — and the dashboard shows *which features* drifted, the distance and speed mix, as an explainable chip rather than a silent degradation. This drift view itself was a bug report from our own review: the tab crashed because the frontend and backend disagreed on a field name — fixed, and now it renders two charts plus a slice table."

---

## Slide 9 — Positioning

**Say:** "Why this wins: the closed vendors sell visibility, not independent error audit. The open benchmark — WUT-TrajData — is a dataset, not a served product. We're the only box that is simultaneously open-source, self-hostable, a served quantile model, *and* its own scorecard with an AI analyst on top. And because it's Apache-2.0, a classification society or a port authority can adopt it without a procurement cycle."

---

## Slide 10 — Closing (dark)

**Say:** "You can run all of this yourself: clone the repo, make data, make train, make api. Or just run start.sh — one script boots the API, the dashboards, the live feeds, and the AI analyst. Voyance II: open-source maritime voyage intelligence. Thank you — and the repo URL stays on screen."

**Q&A prep:** the three most likely questions are (1) data licensing for commercial use — Open-Meteo free tier is non-commercial, swap a key for production, it's one env var; (2) global coverage — NOAA AIS is US waters, Digitraffic adds the Baltic live, the pipeline takes any AIS feed; (3) model freshness — retraining is a single make target, minutes on a laptop GPU.
