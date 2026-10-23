"""Build voyage samples from NOAA/MarineCadastre daily AIS broadcast-point GeoParquet.

Input : data/raw/ais-YYYY-MM-DD.parquet  (CC0, NOAA Office for Coastal Management)
Output: data/interim/samples-YYYY-MM.parquet   (one row per voyage sample point)
        data/interim/voyages-YYYY-MM.parquet   (one row per voyage)

Voyage definition: a vessel leaving a UN/LOCODE port buffer (15 km) and arriving
at another port buffer (or the same after >= 6 h away). Samples are points
>= 1 h apart, >= 30 NM from the arrival port, with real timestamps and SOG.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import shapely

sys.path.insert(0, str(Path(__file__).parent))
from geo import (  # noqa: E402
    KEEP_TYPES, TYPE_TO_GROUP, PortMatcher, assign_region, haversine_nm,
    load_ports,
)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PORTS_CSV = ROOT / "data" / "raw" / "unlocode.csv"

BUFFER_KM = 15.0
MIN_VOYAGE_H = 3.0
MAX_VOYAGE_H = 10 * 24.0
MAX_GAP_MIN = 90.0
SAME_PORT_AWAY_H = 6.0
SAMPLE_SPACING_H = 1.0
MIN_DIST_DEST_NM = 8.0
MIN_SOG = 0.5
MAX_FIX_SPEED_KN = 90.0   # implied speed between consecutive fixes that breaks a track
MAX_VOYAGE_SPEED_KN = 40.0  # plausible max sustained speed → drops flap-noise voyages
# NOAA daily files contain receiver-noise positions outside US waters; the
# MarineCadastre domain is US waters, so drop impossible positions early.
US_LAT = (14.0, 72.0)
US_LON = (-180.0, -60.0)


def collect_points(paths: list[Path]) -> pd.DataFrame:
    mmsi_all, ts_all, lat_all, lon_all, sog_all, cog_all, vt_all = [], [], [], [], [], [], []
    length_all, draft_all = [], []
    for p in paths:
        pf = pq.ParquetFile(p)
        for rg in range(pf.metadata.num_row_groups):
            tbl = pf.read_row_group(rg, columns=[
                "mmsi", "base_date_time", "sog", "cog", "vessel_type",
                "length", "draft", "geometry"])
            vt = tbl.column("vessel_type").to_numpy()
            keep = np.isin(vt, sorted(KEEP_TYPES))
            if not keep.any():
                continue
            tbl = tbl.take(np.nonzero(keep)[0])
            gi = tbl.schema.get_field_index("geometry")
            tbl = tbl.set_column(gi, "geometry",
                                 tbl.column("geometry").cast(pa.large_binary()))
            coords = shapely.get_coordinates(
                shapely.from_wkb(tbl.column("geometry").to_pylist()))
            mmsi_all.append(tbl.column("mmsi").to_numpy().astype(np.int64))
            ts_all.append(tbl.column("base_date_time")
                          .cast("timestamp[ms]").to_numpy().astype(np.int64))
            lat_all.append(coords[:, 1].astype(np.float32))
            lon_all.append(coords[:, 0].astype(np.float32))
            sog_all.append(tbl.column("sog").to_numpy().astype(np.float32))
            cog_all.append(tbl.column("cog").to_numpy().astype(np.float32))
            vt_all.append(tbl.column("vessel_type").to_numpy().astype(np.int16))
            length_all.append(tbl.column("length").to_numpy().astype(np.float32))
            draft_all.append(tbl.column("draft").to_numpy().astype(np.float32))
    df = pd.DataFrame({
        "mmsi": np.concatenate(mmsi_all), "ts": np.concatenate(ts_all),
        "lat": np.concatenate(lat_all), "lon": np.concatenate(lon_all),
        "sog": np.concatenate(sog_all), "cog": np.concatenate(cog_all),
        "vessel_type": np.concatenate(vt_all),
        "length": np.concatenate(length_all), "draft": np.concatenate(draft_all),
    })
    df = df[(df["lat"].between(*US_LAT) & df["lon"].between(*US_LON))]
    order = np.lexsort((df["ts"].to_numpy(), df["mmsi"].to_numpy()))
    return df.iloc[order].reset_index(drop=True)


def segment_vessel(df_v: pd.DataFrame, matcher: PortMatcher):
    """Return (sample_rows, voyage_rows) lists for one vessel's sorted points."""
    lat = df_v["lat"].to_numpy(np.float64)
    lon = df_v["lon"].to_numpy(np.float64)
    ts = df_v["ts"].to_numpy(np.int64)
    sog = df_v["sog"].to_numpy(np.float32)
    if len(ts) < 10:
        return [], []

    # teleport filter: a fix-to-fix implied speed above MAX_FIX_SPEED_KN is
    # receiver noise (position flapping); each clean run is processed separately
    d_fix = haversine_nm(lat[:-1], lon[:-1], lat[1:], lon[1:])
    dt_h = np.maximum(np.diff(ts) / 3.6e9, 1 / 60)
    cont = np.concatenate([[True], (np.diff(ts) / 6e4 <= MAX_GAP_MIN)
                          & (d_fix / dt_h <= MAX_FIX_SPEED_KN)])
    runs = np.split(np.arange(len(ts)), np.nonzero(~cont)[0] + 1)
    runs = [r for r in runs if len(r) >= 10]
    all_samples, all_voyages = [], []
    for r in runs:
        sel = slice(r[0], r[-1] + 1)
        s, v = _detect_voyages(lat[sel], lon[sel], ts[sel], sog[sel], df_v, matcher)
        all_samples.extend(s)
        all_voyages.extend(v)
    return all_samples, all_voyages


def _detect_voyages(lat, lon, ts, sog, df_v, matcher):
    dist, pidx = matcher.nearest(lat, lon)
    km = np.rad2deg(dist) * 111.32
    inside = km <= BUFFER_KM
    pid = np.where(inside, pidx, -1)

    # port-visit runs: contiguous same-port inside stretches
    change = np.concatenate([[True], (pid[1:] != pid[:-1])])
    starts = np.nonzero(change)[0]
    ends = np.concatenate([starts[1:], [len(pid)]]) - 1

    visits = []  # (start_i, end_i, port, entry_ts, exit_ts)
    for s, e in zip(starts, ends):
        if pid[s] >= 0:
            visits.append((s, e, pid[s], ts[s], ts[e]))

    samples, voyages = [], []
    for vi in range(len(visits) - 1):
        v0, v1 = visits[vi], visits[vi + 1]
        dep_i, dep_port, dep_ts = v0[1], v0[2], v0[4]      # exit of first visit
        arr_i, arr_port, arr_ts = v1[0], v1[2], v1[3]      # entry of next visit
        dur_h = (arr_ts - dep_ts) / 3.6e6
        if dep_port == arr_port and (
                (v1[0] - v0[1]) / 3.6e6 < SAME_PORT_AWAY_H or dur_h < MIN_VOYAGE_H):
            continue
        if not (MIN_VOYAGE_H <= dur_h <= MAX_VOYAGE_H):
            continue
        m = slice(dep_i, arr_i + 1)
        v_lat, v_lon, v_ts, v_sog = lat[m], lon[m], ts[m], sog[m]
        if len(v_ts) < 5:
            continue
        pl = matcher.ports.iloc[arr_port]
        d_lat, d_lon = float(pl["lat"]), float(pl["lon"])
        rem_dist = haversine_nm(v_lat, v_lon, d_lat, d_lon)
        rem_time = (arr_ts - v_ts) / 3.6e6
        cand = np.nonzero((rem_dist >= MIN_DIST_DEST_NM) & (rem_time >= 0.5)
                          & (v_sog >= MIN_SOG))[0]
        if not len(cand):
            continue
        # spacing filter: first point per 1-h bucket
        keep_idx, last_h = [], -1e9
        for j in cand:
            h = (v_ts[j] - dep_ts) / 3.6e6
            if h - last_h >= SAMPLE_SPACING_H - 1e-6:
                keep_idx.append(j)
                last_h = h
        keep_idx = np.asarray(keep_idx, dtype=np.int64)
        if not len(keep_idx):
            continue
        # 6-h median SOG before each sample (time-based window)
        lo6 = v_ts[keep_idx] - 6 * 3600 * 1000
        left = np.searchsorted(v_ts, lo6, side="left")
        right = keep_idx + 1
        sog6 = np.array([
            np.median(v_sog[l:r]) if r - l >= 2 else v_sog[r - 1]
            for l, r in zip(left, right)], dtype=np.float32)
        elapsed = (v_ts[keep_idx] - dep_ts) / 3.6e6
        cum_d = np.concatenate([[0.0], np.cumsum(haversine_nm(
            v_lat[1:], v_lon[1:], v_lat[:-1], v_lon[:-1]))])[keep_idx]

        voyage_id = f"{int(df_v['mmsi'].iloc[0])}-{dep_ts}"
        vt = int(df_v["vessel_type"].iloc[0])
        length = float(df_v["length"].dropna().iloc[0]) if df_v["length"].notna().any() else np.nan
        draft = float(df_v["draft"].dropna().iloc[0]) if df_v["draft"].notna().any() else np.nan

        voyages.append({
            "voyage_id": voyage_id, "mmsi": int(df_v["mmsi"].iloc[0]),
            "vessel_type": vt, "vessel_type_group": TYPE_TO_GROUP.get(vt, "other"),
            "vessel_length": length, "vessel_draft": draft,
            "dep_port_idx": dep_port, "arr_port_idx": arr_port,
            "dep_ts": pd.to_datetime(dep_ts, utc=True, unit='ms'), "arr_ts": pd.to_datetime(arr_ts, utc=True, unit='ms'),
            "voyage_duration_h": dur_h,
            "voyage_distance_nm": float(cum_d[-1] + haversine_nm(
                lat[arr_i], lon[arr_i],
                matcher.ports.iloc[arr_port]["lat"], matcher.ports.iloc[arr_port]["lon"])),
        })
        samples.append(pd.DataFrame({
            "voyage_id": voyage_id, "mmsi": int(df_v["mmsi"].iloc[0]),
            "vessel_type": vt, "vessel_type_group": TYPE_TO_GROUP.get(vt, "other"),
            "vessel_length": length, "vessel_draft": draft,
            "dep_port_idx": dep_port, "arr_port_idx": arr_port,
            "dep_ts": pd.to_datetime(dep_ts, utc=True, unit='ms'), "arr_ts": pd.to_datetime(arr_ts, utc=True, unit='ms'),
            "ts": pd.to_datetime(v_ts[keep_idx], utc=True, unit='ms'),
            "lat": v_lat[keep_idx].astype(np.float32),
            "lon": v_lon[keep_idx].astype(np.float32),
            "sog": v_sog[keep_idx].astype(np.float32),
            "sog_median_6h": sog6,
            "distance_traveled_nm": cum_d.astype(np.float32),
            "elapsed_h": elapsed.astype(np.float32),
            "remaining_distance_nm": rem_dist[keep_idx].astype(np.float32),
            "remaining_time_h": rem_time[keep_idx].astype(np.float32),
        }))
    return samples, voyages


def build(paths: list[Path], month: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = collect_points(paths)
    print(f"  points after type filter: {len(df):,} ({df['mmsi'].nunique():,} vessels)")
    ports = load_ports(str(PORTS_CSV))
    matcher = PortMatcher(ports, BUFFER_KM)
    s_rows, v_rows = [], []
    for _, dv in df.groupby("mmsi", sort=False):
        s, v = segment_vessel(dv, matcher)
        if s:
            s_rows.extend(s)
        if v:
            v_rows.extend(v)
    samples = pd.concat(s_rows, ignore_index=True) if s_rows else pd.DataFrame()
    voyages = pd.DataFrame(v_rows) if v_rows else pd.DataFrame()
    if not voyages.empty:
        implied = voyages["voyage_distance_nm"] / voyages["voyage_duration_h"].clip(lower=0.5)
        ok_v = implied <= MAX_VOYAGE_SPEED_KN
        dropped = int((~ok_v).sum())
        voyages = voyages[ok_v].reset_index(drop=True)
        if not samples.empty:
            samples = samples[samples["voyage_id"].isin(set(voyages["voyage_id"]))] \
                .reset_index(drop=True)
        print(f"  implied-speed filter: dropped {dropped} flap-noise voyages")
    if not samples.empty:
        samples["region"] = assign_region(samples["lat"].to_numpy(), samples["lon"].to_numpy())
        samples["month"] = month
    return samples, voyages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYY-MM label for outputs")
    ap.add_argument("--days", required=True, help="days like 08-14 (same month)")
    args = ap.parse_args()
    d0, d1 = (int(x) for x in args.days.split("-"))
    paths = [RAW / f"ais-{args.month}-{d:02d}.parquet" for d in range(d0, d1 + 1)]
    paths = [p for p in paths if p.exists()]
    print(f"{args.month} days {args.days}: {len(paths)} files")
    samples, voyages = build(paths, args.month)
    INTERIM.mkdir(parents=True, exist_ok=True)
    samples.to_parquet(INTERIM / f"samples-{args.month}.parquet", index=False)
    voyages.to_parquet(INTERIM / f"voyages-{args.month}.parquet", index=False)
    if samples.empty:
        print(f"{args.month}: NO SAMPLES PRODUCED")
        return
    print(f"{args.month}: {len(samples):,} samples, {len(voyages):,} voyages, "
          f"{samples['mmsi'].nunique():,} vessels, "
          f"{samples['arr_port_idx'].nunique()} arrival ports")


if __name__ == "__main__":
    main()
