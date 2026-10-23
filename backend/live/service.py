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

from . import analytics, kinematics, sources

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
REPORTS = ROOT / "reports"
ART = ROOT / "data" / "processed"

router = APIRouter(prefix="/v2", tags=["live & analytics"])


def _load(name: str):
    p = MODELS / name
    if not p.exists():
        return None
    with p.open("rb") as f:
        return pickle.load(f)


from functools import lru_cache  # noqa: E402


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
def overlay_mpas():
    return {"source": "Marine Regions WFS (CC BY 4.0)", "mpas": sources.marine_regions_mpas()}


@router.get("/live/overlays/biodiversity")
def overlay_bio(lat: float, lon: float):
    return {"obis": sources.obis_occurrences(lat, lon), "gbif": sources.gbif_occurrences(lat, lon),
            "attribution": "OBIS · GBIF (open occurrence data)"}


@router.get("/live/bathymetry")
def bathymetry(voyage_id: str | None = None, lat: float | None = None, lon: float | None = None):
    """Depth profile along a historical voyage or at a point (ERDDAP etopo180)."""
    df = _hist()
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
    return {"algorithm": algorithm, **r,
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
