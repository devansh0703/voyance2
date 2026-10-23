# Idealab Idea #586938 — Source Extraction (2026-10-23)

> Extracted in full from https://idealab.ai/idea-details/586938 via gstack `browse` (all four tabs: plan, market & competitors, founder profile, lineage & sources).

## Title
**Fleet AI performance auditor for shipping and naval ops** — "Public ship signals make model checks practical"

## Brief
Cheap ship tracking and model logs now let operators check predictions against real voyages every week. A fleet team trusts a vendor's arrival estimate but cannot see where it fails in bad weather or certain waters. The business sells independent checks of black-box models, joining their predictions to AIS positions. Teams see errors by weather, region, and ship type, then get alerts when results drift. The bet: partners keep sending model logs and pay for ongoing checks, with three still streaming by month three and asking to assess another model type.

## Scores
Clear idea 7 · Open space 6 · Stands out 5→7 · AI-runnable 8 · Problem pain 6 · Timing 6 · Hard to copy 4 · Market 5 · Conviction 6 · License potential 8

## Snapshot
- Wedge market (model estimate): **$100M** (~1,500 digitally active shipping companies × $40K/yr + ~250 maritime AI vendors × $60K/yr + ~60 allied naval/USV programs × $350K/yr)
- Wider market (web-verified): **$4.3B** (global maritime AI market, Grand View Research)
- Capital to start: $220K · Time to market: 5 mo · Team: small (2–5) · Revenue if it works: $12M/yr · Boldness 4/10 · Continent (Multinational)

## 01 The plan
**Why now:** cheap ship-location data + low-cost model logs make repeated checks possible where one-off studies once carried the burden. Deep-learning systems now guide ship arrival estimates and naval infrared sensing, while operators still judge them from vendor claims. Public ship data gives an outside measure of performance.

**First customers:** fleet teams comparing vendor claims with delayed arrivals, fuel use, safety events. A digital/fleet-performance lead buys when a new model enters use or a vendor must defend results in a tender. First firms run liner, tanker, dry-bulk fleets; later ports and vessel-traffic services.

**What to build first:** a web scorecard that takes model logs, matches each prediction to a ship's later AIS position, and shows error and drift by sea area, ship type, and weather. Start with one week of logs, then weekly feeds. Eight design partners: four maritime software vendors + four mid-size fleet digital teams.

**First 90 days:** build a monitoring loop that scores black-box ship trajectory and ETA models against AIS ground truth, sliced by sea region, vessel class, weather. Recruit design partners through DNV and Lloyd's Register innovation programs, CMA Shipping and Nor-Shipping, AIS-analytics communities. Ship a vendor-and-operator scorecard: ingest a week of inference logs, join to AIS positions, show where the model drifted and what that drift cost in late arrivals or extra fuel. Hires year one: one ML engineer (geospatial + time-series) + part-time maritime ops advisor. Make-or-break: vendors/operators stream live inference telemetry and treat AIS-derived error as a paid operational scorecard. Kill if partners refuse to share logs, only buy a consultancy report, or say generic MLOps covers them. Expand to fuel/routing models year one, then naval IR/USV perception via a cleared partner.

**Segments:**
1. Maritime AI vendors (ETA, routing, collision-avoidance) — B2B direct via classification societies and maritime tech conferences, phase 1
2. Digital/fleet-performance teams at mid-size liner, tanker, dry-bulk operators — phase 1–2
3. Port authorities and vessel-traffic services — phase 2
4. Allied naval fleet commands and USV programs auditing IR/perception models — cleared partner, phase 3

**Watch for:** vendors/fleets withhold logs; generic MLOps firms add checks faster; naval procurement blocks access; scorecards show no useful performance differences.

## 02 Market & competitors
- Grand View Research maritime AI market: https://www.grandviewresearch.com/industry-analysis/maritime-artificial-intelligence-market-report
- Competitors (6):

| Player | Prox | Stage | What they do |
|---|---|---|---|
| Windward Maritime AI / Predicted ETA | 7/10 | Growth | Predicted ETA + ocean-freight visibility from AIS, carrier sites, weather. Operational intelligence, not an independent auditor. https://windward.ai/solution-2/ |
| PortXchange ETAPredictor | 7/10 | Growth | Continuously recalculates vessel ETAs; arrival planning for ports and inland operators. https://port-xchange.com/etapredictor/ |
| WHIZTEC Predictive ETA | 6/10 | Growth | ML + carrier/port history + AIS to predict shipment arrival, flag exceptions. https://www.whiztec.com/ai/predictive-eta/ |
| Broadpath Logistics | 6/10 | Startup | Ocean/air/rail tracking, predictive ETAs, route-risk scoring. https://broadpath.app/product/ |
| Kairon | 5/10 | Startup | Public AIS for just-in-time speed recommendations, auditable speed logs. https://www.kairon-system.com/ |
| WUT-TrajData | 4/10 | Adjacent | AIS-based benchmark/dataset for trajectory-prediction evaluation. https://github.com/MAPGroup/WUT-TrajData |

## 03 Founder profile
- Fit: production ML evaluation + selling software to cautious maritime buyers; or maritime software background + geospatial ML hire. Founder-fit difficulty 6/10.
- Vehicle: highly automatable, all-digital SaaS; public AIS + vendor logs; no wet lab/classified facility. Naval IR later via cleared partner.
- Execution: $220K capital, 2–5 team, 4 headcount year 1, 5 mo to market, boldness 4/10 (incremental), AI-runnable 8/10.

## 04 Lineage & sources
- **Seed:** "Continuous IR model performance dashboard for fleet-wide consistency auditing" (idea 740400)
- **Sibling:** "Real-time AI performance dashboard for maritime ops" (idea 3481476)
- **Cluster note:** merged naval IR fleet-consistency dashboard + generic AI performance-vs-self-assessment pitch into one maritime model auditor — same core value (condition-sliced live performance vs claimed maturity), commercial then naval.
- **Pack verdict:** ONE commercial-first maritime AI performance auditor (AIS trajectory scorecard → other onboard models → naval IR); studio_build; cluster size 3.
- **Scientific paper (2024):** "Ship infrared automatic target recognition via bipartite graph model-matching recommendation" (Academic Publisher)
- **Publishers in evidence:** Manila Times, Business Insider, RFI, The Register, Washington Post, ZDNET
- **Tags:** Software and data · Open · Sectors: AI Infrastructure, Defense Software, Industrial Software

## Product pivot (user directive)
The idea sells *audits of other vendors' models*. The user directs instead: **our model IS the product** — we build and ship the model + platform directly as an open-source product ("our model works okay"). So the product is an open-source maritime voyage-intelligence platform that provides:
- its own AIS-grounded voyage/ETA model served via API,
- performance decomposition by weather, sea region, ship type,
- drift monitoring + alerts,
- research-grade reports and dashboards (map, 3D globe, charts),
built entirely on open-source data (NOAA/MarineCadastre AIS, Open-Meteo weather, UN/LOCODE ports).
