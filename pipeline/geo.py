"""Shared geospatial utilities: ports, haversine, regions, Beaufort scale.

Open data sources:
- UN/LOCODE code list (UNECE, open): data/raw/unlocode.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

EARTH_RADIUS_NM = 3440.065


def parse_locode_coords(coord: str) -> tuple[float, float] | None:
    """Parse UN/LOCODE '4230N 00131E' into (lat, lon) degrees."""
    if not isinstance(coord, str) or len(coord) < 11:
        return None
    try:
        lat_deg = int(coord[0:2])
        lat_min = int(coord[2:4])
        lat_h = coord[4]
        lon_deg = int(coord[6:9])
        lon_min = int(coord[9:11])
        lon_h = coord[11]
        lat = (lat_deg + lat_min / 60.0) * (1 if lat_h == "N" else -1)
        lon = (lon_deg + lon_min / 60.0) * (1 if lon_h == "E" else -1)
        return lat, lon
    except (ValueError, IndexError):
        return None


def load_ports(path: str, buffer_km: float = 15.0) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df = df[df["Function"].fillna("").str.contains("1")]
    coords = df["Coordinates"].map(parse_locode_coords)
    df = df[coords.notna()].copy()
    df[["lat", "lon"]] = pd.DataFrame(coords.dropna().tolist(), index=df.index)
    df["unlocode"] = df["Country"] + df["Location"]
    df = df.rename(columns={"NameWoDiacritics": "name"})
    keep = ["unlocode", "name", "Country", "lat", "lon"]
    df = df[keep].drop_duplicates("unlocode").reset_index(drop=True)
    # distance in km for a given buffer: precompute per-port buffer radius in degrees
    df["buffer_deg"] = buffer_km / 111.32
    return df


class PortMatcher:
    """Nearest-port matcher with spatial clustering of adjacent UN/LOCODE entries.

    Raw UN/LOCODE contains several entries for one harbor (breakwater, anchorage,
    terminal). Without clustering, nearest-port matching flickers between them,
    which fragments port-visit detection. Entries within `cluster_km` collapse
    into one port area represented by the longest-named member.
    """

    def __init__(self, ports: pd.DataFrame, buffer_km: float = 15.0,
                 cluster_km: float = 20.0):
        lat = np.radians(ports["lat"].to_numpy())
        lon = np.radians(ports["lon"].to_numpy())
        xyz = np.column_stack([
            np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat),
        ])
        tree = cKDTree(xyz)
        r = cluster_km / 6371.0
        pairs = tree.query_pairs(r)
        parent = np.arange(len(ports))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i, j in pairs:
            a, b = find(int(i)), find(int(j))
            if a != b:
                parent[max(a, b)] = min(a, b)
        roots = np.array([find(i) for i in range(len(ports))])
        ports = ports.copy()
        ports["_cluster"] = roots
        # representative: longest name in cluster (stable, informative)
        ports["_nlen"] = ports["name"].str.len()
        rep = (ports.sort_values("_nlen", ascending=False)
                    .groupby("_cluster").first().reset_index())
        rep = rep.rename(columns={"_cluster": "cluster_id"})
        rep = rep[["cluster_id", "unlocode", "name", "Country", "lat", "lon"]]
        self.raw_ports = ports
        self.ports = rep.reset_index(drop=True)
        self.buffer_km = buffer_km
        la = np.radians(self.ports["lat"].to_numpy())
        lo = np.radians(self.ports["lon"].to_numpy())
        self._xyz = np.column_stack([
            np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la),
        ])
        self.tree = cKDTree(self._xyz)

    def nearest(self, lat: np.ndarray, lon: np.ndarray):
        """Return (index, angular_distance_rad) of nearest port for each point."""
        la = np.radians(lat)
        lo = np.radians(lon)
        xyz = np.column_stack([
            np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la),
        ])
        return self.tree.query(xyz, k=1)


def haversine_nm(lat1, lon1, lat2, lon2) -> np.ndarray:
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = la2 - la1
    dlon = lo2 - lo1
    a = np.sin(dlat / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_NM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


REGIONS = [
    # name, lat_min, lat_max, lon_min, lon_max  (US-centric; MarineCadastre is US waters)
    ("us_west_coast", 32.0, 49.0, -130.0, -117.0),
    ("us_east_coast", 24.0, 45.5, -82.0, -66.0),
    ("gulf_of_mexico", 18.0, 30.5, -98.0, -80.5),
    ("alaska", 51.0, 60.0, -170.0, -140.0),
    ("hawaii_pacific", 15.0, 29.0, -180.0, -150.0),
    ("great_lakes", 41.0, 49.0, -92.0, -76.0),
    ("puerto_rico_caribbean", 15.0, 19.5, -68.0, -62.0),
]


def assign_region(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    out = np.full(lat.shape, "other_us_waters", dtype=object)
    for name, la0, la1, lo0, lo1 in REGIONS:
        mask = (lat >= la0) & (lat <= la1) & (lon >= lo0) & (lon <= lo1) & (out == "other_us_waters")
        out[mask] = name
    return out


def beaufort_from_wind_kn(ws: np.ndarray) -> np.ndarray:
    """Beaufort scale bounds in knots (0..12)."""
    bounds = np.array([1, 3, 6, 10, 16, 21, 27, 33, 40, 47, 55, 63])
    out = np.searchsorted(bounds, ws, side="right")
    return out.astype(np.int8)


VESSEL_TYPE_GROUPS = {
    "cargo": list(range(70, 80)),
    "tanker": list(range(80, 90)),
    "passenger": list(range(60, 70)),
    "tug_pilot": [31, 32, 52, 53],
    "fishing": [30],
    "pleasure": [36, 37],
    "other": [x for x in range(20, 100) if x not in (
        list(range(60, 90)) + [30, 31, 32, 36, 37, 52, 53])],
}

TYPE_TO_GROUP = {t: g for g, ts in VESSEL_TYPE_GROUPS.items() for t in ts}

# Types kept for ETA modeling (matches the idea's segments: liner, tanker, dry-bulk + support)
KEEP_TYPES = set(range(60, 90)) | {30, 31, 32, 52, 53}
