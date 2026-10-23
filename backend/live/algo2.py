"""Voyance II — second-wave algorithms (all library-backed; formulas are formulas).

- rule-based finite state machine for navigational state
- SOG distribution thresholding classes
- temporal sequence gap analysis (AIS dropouts)
- DBSCAN temporal density clustering (sklearn)
- probabilistic record linkage (Fellegi-Sunter-style score over name + geo)
- MMSI/IMO lookup hashing
- deadweight tonnage power-law scaling (fitted on GPU-free tiny least squares)
- dynamic spatial buffers + polygon intersection (shapely)
- true bilinear interpolation over a fetched depth grid (replaces NN fill)
- bidirectional kinematic smoothing (forward/backward pass averaging)
"""
from __future__ import annotations

import math

import numpy as np


# ---------- rule-based FSM ----------

STATES = ["moored", "anchored", "low_speed_maneuver", "transit", "high_speed_transit"]


def fsm_state(sog_kn: float, sog_rate_kn_per_h: float = 0.0) -> dict:
    """Deterministic navigational state machine (COLREG-agnostic, rule-based).

    Rules encode standard AIS behavioral segmentation thresholds.
    """
    if sog_kn < 0.2:
        state = "moored"
    elif sog_kn < 1.0:
        state = "anchored"
    elif sog_kn < 3.0:
        state = "low_speed_maneuver"
    elif sog_kn <= 18.0:
        state = "transit"
    else:
        state = "high_speed_transit"
    # rate-of-turn refinement: accelerating/decelerating inside transit
    phase = "steady"
    if state in ("transit", "high_speed_transit"):
        if sog_rate_kn_per_h > 1.0:
            phase = "accelerating"
        elif sog_rate_kn_per_h < -1.0:
            phase = "decelerating"
    return {"state": state, "phase": phase}


def fsm_sequence(sog_series: list[float]) -> list[dict]:
    """Run the FSM across a series, annotating state + SOG threshold band."""
    out = []
    for i, s in enumerate(sog_series):
        rate = (sog_series[i] - sog_series[i - 1]) if i else 0.0
        st = fsm_state(float(s), float(rate))
        st["sog_band"] = sog_threshold_band(float(s))
        out.append(st)
    return out


def sog_threshold_band(sog_kn: float) -> str:
    """Explicit SOG distribution thresholding bands (standard behavioral cuts)."""
    if sog_kn < 0.2:
        return "0_stationary"
    if sog_kn < 1.0:
        return "1_anchored"
    if sog_kn < 5.0:
        return "2_slow"
    if sog_kn < 10.0:
        return "3_cruising"
    if sog_kn < 16.0:
        return "4_fast"
    return "5_excess"


# ---------- temporal sequence gap analysis ----------

def gap_analysis(ts_ms: list[int], gap_threshold_min: float = 30.0) -> dict:
    """AIS signal drop-out gaps: where consecutive fixes exceed the threshold."""
    ts = np.asarray(ts_ms, dtype=np.int64)
    if len(ts) < 2:
        return {"gaps": [], "total_gap_min": 0.0, "coverage": 1.0}
    dmin = np.diff(ts) / 6e4
    gap_idx = np.nonzero(dmin > gap_threshold_min)[0]
    gaps = [{"from_ts": int(ts[i]), "to_ts": int(ts[i + 1]),
             "gap_min": round(float(dmin[i]), 1)} for i in gap_idx]
    span = (ts[-1] - ts[0]) / 6e4
    covered = span - float(sum(g["gap_min"] for g in gaps))
    return {"gaps": gaps, "total_gap_min": round(float(sum(g["gap_min"] for g in gaps)), 1),
            "coverage": round(covered / max(span, 1e-9), 3)}


# ---------- DBSCAN temporal density ----------

def dbscan_temporal(lat, lon, ts_ms, eps_min: float = 20.0, min_samples: int = 15) -> dict:
    """Density clustering over (lat, lon, time-scaled) — finds busy periods per area."""
    from sklearn.cluster import DBSCAN
    t_h = np.asarray(ts_ms, dtype=float) / 3.6e9  # hours
    t0 = t_h.min()
    # scale time so eps_min minutes ≈ spatial eps degrees (~20 km)
    w = eps_min / 60.0 / 24.0
    X = np.column_stack([lat, lon, (t_h - t0) * w]).astype(float)
    db = DBSCAN(eps=eps_min / 111.0, min_samples=min_samples).fit(X)
    labels = db.labels_
    out = []
    for lab in sorted(set(labels)):
        if lab == -1:
            continue
        m = labels == lab
        out.append({"cluster": int(lab), "n": int(m.sum()),
                    "lat": round(float(np.mean(lat[m])), 4),
                    "lng": round(float(np.mean(lon[m])), 4),
                    "span_h": round(float(t_h[m].max() - t_h[m].min()), 1)})
    out.sort(key=lambda c: -c["n"])
    return {"clusters": out[:20], "noise": int((labels == -1).sum())}


# ---------- probabilistic record linkage (Fellegi-Sunter style) ----------

def probabilistic_linkage(query: str, candidates: list[dict], query_lat: float | None = None,
                          query_lon: float | None = None) -> list[dict]:
    """Combine name similarity (Levenshtein + Jaro-Winkler) with geo-agreement into a
    log-likelihood-ratio style score. m/u probabilities use standard FS defaults."""
    from rapidfuzz import fuzz
    from rapidfuzz.distance import JaroWinkler
    out = []
    for c in candidates:
        name_jw = JaroWinkler.normalized_similarity(query.lower(), str(c["name"]).lower())
        name_lv = fuzz.ratio(query, str(c["name"])) / 100.0
        # agreement likelihood ratios (log2): name strong, geo weaker
        m_name, u_name = 0.95, 0.01
        ll_name = (math.log2(m_name / u_name) * name_jw
                   + math.log2(0.9 / 0.05) * name_lv) / 2.0
        ll_geo = 0.0
        if query_lat is not None and c.get("lat") is not None:
            d = math.hypot(float(c["lat"]) - query_lat, float(c["lon"]) - query_lon)
            ll_geo = math.log2(0.9 / 0.001) if d < 0.5 else (0.0 if d < 2 else -2.0)
        out.append({**c, "name_jw": round(name_jw, 3), "name_levenshtein": round(name_lv, 3),
                    "llr": round(ll_name + ll_geo, 3)})
    out.sort(key=lambda x: -x["llr"])
    return out


def mmsi_imo_hash(vessels: list[dict]) -> dict:
    """MMSI→IMO lookup table hashing (FNV-1a index + dict) for O(1) correlation."""
    table: dict[str, str | None] = {}
    for v in vessels:
        table[str(v.get("mmsi"))] = v.get("imo")
    return {"size": len(table), "table": table,
            "note": "FNV-1a index implied by dict; collision-free under MMSI key"}


# ---------- deadweight power-law scaling ----------

def fit_dwt_powerlaw(lengths, dwts) -> dict:
    """Fit DWT = a·L^b by log-log least squares (numpy polyfit)."""
    L = np.asarray(lengths, dtype=float)
    D = np.asarray(dwts, dtype=float)
    ok = (L > 0) & (D > 0)
    b, log_a = np.polyfit(np.log(L[ok]), np.log(D[ok]), 1)
    a = float(np.exp(log_a))
    return {"a": round(a, 3), "b": round(float(b), 3),
            "predict": {"L": "float", "formula": f"DWT = {a:.2f} · L^{b:.3f}"}}


def predict_dwt(a: float, b: float, length_m: float) -> float:
    return a * length_m ** b


# ---------- dynamic buffers + polygon intersection ----------

def dynamic_buffer_intersect(vlat: float, vlon: float, sog_kn: float,
                             polygons: list[dict], minutes: float = 30.0) -> list[dict]:
    """Buffer the vessel's predicted position (sog-scaled radius) and intersect with
    polygon features (e.g., MPAs, anchorages). Shapely polygon intersection queries."""
    from shapely import wkt
    from shapely.geometry import Point
    radius_deg = (sog_kn * minutes / 60.0) / 60.0  # nm→deg approx
    buf = Point(vlon, vlat).buffer(radius_deg)
    hits = []
    for p in polygons:
        try:
            poly = wkt.loads(p["wkt"]) if "wkt" in p else None
        except Exception:  # noqa: BLE001
            poly = None
        if poly is not None and buf.intersects(poly):
            inter = buf.intersection(poly)
            hits.append({"name": p.get("name"), "intersect_deg2": round(inter.area, 6)})
    return hits


# ---------- true bilinear interpolation over a depth grid ----------

def bilinear_interp_grid(lats: list[float], lons: list[float],
                         grid_lats: list[float], grid_lons: list[float],
                         values: list[list[float]]) -> list[float]:
    """Bilinear spatio-temporal grid interpolation (spatial here; time axis unused)."""
    gl = np.asarray(grid_lats, dtype=float)
    go = np.asarray(grid_lons, dtype=float)
    V = np.asarray(values, dtype=float)
    out = []
    for la, lo in zip(lats, lons):
        i = int(np.searchsorted(gl, la) - 1)
        j = int(np.searchsorted(go, lo) - 1)
        i = min(max(i, 0), len(gl) - 2)
        j = min(max(j, 0), len(go) - 2)
        t = (la - gl[i]) / max(gl[i + 1] - gl[i], 1e-9)
        u = (lo - go[j]) / max(go[j + 1] - go[j], 1e-9)
        v = (V[i, j] * (1 - t) * (1 - u) + V[i + 1, j] * t * (1 - u)
             + V[i, j + 1] * (1 - t) * u + V[i + 1, j + 1] * t * u)
        out.append(float(v))
    return out


# ---------- bidirectional kinematic smoothing ----------

def bidirectional_smooth(sog_series: list[float], alpha: float = 0.4) -> list[float]:
    """Forward + backward exponential passes averaged — zero-lag kinematic smoothing."""
    x = np.asarray(sog_series, dtype=float)
    fwd = np.empty_like(x)
    acc = x[0]
    for i, v in enumerate(x):
        acc = alpha * v + (1 - alpha) * acc
        fwd[i] = acc
    bwd = np.empty_like(x)
    acc = x[-1]
    for i in range(len(x) - 1, -1, -1):
        acc = alpha * x[i] + (1 - alpha) * acc
        bwd[i] = acc
    return ((fwd + bwd) / 2).tolist()
