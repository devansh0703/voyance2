"""Kinematics + algorithms: EKF/UKF tracking (filterpy), splines, Douglas-Peucker,
Fréchet, Vincenty/haversine, Levenshtein/Jaro-Winkler (rapidfuzz), z-score/IQR.

Libraries do the math (owner rule: never hand-roll what exists open-source);
collision-domain formulas (DCPA/TCPA, Goodwin-Stanton, fuzzy CRI) are standard
domain equations from the COLREG literature.
"""
from __future__ import annotations

import numpy as np
import shapely
from filterpy.kalman import ExtendedKalmanFilter, UnscentedKalmanFilter, MerweScaledSigmaPoints
from haversine import haversine_vector, Unit
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler
from scipy.interpolate import CubicSpline

EARTH_R_NM = 3440.065


def haversine_nm(lat1, lon1, lat2, lon2):
    """Vectorized haversine via haversine library when scalar-friendly."""
    p1 = np.column_stack([np.atleast_1d(lat1), np.atleast_1d(lon1)])
    p2 = np.column_stack([np.atleast_1d(lat2), np.atleast_1d(lon2)])
    return haversine_vector(p1, p2, Unit.NAUTICAL_MILES)


def vincenty_nm(lat1, lon1, lat2, lon2):
    """High-precision geodesic (WGS-84) via pyproj Geod."""
    from pyproj import Geod
    g = Geod(ellps="WGS84")
    _, _, d = g.inv(np.atleast_1d(lon1), np.atleast_1d(lat1),
                    np.atleast_1d(lon2), np.atleast_1d(lat2))
    return np.asarray(d) / 1852.0


def haversine_nm_arr(lat1, lon1, lat2, lon2) -> np.ndarray:
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return np.atleast_1d(2 * EARTH_R_NM * np.arcsin(np.sqrt(np.clip(a, 0, 1))))


# ---------- EKF / UKF vessel tracking (constant-velocity, polar → cartesian) ----------

def _lla_to_en(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Local east/north meters around a reference origin (degrees in, meters out)."""
    k = np.pi / 180
    return (lon - lon0) * 111320 * np.cos(lat0 * k), (lat - lat0) * 110540


def _en_to_lla(e: float, n: float, lat0: float, lon0: float) -> tuple[float, float]:
    return n / 110540 + lat0, e / (111320 * np.cos(lat0 * np.pi / 180)) + lon0


def ekf_track(lats: list[float], lons: list[float], dts: list[float]) -> list[tuple[float, float]]:
    """Extended Kalman Filter, constant-velocity in local ENU. Returns smoothed positions."""
    if len(lats) < 2:
        return list(zip(lats, lons))
    lat0, lon0 = float(np.mean(lats)), float(np.mean(lons))
    e0, n0 = _lla_to_en(lats[0], lons[0], lat0, lon0)
    f = ExtendedKalmanFilter(dim_x=4, dim_z=2)
    f.x = np.array([e0, n0, 0.0, 0.0])
    f.F = np.eye(4)
    f.H = np.array([[1.0, 0, 0, 0], [0, 1.0, 0, 0]])
    f.P *= 100.0
    f.R = np.eye(2) * 25.0          # AIS position σ ≈ 5 m–50 m; be forgiving
    f.Q = np.eye(4) * 0.5
    out = [(float(lats[0]), float(lons[0]))]
    for i in range(1, len(lats)):
        dt = max(dts[i] - dts[i - 1], 0.0)
        f.F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]])
        f.predict()
        e, n = _lla_to_en(lats[i], lons[i], lat0, lon0)
        f.update(np.array([e, n]), HJacobian=lambda x: f.H, Hx=lambda x: x[:2])
        lat_s, lon_s = _en_to_lla(f.x[0], f.x[1], lat0, lon0)
        out.append((float(lat_s), float(lon_s)))
    return out


def ukf_track(lats: list[float], lons: list[float], dts: list[float]) -> list[tuple[float, float]]:
    """Unscented Kalman Filter variant of the same tracker."""
    if len(lats) < 2:
        return list(zip(lats, lons))
    lat0, lon0 = float(np.mean(lats)), float(np.mean(lons))
    e0, n0 = _lla_to_en(lats[0], lons[0], lat0, lon0)
    sigmas = MerweScaledSigmaPoints(4, alpha=0.3, beta=2.0, kappa=0.0)
    f = UnscentedKalmanFilter(dim_x=4, dim_z=2, fx=lambda x, dt: x @ np.eye(4),
                              hx=lambda x: x[:2], dt=1.0, points=sigmas)
    f.x = np.array([e0, n0, 0.0, 0.0])
    f.P *= 100.0
    f.R = np.eye(2) * 25.0
    f.Q = np.eye(4) * 0.5
    out = [(float(lats[0]), float(lons[0]))]
    def _fx(x, dt):
        return np.array([x[0] + x[2] * dt, x[1] + x[3] * dt, x[2], x[3]])
    for i in range(1, len(lats)):
        dt = max(dts[i] - dts[i - 1], 0.0)
        f.predict(dt=dt, fx=_fx)
        e, n = _lla_to_en(lats[i], lons[i], lat0, lon0)
        f.update(np.array([e, n]))
        lat_s, lon_s = _en_to_lla(f.x[0], f.x[1], lat0, lon0)
        out.append((float(lat_s), float(lon_s)))
    return out


def spline_smooth(xs, ys, n: int = 60):
    """Cubic spline interpolation along the track (param = cumulative index)."""
    t = np.arange(len(xs), dtype=float)
    if len(t) < 3:
        return list(zip(xs, ys))
    cs_x, cs_y = CubicSpline(t, xs), CubicSpline(t, ys)
    tt = np.linspace(0, t[-1], n)
    return list(zip(cs_x(tt).tolist(), cs_y(tt).tolist()))


def douglas_peucker(coords: list[tuple[float, float]], tol_deg: float = 0.005):
    """Line simplification via shapely (Douglas-Peucker implementation)."""
    line = shapely.LineString(coords)
    return list(line.simplify(tol_deg).coords)


def frechet_distance(coords_a, coords_b) -> float:
    """Discrete Fréchet distance via shapely."""
    from shapely import frechet_distance
    return float(frechet_distance(shapely.LineString(coords_a), shapely.LineString(coords_b)))


def name_similarity(a: str, b: str) -> dict:
    """Levenshtein ratio + Jaro-Winkler (rapidfuzz) for port-name record linkage."""
    return {"levenshtein_ratio": fuzz.ratio(a, b) / 100.0,
            "jaro_winkler": JaroWinkler.normalized_similarity(a.lower(), b.lower())}


def zscore_outliers(xs) -> list[int]:
    xs = np.asarray(xs, dtype=float)
    if len(xs) < 3:
        return []
    z = np.abs((xs - xs.mean()) / max(xs.std(), 1e-9))
    return list(np.nonzero(z > 3)[0])


def iqr_filter_mask(xs) -> np.ndarray:
    xs = np.asarray(xs, dtype=float)
    q1, q3 = np.quantile(xs, [0.25, 0.75])
    iqr = q3 - q1
    return (xs >= q1 - 1.5 * iqr) & (xs <= q3 + 1.5 * iqr)


# ---------- DCPA / TCPA, Goodwin-Stanton domain, fuzzy CRI ----------

def dcpa_tcpa(lat1, lon1, cog1_deg, sog1_kn, lat2, lon2, cog2_deg, sog2_kn):
    """Closest Point / Time of Closest Point of Approach for two surface contacts.

    Constant-velocity encounter model in local ENU. Returns (dcpa_nm, tcpa_min).
    """
    k = np.pi / 180
    # meters/second, east/north
    v1 = np.array([np.sin(cog1_deg * k), np.cos(cog1_deg * k)]) * sog1_kn * 0.5144
    v2 = np.array([np.sin(cog2_deg * k), np.cos(cog2_deg * k)]) * sog2_kn * 0.5144
    rel_v = v2 - v1                     # relative velocity of B w.r.t. A
    p1 = np.array(_lla_to_en(lat1, lon1, lat1, lon1))
    p2 = np.array(_lla_to_en(lat2, lon2, lat1, lon1))
    rel_p = p2 - p1
    vv = float(rel_v @ rel_v)
    if vv < 1e-6:
        d = float(np.linalg.norm(rel_p)) / 1852.0
        return d, None
    t_star = -float(rel_p @ rel_v) / vv          # seconds
    closest = rel_p + rel_v * max(t_star, 0.0)
    dcpa_m = float(np.linalg.norm(closest))
    return dcpa_m / 1852.0, (t_star / 60.0 if t_star > 0 else 0.0)


def goodwin_stanton_semi_axes(sog_kn: float) -> tuple[float, float]:
    """Goodwin's ship-domain ellipse semi-axes in nautical miles.

    Classic Goodwin (1975) formulation scaled by speed: fore ≈ 6·L, aft ≈ 2·L
    with L ~ 1.5·sog/10 NM region; we use the common analytic approximation:
    a (fore) = 0.20 + 0.06·sog, b (athwart) = 0.35·a  (Goodwin-Stanton blend).
    """
    a = 0.20 + 0.06 * float(sog_kn)
    return a, 0.35 * a


def in_goodwin_stanton(d_nm: float, bearing_from_own_deg: float, sog_kn: float) -> bool:
    """Is contact d NM away inside our domain ellipse given bearing (0 = dead ahead)?"""
    a, b = goodwin_stanton_semi_axes(sog_kn)
    th = np.radians(bearing_from_own_deg)
    return (d_nm * np.cos(th)) ** 2 / a ** 2 + (d_nm * np.sin(th)) ** 2 / b ** 2 <= 1.0


def fuzzy_cri(dcpa_nm: float, tcpa_min: float | None, sog_kn: float) -> float:
    """Fuzzy Collision Risk Index ∈ [0,1]: distance & time membership x domain weight.

    Membership functions follow the widely used fuzzy-CRI literature (triangular
    sets on dCPA/TCPA), weighted by Goodwin-Stanton domain intrusion.
    """
    if tcpa_min is None:
        t_risk = 0.0 if dcpa_nm > 2.0 else 0.3
    else:
        if tcpa_min <= 3:
            t_risk = 1.0
        elif tcpa_min <= 8:
            t_risk = (8 - tcpa_min) / 5
        elif tcpa_min <= 15:
            t_risk = 0.3 * (15 - tcpa_min) / 7
        else:
            t_risk = 0.0
    if dcpa_nm <= 0.25:
        d_risk = 1.0
    elif dcpa_nm <= 1.0:
        d_risk = (1.0 - dcpa_nm) / 0.75
    elif dcpa_nm <= 3.0:
        d_risk = 0.5 * (3.0 - dcpa_nm) / 2.0
    else:
        d_risk = 0.0
    a, b = goodwin_stanton_semi_axes(sog_kn)
    domain_w = min(1.0, (a + b) / 2 / max(dcpa_nm, 0.1))
    return float(min(1.0, max(d_risk, t_risk) * (0.6 + 0.4 * min(domain_w, 1.0))))
