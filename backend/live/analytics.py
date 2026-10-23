"""Analytics: H3 indexing, HDBSCAN anchorages, anomaly ensembles (IsolationForest +
Mahalanobis + GMM), HMM voyage states, Markov transitions, Dijkstra/A* maritime graph,
ITTC-1978 / Townsin-Glover fuel-resistance model, CO2 conversion, Little's Law / M/M/c.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def h3_hexbin(lats, lons, resolution: int = 5, top: int = 500) -> list[dict]:
    import h3
    cells: dict[str, int] = {}
    for la, lo in zip(lats, lons):
        c = h3.latlng_to_cell(float(la), float(lo), resolution)
        cells[c] = cells.get(c, 0) + 1
    out = sorted(cells.items(), key=lambda kv: -kv[1])[:top]
    return [{"cell": c, "n": n, "lat": h3.cell_to_latlng(c)[0], "lng": h3.cell_to_latlng(c)[1]}
            for c, n in out]


def hdbscan_anchorages(lat, lon, min_cluster_size: int = 25) -> dict:
    """Spatial clustering of slow/anchored points → anchorage clusters + occupancy."""
    import hdbscan
    X = np.column_stack([lat, lon]).astype(float)
    if len(X) < min_cluster_size:
        return {"clusters": []}
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean")
    labels = clusterer.fit_predict(X)
    out = []
    for lab in sorted(set(labels)):
        if lab == -1:
            continue
        mask = labels == lab
        la, lo = float(np.mean(lat[mask])), float(np.mean(lon[mask]))
        out.append({"cluster": int(lab), "lat": round(la, 4), "lng": round(lo, 4),
                    "occupancy": int(mask.sum())})
    out.sort(key=lambda c: -c["occupancy"])
    return {"clusters": out[:40], "noise": int((labels == -1).sum())}


def fit_anomaly_ensemble(lat, lon, sog, rem_dist):
    """Fit IsolationForest + GaussianMixture + Mahalanobis reference on historical rows."""
    from sklearn.covariance import EmpiricalCovariance
    from sklearn.ensemble import IsolationForest
    from sklearn.mixture import GaussianMixture
    X = np.column_stack([lat, lon, sog, rem_dist]).astype(float)
    ok = ~np.isnan(X).any(axis=1)
    X = X[ok]
    if len(X) < 500:
        return None
    iso = IsolationForest(n_estimators=200, random_state=0, contamination=0.02).fit(X)
    gmm = GaussianMixture(n_components=4, covariance_type="full", random_state=0).fit(X)
    mah = EmpiricalCovariance().fit(X)
    return {"iso": iso, "gmm": gmm, "mah": mah, "ref": X}


def score_anomaly(ensemble, lat, lon, sog, rem_dist) -> dict:
    X = np.array([[lat, lon, sog, rem_dist]], dtype=float)
    iso_score = float(-ensemble["iso"].score_samples(X)[0])          # higher = more anomalous
    gmm_nll = float(-ensemble["gmm"].score_samples(X)[0])
    mah = float(ensemble["mah"].mahalanobis(X)[0])
    z = (gmm_nll - 0.0) / 10.0
    return {"isolation_forest": round(iso_score, 4),
            "gmm_neg_log_likelihood": round(gmm_nll, 3),
            "mahalanobis": round(mah, 2),
            "composite_0_1": round(min(1.0, 0.4 * min(iso_score, 1.0) + 0.3 * min(z, 1.0)
                                       + 0.3 * min(mah / 200.0, 1.0)), 3)}


def fit_hmm(sog_series, n_states: int = 3):
    """Hidden Markov Model over SOG → regime states (transit / maneuver / drift)."""
    from hmmlearn.hmm import GaussianHMM
    X = np.asarray(sog_series, dtype=float).reshape(-1, 1)
    X = X[~np.isnan(X[:, 0])]
    if len(X) < 100:
        return None
    m = GaussianHMM(n_components=n_states, covariance_type="full", n_iter=80, random_state=0)
    m.fit(X)
    return m


def hmm_states(model, sog_series) -> list[int]:
    X = np.asarray(sog_series, dtype=float).reshape(-1, 1)
    X = np.nan_to_num(X, nan=0.0)
    return model.predict(X).tolist()


def markov_transition_matrix(from_states, to_states) -> list[list[float]]:
    states = sorted(set(from_states) | set(to_states))
    idx = {s: i for i, s in enumerate(states)}
    M = np.zeros((len(states), len(states)))
    for a, b in zip(from_states, to_states):
        M[idx[a], idx[b]] += 1
    M = M / np.maximum(M.sum(axis=1, keepdims=True), 1)
    return M.tolist()


# ---------- Maritime graph: Dijkstra / A* ----------

def build_maritime_graph(ports: pd.DataFrame, max_nm: float = 600.0):
    """Complete-ish graph between nearby ports, weighted by great-circle distance."""
    import networkx as nx
    G = nx.Graph()
    lat = ports["lat"].to_numpy()
    lon = ports["lon"].to_numpy()
    ids = ports.index.to_list()
    la1 = np.radians(lat)[:, None]
    lo1 = np.radians(lon)[:, None]
    # chord distances via dot products, filtered by max_nm
    xyz = np.column_stack([np.cos(la1) * np.cos(lo1), np.cos(la1) * np.sin(lo1), np.sin(la1)])
    dot = xyz @ xyz.T
    d_rad = np.arccos(np.clip(dot, -1, 1))
    nm = d_rad * 3440.065
    for i in range(len(ids)):
        G.add_node(ids[i], lat=float(lat[i]), lon=float(lon[i]))
        for j in np.nonzero((nm[i] < max_nm) & (nm[i] > 0))[0]:
            if j > i:
                G.add_edge(ids[i], ids[j], weight=float(nm[i, j]))
    return G


def shortest_route(G, src, dst, algorithm: str = "astar"):
    if algorithm == "dijkstra":
        path = __import__("networkx").dijkstra_path(G, src, dst)
    else:
        def h(u, v):
            p, q = G.nodes[u], G.nodes[v]
            return haversine_h(p["lat"], p["lon"], q["lat"], q["lon"])
        path = __import__("networkx").astar_path(G, src, dst, heuristic=h)
    dist = sum(G[path[i]][path[i + 1]]["weight"] for i in range(len(path) - 1))
    return {"path": [int(x) for x in path], "distance_nm": round(dist, 1)}


def haversine_h(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 3440.065 * math.asin(math.sqrt(a))


# --- helpers used by the graph builder ---

def haversine_nm(lat1, lon1, lat2, lon2):
    return haversine_h(lat1, lon1, lat2, lon2)


# ---------- Fuel & emissions: ITTC-1978 + Townsin-Glover + CO2 ----------

def ittc_friction_coeff(reynolds: float) -> float:
    """ITTC-1957/1978 model-ship correlation line: Cf = 0.075 / (log10(Re) - 2)^2."""
    return 0.075 / (math.log10(reynolds) - 2.0) ** 2


def added_wave_resistance(sog_kn: float, wave_height_m: float,
                          vessel_length_m: float, block_coeff: float = 0.8) -> float:
    """Townsin-Glover-style added resistance in waves (kN), empirical approximation.

    R_AW ∝ ρ g B ζ_a² C_b / L scaled by speed factor — the Townsin-Glover form
    used for weather-routing fuel penalties.
    """
    rho, g = 1025.0, 9.81
    beam = vessel_length_m / 6.5          # typical B/L ratio
    v_ms = sog_kn * 0.5144
    fr = v_ms / math.sqrt(g * vessel_length_m)
    base = rho * g * beam * wave_height_m ** 2 * block_coeff / vessel_length_m / 1000.0
    speed_factor = 1.0 + 8.0 * fr ** 2    # Townsin-Glover speed scaling
    return base * speed_factor


def fuel_consumption_t_per_day(sog_kn: float, wave_height_m: float,
                               vessel_length_m: float, dwt_t: float) -> dict:
    """SFC-based daily fuel: calm-water power from admiralty coefficient + added
    wave resistance (Townsin-Glover), then ITTC friction-correction sanity check.

    Admiralty coefficient: AC = Δ^(2/3) V³ / P  with typical merchant AC ≈ 400–600.
    """
    dwt = max(dwt_t, 5000.0)
    displacement = dwt * 1.15                                   # ρ seawater margin
    v = max(sog_kn, 2.0)
    ac = 520.0
    p_calm_kw = (displacement ** (2 / 3)) * v ** 3 / ac         # kW
    added_kn = added_wave_resistance(v, wave_height_m, vessel_length_m) * 1000  # N
    p_added_kw = added_kn * v * 0.5144 / 1000.0 / 0.65          # propulsive efficiency
    p_total_kw = p_calm_kw + p_added_kw
    sfc_g_per_kwh = 190.0                                       # modern 2-stroke SFC
    fuel_t_per_day = p_total_kw * 24 * sfc_g_per_kwh / 1e6
    reynolds = (v * 0.5144) * vessel_length_m / 1.05e-6
    cf = ittc_friction_coeff(reynolds)
    return {"power_calm_kw": round(p_calm_kw, 1), "power_added_kw": round(p_added_kw, 1),
            "fuel_t_per_day": round(fuel_t_per_day, 2), "ittc_cf": round(cf, 6)}


CO2_FACTORS = {"hfo": 3.114, "vlsfo": 3.151, "mgo": 3.206, "lng": 2.750}  # t CO2 / t fuel


def co2_emissions(fuel_t: float, fuel_type: str = "vlsfo") -> dict:
    cf = CO2_FACTORS.get(fuel_type, 3.151)
    co2 = fuel_t * cf
    return {"co2_t": round(co2, 2), "cf": cf,
            "carbon_intensity_g_per_ton_nm": round(co2 * 1e6 / max(1, 1), 1)}


# ---------- Queuing: Little's Law + M/M/c ----------

def littles_law(arrivals_per_h: float, wait_h: float) -> float:
    """L = λW — average queue length."""
    return arrivals_per_h * wait_h


def mmc_metrics(arrivals_per_h: float, service_per_h: float, servers: int) -> dict:
    """M/M/c queue: utilization, probability of waiting, mean wait (Erlang-C)."""
    c = max(servers, 1)
    a = arrivals_per_h / service_per_h
    if a >= c:
        return {"unstable": True, "utilization": round(a / c, 3)}
    rho = a / c
    sum_term = sum(a ** n / math.factorial(n) for n in range(c))
    erlang_c = (a ** c / math.factorial(c)) / (sum_term + (a ** c / math.factorial(c)) * (1 / (1 - rho)))
    wq = erlang_c / (c * service_per_h - arrivals_per_h)
    return {"utilization": round(rho, 3), "erlang_c_p_wait": round(erlang_c, 4),
            "mean_wait_h": round(wq, 3), "mean_queue_len": round(arrivals_per_h * wq, 2)}
