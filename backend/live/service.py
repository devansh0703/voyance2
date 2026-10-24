"""Voyance II live & analytics router — mounted into the FastAPI app.

Serves: live AIS (Digitraffic), EKF/UKF tracking, collision watch (DCPA/TCPA +
Goodwin-Stanton + fuzzy CRI), weather overlays (Open-Meteo/NWS/NDBC), bathymetry
profiles, earthquakes, MPAs, biodiversity, H3 density, HDBSCAN anchorages with
M/M/c queue stats, A*/Dijkstra routing, fuel/CO2, port-name record linkage,
anomaly scoring with a trained ensemble, and a data-quality health strip.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from functools import lru_cache  # noqa: E402

from . import ai, algo2, analytics, kinematics, sources, sources2

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
CATEGORICAL = ["vessel_type_group", "region", "arr_port_idx", "dep_port_idx"]
REPORTS = ROOT / "reports"
ART = ROOT / "data" / "processed"

router = APIRouter(prefix="/v2", tags=["live & analytics"])


@lru_cache(maxsize=1)
def _all_months():
    frames = []
    for m in ("2024-01", "2024-04", "2024-07"):
        f = ROOT / "data" / "interim" / f"features-{m}.parquet"
        if f.exists():
            frames.append(pd.read_parquet(f))
    if not frames:
        return None
    allm = pd.concat(frames, ignore_index=True)
    return allm[allm["vessel_type_group"].isin(["cargo", "tanker", "passenger"])]


def _load(name: str):
    p = MODELS / name
    if not p.exists():
        return None
    with p.open("rb") as f:
        return pickle.load(f)


def _load_cat_levels() -> dict[str, list[str]]:
    p = MODELS / "categoricals.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _load_type_speeds() -> dict[str, float]:
    p = MODELS / "type_speeds.json"
    return json.loads(p.read_text()) if p.exists() else {}



@lru_cache(maxsize=1)
def _hist():
    f = ROOT / "data" / "interim" / "samples-2024-07.parquet"
    if not f.exists():
        return None
    df = pd.read_parquet(f)
    return df[df["vessel_type_group"].isin(["cargo", "tanker", "passenger"])]


# ---------- live vessels + tracking ----------

@router.get("/live/vessels")
def live_vessels(limit: int = 250):
    v = sources.digitraffic_vessels(limit)
    meta = sources.digitraffic_vessel_metadata()
    for x in v:
        m = meta.get(x["mmsi"], {})
        x["name"] = m.get("name")
        x["ship_type"] = m.get("shipType")
        x["destination"] = m.get("destination")
        x["draught"] = m.get("draught")
    return {"count": len(v), "source": "Digitraffic Finland Marine AIS (CC BY 4.0)",
            "fetched_utc": pd.Timestamp.utcnow().isoformat(), "vessels": v}


@router.get("/live/track/{mmsi}")
def live_track(mmsi: int, points: int = 40):
    """EKF + UKF smoothed live track for one vessel (Digitraffic track endpoints)."""
    try:
        r = sources._get(
            f"https://meri.digitraffic.fi/api/ais/v1/locations?mmsi={mmsi}", timeout=15
        ).json()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"upstream error: {e}")
    feats = r.get("features", [])[-points:]
    lats, lons, dts = [], [], []
    for f in feats:
        c = f["geometry"]["coordinates"]
        lats.append(c[1]); lons.append(c[0])
        dts.append(f["properties"]["timestampExternal"] / 1000.0)
    if len(lats) < 2:
        return {"mmsi": mmsi, "points": len(lats), "track": []}
    ekf = kinematics.ekf_track(lats, lons, dts)
    ukf = kinematics.ukf_track(lats, lons, dts)
    raw = list(zip(lats, lons))
    return {
        "mmsi": mmsi, "points": len(raw),
        "raw": [[round(a, 5), round(b, 5)] for a, b in raw],
        "ekf": [[round(a, 5), round(b, 5)] for a, b in ekf],
        "ukf": [[round(a, 5), round(b, 5)] for a, b in ukf],
        "simplified_douglas_peucker": [[round(a, 5), round(b, 5)]
                                       for a, b in kinematics.douglas_peucker(raw, 0.002)],
        "spline": [[round(a, 5), round(b, 5)] for a, b in kinematics.spline_smooth(
            [p[0] for p in raw], [p[1] for p in raw], n=60)],
        "frechet_ekf_vs_raw_nm": round(kinematics.frechet_distance(
            [[a, b] for a, b in ekf], [[a, b] for a, b in raw]) * 60.0, 4),
    }


# ---------- collision watch ----------

@router.get("/live/collision")
def collision_watch(top: int = 12):
    """Fuzzy-CRI ranked encounter table for live vessels."""
    v = sources.digitraffic_vessels(120)
    if len(v) < 2:
        return {"pairs": []}
    out = []
    for i in range(min(len(v), 60)):
        for j in range(i + 1, min(len(v), 60)):
            a, b = v[i], v[j]
            if a.get("sog") is None or b.get("sog") is None:
                continue
            d = kinematics.haversine_nm_arr(a["lat"], a["lon"], b["lat"], b["lon"])
            if d[0] > 15:
                continue
            dcpa, tcpa = kinematics.dcpa_tcpa(
                a["lat"], a["lon"], a.get("cog") or 0, float(a["sog"]),
                b["lat"], b["lon"], b.get("cog") or 0, float(b["sog"]))
            cri = kinematics.fuzzy_cri(dcpa, tcpa, float(a["sog"]))
            out.append({
                "mmsi_a": a["mmsi"], "mmsi_b": b["mmsi"],
                "distance_nm": round(float(d[0]), 2),
                "dcpa_nm": round(dcpa, 2), "tcpa_min": round(tcpa, 1) if tcpa else None,
                "cri": round(cri, 3),
                "domain_intrusion": bool(kinematics.in_goodwin_stanton(
                    dcpa, 0.0, float(a["sog"]))),
            })
    out.sort(key=lambda x: -x["cri"])
    return {"pairs": out[:top], "model": "DCPA/TCPA + Goodwin-Stanton domain + fuzzy CRI"}


# ---------- weather overlays ----------

@router.get("/live/weather")
def live_weather(lat: float, lon: float):
    return {
        "open_meteo_current": sources.open_meteo_forecast(lat, lon),
        "open_meteo_marine": sources.open_meteo_marine(lat, lon),
        "nws": sources.nws_point_forecast(lat, lon),
        "ndbc_buoys": sources.ndbc_all(),
        "attribution": "Open-Meteo (CC BY 4.0) · NOAA NWS · NOAA NDBC",
    }


# ---------- overlay chips ----------

@router.get("/live/overlays/quakes")
def overlay_quakes():
    return {"source": "USGS Earthquake Hazards Program (public domain)",
            "features": sources.usgs_quakes(day=True)}


@router.get("/live/overlays/mpas")
def overlay_mpas(south: float = 58.0, west: float = 14.0, north: float = 66.0, east: float = 31.0):
    fc = sources.marine_regions_mpas(south, west, north, east)
    return {"source": "Marine Regions WFS (CC BY 4.0)", "count": len(fc.get("features", [])),
            "feature_collection": fc}


@router.get("/live/overlays/biodiversity")
def overlay_bio(lat: float, lon: float):
    return {"obis": sources.obis_occurrences(lat, lon), "gbif": sources.gbif_occurrences(lat, lon),
            "attribution": "OBIS · GBIF (open occurrence data)"}


@router.get("/live/sar")
def live_sar(lat: float = 60.1, lon: float = 24.9):
    return {"source": "Sentinel-1 GRD via Copernicus Data Space OData catalog "
                      "(metadata keyless; imagery needs free CDSE registration)",
            "granules": sources2.sar_granules(lat, lon)}


@router.get("/live/bathymetry")
def bathymetry(voyage_id: str | None = None, lat: float | None = None, lon: float | None = None):
    """Depth profile along a historical voyage or at a point (OpenTopoData ETOPO1)."""
    df = _all_months()
    if df is None:
        raise HTTPException(503, "historical samples missing — run make data")
    if voyage_id:
        s = df[df["voyage_id"] == voyage_id].sort_values("ts")
        if s.empty:
            raise HTTPException(404, "voyage not found")
        lats, lons = s["lat"].tolist(), s["lon"].tolist()
    elif lat is not None and lon is not None:
        lats, lons = [lat - 0.5, lat, lat + 0.5], [lon - 0.5, lon, lon + 0.5]
    else:
        raise HTTPException(400, "voyage_id or lat+lon required")
    depths = sources.bathy_depths(lats, lons)
    return {"source": "EMODnet 2018 bathymetry via OpenTopoData (CC BY 4.0)",
            "profile": [{"lat": round(a, 3), "lon": round(b, 3), "depth_m": d}
                        for a, b, d in zip(lats, lons, depths)]}


# ---------- historical analytics ----------

@router.get("/analytics/h3")
def analytics_h3(resolution: int = Query(4, ge=1, le=7)):
    df = _hist()
    if df is None:
        raise HTTPException(503, "historical samples missing")
    return {"resolution": resolution,
            "hexes": analytics.h3_hexbin(df["lat"].to_numpy(), df["lon"].to_numpy(), resolution)}


@router.get("/analytics/anchorages")
def analytics_anchorages():
    df = _hist()
    if df is None:
        raise HTTPException(503, "historical samples missing")
    slow = df[df["sog"] < 1.0]
    r = analytics.hdbscan_anchorages(slow["lat"].to_numpy(), slow["lon"].to_numpy())
    # Little's Law + M/M/c per top anchorage (occupancy as arrival proxy)
    for c in r["clusters"][:10]:
        lam = c["occupancy"] / (24 * 7)     # observed arrivals per hour over the week
        c["queue_mmc"] = analytics.mmc_metrics(max(lam, 0.01), 1 / 2.5, servers=2)
        c["queue_littles_L"] = analytics.littles_law(max(lam, 0.01), 2.5)
    return {"model": "HDBSCAN spatial clustering · Little's Law (L=λW) · M/M/c Erlang-C",
            "anchorages": r["clusters"], "noise_points": r["noise"]}


@router.get("/analytics/route")
def analytics_route(src: int, dst: int, algorithm: str = "astar"):
    G = _load("maritime_graph.pkl")
    if G is None:
        raise HTTPException(503, "graph missing — run pipeline/precompute_v2.py")
    try:
        r = analytics.shortest_route(G, src, dst, algorithm)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    coords = [[round(float(G.nodes[n]["lat"]), 4), round(float(G.nodes[n]["lon"]), 4)]
              for n in r["path"] if n in G.nodes]
    return {"algorithm": algorithm, **r, "path_coords": coords,
            "model": "Dijkstra/A* on great-circle maritime graph (networkx)"}


@router.get("/analytics/fuel")
def analytics_fuel(sog_kn: float = 12.0, wave_height_m: float = 1.0,
                   vessel_length_m: float = 180.0, dwt_t: float = 50000.0,
                   distance_nm: float = 500.0, fuel_type: str = "vlsfo"):
    f = analytics.fuel_consumption_t_per_day(sog_kn, wave_height_m, vessel_length_m, dwt_t)
    days = distance_nm / max(sog_kn * 24, 1)
    voyage_fuel = f["fuel_t_per_day"] * days
    co2 = analytics.co2_emissions(voyage_fuel, fuel_type)
    return {"voyage_days": round(days, 2), **f, "voyage_fuel_t": round(voyage_fuel, 2),
            **co2, "models": "ITTC-1978 Cf · Townsin-Glover added resistance · IMO C factors"}


@router.get("/analytics/linkage")
def analytics_linkage(query: str, limit: int = 8):
    """Probabilistic port-name record linkage: Levenshtein + Jaro-Winkler."""
    f = ART / "ports-clustered.csv"
    if not f.exists():
        raise HTTPException(503, "ports table missing — run pipeline/precompute_v2.py")
    ports = pd.read_csv(f)
    scored = []
    for _, r in ports.iterrows():
        sim = kinematics.name_similarity(query, str(r["name"]))
        scored.append({"unlocode": r["unlocode"], "name": r["name"], **sim,
                       "lat": r["lat"], "lon": r["lon"]})
    scored.sort(key=lambda x: -x["jaro_winkler"])
    return {"query": query, "model": "Levenshtein ratio + Jaro-Winkler (rapidfuzz)",
            "matches": scored[:limit]}


@router.get("/analytics/anomaly")
def analytics_anomaly(lat: float, lon: float, sog: float, remaining_distance_nm: float):
    ens = _load("anomaly_ensemble.pkl")
    if ens is None:
        raise HTTPException(503, "ensemble missing — run pipeline/train_v2.py")
    return {"input": {"lat": lat, "lon": lon, "sog": sog, "remaining_distance_nm": remaining_distance_nm},
            "scores": analytics.score_anomaly(ens, lat, lon, sog, remaining_distance_nm)}


@router.get("/analytics/hmm")
def analytics_hmm(sog_series: str):
    """Decode voyage regime states (HMM) for a comma-separated SOG series."""
    m = _load("hmm_sog.pkl")
    if m is None:
        raise HTTPException(503, "HMM missing — run pipeline/train_v2.py")
    series = [float(x) for x in sog_series.split(",")]
    states = analytics.hmm_states(m, series)
    means = m.means_.flatten().tolist()
    labels = sorted(range(len(means)), key=lambda i: means[i])
    names = {labels[0]: "drift", labels[-1]: "transit"}
    if len(labels) == 3:
        names[labels[1]] = "maneuver"
    return {"states": states, "state_names": [names.get(s, f"state{s}") for s in states],
            "state_means_kn": [round(x, 2) for x in means],
            "transition_matrix": analytics.markov_transition_matrix(states[:-1], states[1:])}


# ---------- data-quality health strip ----------

@router.get("/health-quality")
def health_quality():
    df = _hist()
    checks = {}
    if df is not None:
        sog = df["sog"].to_numpy()
        checks["sog_iqr_pass_fraction"] = round(float(np.nanmean(kinematics.iqr_filter_mask(sog))), 3)
        checks["speed_outliers_z3"] = len(kinematics.zscore_outliers(sog))
        checks["rows"] = int(len(df))
        checks["nan_fraction"] = round(float(df[["lat", "lon", "sog", "remaining_distance_nm"]]
                                              .isna().mean().mean()), 5)
    checks["upstreams"] = {
        "digitraffic_ais": bool(sources.digitraffic_vessels(3)),
        "open_meteo": bool(sources.open_meteo_forecast(60.15, 24.95)),
    }
    return {"probe": "z-score + IQR + NaN audit on live sample store + upstream reachability",
            "checks": checks, "generated_utc": pd.Timestamp.utcnow().isoformat()}


# ---------- second-wave sources ----------

@router.get("/live/dma")
def live_dma():
    return {"source": "Danish Maritime Authority open AIS", "vessels": sources2.dma_ais_vessels()}


@router.get("/live/argo")
def live_argo():
    return {"source": "Argo floats via ERDDAP (open data)", "floats": sources2.argo_floats()}


@router.get("/live/water")
def live_water(state: str = "fl"):
    return {"source": "USGS Water Services instantaneous values (public domain)",
            "stations": sources2.usgs_water_stations(state)}


@router.get("/live/harbors")
def live_harbors(south: float = 59.5, west: float = 22.0, north: float = 60.8, east: float = 28.5):
    return {"source": "OpenStreetMap Overpass (ODbL)", "harbors": sources2.overpass_harbors(south, west, north, east)}


@router.get("/live/radar")
def live_radar():
    return {"source": "RainViewer public radar (keyless)", **sources2.rainviewer_frames()}


@router.get("/live/wpi")
def live_wpi():
    return {"source": "World Port Index (NGA) community mirror (public domain)",
            "ports": sources2.wpi_ports()}


@router.get("/live/geology")
def live_geology(west: float = 22.0, south: float = 59.0, east: float = 30.0, north: float = 61.5):
    return {"source": "EMODnet Geology WFS seabed substrate (CC BY 4.0)",
            "subsets": sources2.emodnet_geology(west, south, east, north)}


@router.get("/live/naturalearth")
def live_naturalearth():
    gj = sources2.natural_earth_coastline()
    return {"source": "Natural Earth (public domain)", "features": len(gj.get("features", []))}


# ---------- second-wave analytics ----------

@router.get("/analytics/gaps")
def analytics_gaps(limit: int = 12):
    """AIS signal drop-out gap analysis per historical voyage."""
    df = _hist()
    if df is None:
        raise HTTPException(503, "historical samples missing")
    out = []
    for vid, g in list(df.groupby("voyage_id"))[:limit]:
        ts = pd.to_datetime(g["ts"], utc=True).astype("int64").tolist()
        out.append({"voyage_id": vid, **algo2.gap_analysis(ts)})
    return {"threshold_min": 30.0, "voyages": out,
            "model": "temporal sequence gap analysis (drop-out indicator source)"}


@router.get("/analytics/fsm")
def analytics_fsm(sog_series: str):
    series = [float(x) for x in sog_series.split(",")]
    return {"model": "rule-based finite state machine + SOG threshold bands",
            "sequence": algo2.fsm_sequence(series)}


@router.get("/analytics/sog-histogram")
def analytics_sog_histogram():
    df = _hist()
    if df is None:
        raise HTTPException(503, "historical samples missing")
    sog = df["sog"].dropna().to_numpy()
    bands = {}
    for v in sog:
        b = algo2.sog_threshold_band(float(v))
        bands[b] = bands.get(b, 0) + 1
    hist, edges = np.histogram(sog, bins=40, range=(0, 25))
    return {"histogram": [{"bin_lo": round(float(edges[i]), 2),
                           "bin_hi": round(float(edges[i + 1]), 2), "n": int(hist[i])}
                          for i in range(len(hist)) if hist[i] > 0],
            "threshold_bands": bands,
            "model": "SOG distribution thresholding (behavioral bands)"}


@router.get("/analytics/linkage2")
def analytics_linkage2(query: str, lat: float | None = None, lon: float | None = None):
    from pathlib import Path as P
    f = P(__file__).resolve().parents[2] / "data" / "processed" / "ports-clustered.csv"
    if not f.exists():
        raise HTTPException(503, "ports table missing")
    ports = pd.read_csv(f)
    candidates = ports.head(3000).to_dict("records")
    return {"query": query, "model": "probabilistic record linkage (Fellegi-Sunter style)",
            "matches": algo2.probabilistic_linkage(query, candidates, lat, lon)[:8]}


@router.get("/analytics/mmsi-imo")
def analytics_mmsi_imo():
    v = sources.digitraffic_vessels(200)
    meta = sources.digitraffic_vessel_metadata()
    enriched = [{**x, "imo": (meta.get(x["mmsi"]) or {}).get("imo")} for x in v]
    return {"model": "MMSI/IMO lookup table hashing", **algo2.mmsi_imo_hash(enriched)}


@router.get("/analytics/dwt-fit")
def analytics_dwt_fit():
    df = _hist()
    if df is None:
        raise HTTPException(503, "historical samples missing")
    d = df.dropna(subset=["vessel_length", "vessel_draft"])
    d = d[d["vessel_length"] > 10]
    fit = algo2.fit_dwt_powerlaw(d["vessel_length"].to_numpy(),
                                 (d["vessel_draft"] * d["vessel_length"]).to_numpy() / 3.0)
    return {"model": "deadweight tonnage power-law scaling (log-log fit on AIS length/draft proxy)",
            **fit}


@router.get("/analytics/dbscan-temporal")
def analytics_dbscan_temporal(eps_min: float = 240.0, min_samples: int = 10):
    df = _hist()
    if df is None:
        raise HTTPException(503, "historical samples missing")
    slow = df[df["sog"] < 1.0]
    ts = pd.to_datetime(slow["ts"], utc=True).astype("int64").to_numpy() // 10**6  # ms
    r = algo2.dbscan_temporal(slow["lat"].to_numpy(), slow["lon"].to_numpy(), ts,
                              eps_min=eps_min, min_samples=min_samples)
    return {"model": "DBSCAN temporal density clustering (sklearn) — time-scaled eps",
            **r}


@router.get("/analytics/buffer-intersect")
def analytics_buffer_intersect(lat: float, lon: float, sog_kn: float = 12.0,
                               minutes: float = 30.0):
    """Dynamic sog-scaled buffer around a predicted position intersected with
    MPA polygons (Shapely polygon intersection queries)."""
    from shapely.geometry import shape
    fc = sources.marine_regions_mpas(lat - 5, lon - 5, lat + 5, lon + 10)
    polys = []
    for f in fc.get("features", []):
        try:
            polys.append({"name": (f.get("properties") or {}).get("name"),
                          "geom": shape(f.get("geometry"))})
        except Exception:  # noqa: BLE001
            continue
    radius_deg = (sog_kn * minutes / 60.0) / 60.0
    hits = []
    for p in polys:
        buf = shape({"type": "Polygon",
                     "coordinates": [[(lon + radius_deg * math.cos(math.radians(a)),
                                       lat + radius_deg * math.sin(math.radians(a)))
                                      for a in range(0, 361, 20)]]})
        if buf.intersects(p["geom"]):
            hits.append({"name": p["name"], "buffer_radius_deg": round(radius_deg, 3)})
    return {"model": "dynamic spatial buffer intersecting + Shapely polygon intersection",
            "buffer_radius_deg": round(radius_deg, 3), "mpas_scanned": len(polys),
            "hits": hits}


@router.get("/analytics/bilinear-depth")
def analytics_bilinear_depth(lat: float, lon: float):
    """True bilinear interpolation over a fetched EMODnet depth grid (3×3 cells)."""
    la0, lo0 = math.floor(lat), math.floor(lon)
    glats = [la0 - 1 + i for i in range(3)]
    glons = [lo0 - 1 + i for i in range(3)]
    lats, lons = [], []
    for a in glats:
        for b in glons:
            lats.append(a + 0.5)
            lons.append(b + 0.5)
    depths = sources.bathy_depths(lats, lons)
    V = [depths[i * 3:(i + 1) * 3] for i in range(3)]
    if any(v is None for row in V for v in row):
        return {"available": False, "reason": "OpenTopoData cell(s) missing"}
    v = algo2.bilinear_interp_grid([lat], [lon], glats, glons, V)[0]
    return {"available": True, "model": "bilinear interpolation over 3×3 ETOPO1 grid",
            "grid_lats": glats, "grid_lons": glons, "grid_depths": V,
            "bilinear_depth_m": round(float(v), 2)}


import math  # noqa: E402


@router.get("/analytics/darkvessels")
def analytics_darkvessels(limit: int = 40):
    """Dark-vessel candidates: last-known positions before AIS drop-outs."""
    df = _hist()
    if df is None:
        raise HTTPException(503, "historical samples missing")
    markers = []
    for vid, g in list(df.groupby("voyage_id"))[: limit * 3]:
        gg = g.sort_values("ts")
        ts = (pd.to_datetime(gg["ts"], utc=True).astype("int64") // 10**6).to_numpy()  # ns→ms
        gaps = algo2.gap_analysis(ts, gap_threshold_min=45.0)
        for gap in gaps["gaps"]:
            after = gg[g["ts"] > pd.Timestamp(gap["to_ts"], tz="UTC")]
            if after.empty:
                continue
            row = after.iloc[0]
            markers.append({"voyage_id": vid, "lat": float(row["lat"]), "lon": float(row["lon"]),
                            "gap_min": gap["gap_min"], "sog": float(row["sog"] or 0),
                            "type": str(row["vessel_type_group"])})
            if len(markers) >= limit:
                break
        if len(markers) >= limit:
            break
    markers.sort(key=lambda m: -m["gap_min"])
    return {"model": "dark-vessel candidates = first position after AIS drop-out ≥ 45 min",
            "markers": markers}


@router.get("/analytics/replay/{voyage_id}")
def analytics_replay(voyage_id: str):
    """Historical track replay bundle: coords, SOG series, gaps, FSM states, fuel series."""
    df = _hist()
    if df is None:
        raise HTTPException(503, "historical samples missing")
    try:  # fall back across all months so any exported voyage id replays
        extra = [pd.read_parquet(ROOT / "data" / "interim" / f"features-{m}.parquet")
                 for m in ("2024-01", "2024-04")]
        for ex in extra:
            ex = ex[ex["vessel_type_group"].isin(["cargo", "tanker", "passenger"])]
            if voyage_id in set(ex["voyage_id"]):
                df = pd.concat([df, ex], ignore_index=True)
                break
    except Exception:  # noqa: BLE001
        pass
    s = df[df["voyage_id"] == voyage_id].sort_values("ts")
    if s.empty:
        raise HTTPException(404, "voyage not found")
    sog = s["sog"].fillna(0).tolist()
    ts = (pd.to_datetime(s["ts"], utc=True).astype("int64") // 10**6).tolist()  # ns→ms
    gaps = algo2.gap_analysis(ts)
    smoothed = algo2.bidirectional_smooth(sog)
    fuel_pts = []
    for la, lo, v, wd in zip(s["lat"], s["lon"], sog, [0.8] * len(sog)):
        f = analytics.fuel_consumption_t_per_day(max(v, 1), wd, float(s["vessel_length"].iloc[0] or 180), 50000)
        fuel_pts.append(round(f["fuel_t_per_day"], 2))
    return {"voyage_id": voyage_id,
            "coords": [[round(float(b), 4), round(float(a), 4)] for a, b in zip(s["lat"], s["lon"])],
            "sog": [round(float(x), 2) for x in sog],
            "sog_smoothed": [round(float(x), 2) for x in smoothed],
            "ts": ts, "gaps": gaps, "fsm": algo2.fsm_sequence(sog),
            "fuel_series_t_day": fuel_pts,
            "carbon_badge": analytics.co2_emissions(sum(fuel_pts) * (gaps["coverage"] or 1) * 24 / 24)["co2_t"]}


# ---------- wave field grid + wind barbs (Open-Meteo marine grid) ----------

@router.get("/live/wavefield")
def wavefield(lat: float = 59.5, lon: float = 21.0, step: float = 1.0, n: int = 4):
    """n×n marine grid around a point: wave height + wind vectors for field overlays."""
    cells = []
    for i in range(n):
        for j in range(n):
            la = lat + i * step
            lo = lon + j * step
            m = sources.open_meteo_marine(la, lo)
            w = sources.open_meteo_forecast(la, lo)
            cells.append({"lat": round(la, 2), "lng": round(lo, 2),
                          "wave_height": m.get("wave_height"),
                          "wave_period": m.get("wave_period"),
                          "wind_kn": w.get("wind_speed_10m"),
                          "wind_dir_deg": w.get("wind_direction_10m")})
    return {"grid": cells, "n": n, "step_deg": step,
            "attribution": "Open-Meteo marine+forecast (CC BY 4.0)"}


# ---------- API usage dashboard counters ----------

_usage: dict[str, int] = {"requests": 0, "predict": 0, "live": 0, "analytics": 0}


@router.get("/usage")
def usage():
    return {"counters": _usage, "note": "in-process counters since last restart"}


@router.get("/live/datasets")
def datasets_status():
    """Downloadable dataset registry + availability (drives progress modal)."""
    import os
    raw = ROOT / "data" / "raw"
    items = []
    for name, label in [
        ("unlocode.csv", "UN/LOCODE code list"),
        ("ais-track-2024-01.parquet", "NOAA AIS tracks 2024-01"),
        ("ais-track-2024-04.parquet", "NOAA AIS tracks 2024-04"),
        ("ais-track-2024-07.parquet", "NOAA AIS tracks 2024-07"),
        ("ais-2024-01-08.parquet", "NOAA AIS points 2024-01-08"),
        ("ais-2024-04-08.parquet", "NOAA AIS points 2024-04-08"),
        ("ais-2024-07-08.parquet", "NOAA AIS points 2024-07-08"),
    ]:
        f = raw / name
        items.append({"file": name, "label": label,
                      "present": f.exists(),
                      "size_mb": round(f.stat().st_size / 1e6, 1) if f.exists() else 0})
    return {"datasets": items, "note": "raw archive data is re-downloadable via make data"}


# ---------- prediction surface: GeoJSON route + drift cone + analogs ----------

@router.get("/predict/route/{voyage_id}")
def predict_route(voyage_id: str):
    """Full prediction GeoJSON for a voyage: actual track, remaining great-circle leg,
    drift cone from P10/P50/P90 spread, ETA markers. OSM-ready."""
    df = _hist()
    if df is None:
        raise HTTPException(503, "historical samples missing")
    try:
        ex = [pd.read_parquet(ROOT / "data" / "interim" / f"features-{m}.parquet")
              for m in ("2024-01", "2024-04", "2024-07")]
        allm = pd.concat(ex, ignore_index=True)
        allm = allm[allm["vessel_type_group"].isin(["cargo", "tanker", "passenger"])]
    except Exception:  # noqa: BLE001
        allm = df
    s = allm[allm["voyage_id"] == voyage_id].sort_values("ts")
    if s.empty:
        raise HTTPException(404, "voyage not found in feature store")
    import xgboost as xgb

    def _xgb(name):
        m = xgb.XGBRegressor(enable_categorical=True)
        m.load_model(str(MODELS / name))
        return m
    q, m10, m90 = _xgb("eta-p50.json"), _xgb("eta-p10.json"), _xgb("eta-p90.json")
    feats = ["lat", "lon", "remaining_distance_nm", "speed_kn", "sog_median_6h",
             "distance_traveled_nm", "elapsed_h", "wind_speed_10m", "wind_gusts_10m",
             "precipitation", "temperature_2m", "relative_humidity_2m",
             "wave_height", "wave_period", "swell_wave_height",
             "cos_wave_dir", "sin_wave_dir", "month_sin", "month_cos",
             "hour_sin", "hour_cos", "vessel_length", "vessel_draft",
             "hours_at_current_speed", "hours_at_type_speed", "hours_at_sog6",
             "vessel_type_group", "region", "arr_port_idx", "dep_port_idx"]
    X = s.copy()
    X["speed_kn"] = X["sog"]
    if "wave_direction" in X:
        wd = np.deg2rad(X["wave_direction"])
        X["cos_wave_dir"], X["sin_wave_dir"] = np.cos(wd), np.sin(wd)
    else:
        X["cos_wave_dir"] = X["sin_wave_dir"] = 0.0
    ts_dt = pd.to_datetime(X["ts"], utc=True)
    X["month"] = ts_dt.dt.month
    X["hour"] = ts_dt.dt.hour
    X["month_sin"] = np.sin(2 * np.pi * X["month"] / 12)
    X["month_cos"] = np.cos(2 * np.pi * X["month"] / 12)
    X["hour_sin"] = np.sin(2 * np.pi * X["hour"] / 24)
    X["hour_cos"] = np.cos(2 * np.pi * X["hour"] / 24)
    X["hours_at_current_speed"] = X["remaining_distance_nm"] / X["sog"].clip(lower=1)
    type_speed = _load_type_speeds().get(str(X["vessel_type_group"].iloc[0]), 8.0)
    X["hours_at_type_speed"] = X["remaining_distance_nm"] / max(type_speed, 2.0)
    X["hours_at_sog6"] = X["remaining_distance_nm"] / X["sog_median_6h"].clip(lower=1)
    X = X[feats].copy()
    lv = _load_cat_levels()
    for c in CATEGORICAL:
        X[c] = pd.Categorical(X[c].astype(str), categories=lv[c])
    p10 = m10.predict(X) if m10 else None
    p50 = q.predict(X)
    p90 = m90.predict(X) if m90 else None
    coords = [[round(float(b), 4), round(float(a), 4)] for a, b in zip(s["lat"], s["lon"])]  # GeoJSON = [lon, lat]
    last = coords[-1]          # [lon, lat]
    import math as _m
    d_nm = float(s["remaining_distance_nm"].iloc[-1])
    brg = float(s["cog"].iloc[-1]) if "cog" in s and not pd.isna(s["cog"].iloc[-1]) else 45.0
    k = _m.pi / 180
    dest_lat = last[1] + (d_nm / 60.0) * _m.cos(brg * k)
    dest_lon = last[0] + (d_nm / 60.0) * _m.sin(brg * k) / max(_m.cos(last[1] * k), 0.2)
    drift_half_width_nm = max(float(np.mean((np.asarray(p90) - np.asarray(p10)) / 2)), 0.25) if p90 is not None else 6.0
    # drift cone polygon: from last point to destination, widening half-width
    # last = [lon, lat]; interpolate in true lat/lon, emit GeoJSON [lon, lat]
    steps = 12
    lon0, lat0 = last[0], last[1]
    right, left = [], []
    for i in range(steps + 1):
        t = i / steps
        la = lat0 + (dest_lat - lat0) * t
        lo = lon0 + (dest_lon - lon0) * t
        w = (drift_half_width_nm / 60.0) * (0.25 + 0.75 * t) * 0.5
        right.append([round(lo + w / max(_m.cos(la * k), 0.2), 4), round(la + w, 4)])
        left.append([round(lo - w / max(_m.cos(la * k), 0.2), 4), round(la - w, 4)])
    cone = right + list(reversed(left))
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"kind": "actual_track"},
             "geometry": {"type": "LineString", "coordinates": coords}},
            {"type": "Feature", "properties": {"kind": "remaining_leg"},
             "geometry": {"type": "LineString",
                          "coordinates": [last, [round(dest_lon, 4), round(dest_lat, 4)]]}},
            {"type": "Feature", "properties": {"kind": "drift_cone",
                                               "half_width_nm": round(drift_half_width_nm, 2)},
             "geometry": {"type": "Polygon", "coordinates": [[*cone, cone[0]]]}},
            {"type": "Feature", "properties": {"kind": "destination"},
             "geometry": {"type": "Point",
                          "coordinates": [round(dest_lon, 4), round(dest_lat, 4)]}},
            {"type": "Feature", "properties": {"kind": "current_position"},
             "geometry": {"type": "Point", "coordinates": last}},
        ],
    }
    return {
        "voyage_id": voyage_id, "geojson": fc,
        "eta": {"p10_h": round(float(p10[-1]), 2) if p10 is not None else None,
                "p50_h": round(float(p50[-1]), 2),
                "p90_h": round(float(p90[-1]), 2) if p90 is not None else None},
        "remaining_distance_nm": d_nm,
        "vessel_type_group": str(s["vessel_type_group"].iloc[0]),
        "samples": int(len(s)),
    }


@router.get("/predict/analogs/{voyage_id}")
def predict_analogs(voyage_id: str, limit: int = 3):
    """Historical analogs: real voyages with the same destination port and vessel-type
    group — the reference backing for AI explanations."""
    df = _hist()
    if df is None:
        raise HTTPException(503, "historical samples missing")
    try:
        ex = [pd.read_parquet(ROOT / "data" / "interim" / f"features-{m}.parquet")
              for m in ("2024-01", "2024-04")]
        allm = pd.concat([df] + ex, ignore_index=True)
        allm = allm[allm["vessel_type_group"].isin(["cargo", "tanker", "passenger"])]
    except Exception:  # noqa: BLE001
        allm = df
    base = allm[allm["voyage_id"] == voyage_id]
    if base.empty:
        raise HTTPException(404, "voyage not found")
    vtype = base["vessel_type_group"].iloc[0]
    dest = base["arr_port_idx"].iloc[0]
    sims = allm[(allm["arr_port_idx"] == dest) & (allm["vessel_type_group"] == vtype)
                & (allm["voyage_id"] != voyage_id)]
    out = []
    for vid, g in list(sims.groupby("voyage_id"))[:limit]:
        out.append({"voyage_id": vid, "duration_h": round(float((pd.to_datetime(g["arr_ts"]).max()
                    - pd.to_datetime(g["dep_ts"]).max()).total_seconds() / 3600), 1),
                    "distance_nm": round(float(g["remaining_distance_nm"].max()), 1),
                    "coords": [[round(float(b), 4), round(float(a), 4)]
                               for a, b in zip(g.sort_values("ts")["lat"], g.sort_values("ts")["lon"])][:80],
                    "vessel_type_group": vtype})
    return {"analogs": out, "basis": "same destination port + vessel type group, real AIS tracks"}


# ---------- AI explanation ----------

@router.get("/ai/providers")
def ai_providers():
    return {"chain": ai.providers_status(),
            "note": "first reachable provider serves; override with provider+model"}


@router.post("/ai/explain")
def ai_explain(body: dict):
    voyage_id = body.get("voyage_id")
    question = body.get("question") or (
        "Why will this route drift tomorrow for this ship type, and what should the fleet team expect?")
    provider = body.get("provider")
    model = body.get("model")
    if not voyage_id:
        raise HTTPException(400, "voyage_id required")

    allm = _all_months()
    if allm is None:
        raise HTTPException(503, "historical samples missing")
    s = allm[allm["voyage_id"] == voyage_id]
    if s.empty:
        raise HTTPException(404, "voyage not found")
    ev = REPORTS / "eval.json"
    evals = json.loads(ev.read_text()) if ev.exists() else {}
    imp = ", ".join(f["feature"] for f in evals.get("feature_importance", [])[:8])
    mae = evals.get("global", {}).get("p50", {}).get("mae_h")

    # weather forecast along the remaining leg (Open-Meteo, keyless)
    last = s.sort_values("ts").iloc[-1]
    wx = sources.open_meteo_forecast(float(last["lat"]), float(last["lon"]))
    marine = sources.open_meteo_marine(float(last["lat"]), float(last["lon"]))

    # historical analogs
    try:
        analogs = predict_analogs(voyage_id)["analogs"]
    except HTTPException:
        analogs = []

    ctx = json.dumps({
        "voyage": {"id": voyage_id,
                   "vessel_type": str(s["vessel_type_group"].iloc[0]),
                   "vessel_length_m": None if pd.isna(s["vessel_length"].iloc[0]) else float(s["vessel_length"].iloc[0]),
                   "remaining_distance_nm": round(float(s["remaining_distance_nm"].iloc[-1]), 1),
                   "speed_kn": round(float(s["sog"].iloc[-1] or 0), 1),
                   "region": str(s["region"].iloc[0]),
                   "month": str(pd.to_datetime(s['ts']).dt.month.iloc[0])},
        "live_weather_forecast": wx,
        "live_waves": marine,
        "model_performance": {"test_mae_h": mae,
                              "p10_p90_coverage": evals.get("coverage_p10_p90"),
                              "top_features": imp},
        "historical_analogs": [{"voyage_id": a["voyage_id"],
                                "duration_h": a["duration_h"],
                                "distance_nm": a["distance_nm"]} for a in analogs],
    }, indent=1, default=str)

    system = (
        "You are Voyance's maritime AI analyst. Answer ONLY from the JSON context provided. "
        "Structure the answer in parsed markdown with exactly these sections:"
        "\n\n## Headline\n(one sentence)"
        "\n\n## Why drift is expected\n(3-5 bullets citing concrete numbers from the context: wind, waves, vessel type, model error)"
        "\n\n## Reference backing\n(bullets, each naming a historical voyage_id from historical_analogs, "
        "its duration/distance, and the live weather values; reference the model's tested MAE)"
        "\n\n## What to watch\n(2-3 bullets)"
        "\n\nNever invent numbers not present in the context. Be concise.")
    user = "Question: " + question + "\n\nContext JSON:\n" + ctx

    result = ai.explain([{"role": "system", "content": system},
                         {"role": "user", "content": user}],
                        provider=provider, model=model)
    if not result["provider"]:
        raise HTTPException(503, json.dumps({"errors": result["errors"]}))
    return {**result,
            "voyage_id": voyage_id,
            "references": [{"voyage_id": a["voyage_id"],
                            "label": f"{a['vessel_type_group']} · {a['distance_nm']} nm · {a['duration_h']} h",
                            "replay_url": f"/analytics?voyage={a['voyage_id']}"}
                           for a in analogs],
            "context_snapshot": json.loads(ctx)}
