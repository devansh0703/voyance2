"""Export pipeline artifacts as static JSON for the web dashboards.

Outputs to web/public/data/: eval.json, drift.json, stats.json, map.json.
Everything is derived from real pipeline outputs; nothing is synthesized.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
REPORTS = ROOT / "reports"
OUT = ROOT / "web" / "public" / "data"
OUT.mkdir(parents=True, exist_ok=True)


def port_names() -> dict[int, str]:
    import sys
    sys.path.insert(0, str(ROOT / "pipeline"))
    from geo import PortMatcher, load_ports
    # indices refer to the CLUSTERED port table (same as PortMatcher used in
    # segmentation) — labeling from the raw list misassigns names
    matcher = PortMatcher(load_ports(str(ROOT / "data" / "raw" / "unlocode.csv")), 15.0)
    return matcher.ports["name"].to_dict()


def export_stats(frames: dict[str, pd.DataFrame]):
    months = []
    region_counter: dict[str, int] = {}
    type_counter: dict[str, int] = {}
    beaufort_counter: dict[str, int] = {}
    weather_ok, total = 0, 0
    for m, df in frames.items():
        months.append({
            "month": m,
            "voyages": int(df["voyage_id"].nunique()),
            "samples": int(len(df)),
            "vessels": int(df["mmsi"].nunique()),
        })
        for k, v in df["region"].value_counts().items():
            region_counter[k] = region_counter.get(k, 0) + int(v)
        for k, v in df["vessel_type_group"].value_counts().items():
            type_counter[k] = type_counter.get(k, 0) + int(v)
        if "beaufort_class" in df:
            for k, v in df["beaufort_class"].dropna().astype(int).value_counts().items():
                beaufort_counter[str(k)] = beaufort_counter.get(str(k), 0) + int(v)
        weather_ok += int(df["weather_ok"].sum())
        total += len(df)
    stats = {
        "months": months,
        "by_region": dict(sorted(region_counter.items(), key=lambda kv: -kv[1])),
        "by_type": dict(sorted(type_counter.items(), key=lambda kv: -kv[1])),
        "by_beaufort": dict(sorted(beaufort_counter.items(), key=lambda kv: int(kv[0]))),
        "weather_ok_fraction": weather_ok / max(total, 1),
        "total_voyages": sum(x["voyages"] for x in months),
        "total_samples": sum(x["samples"] for x in months),
    }
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2))
    print("stats.json:", stats["total_voyages"], "voyages")


def export_map(frames: dict[str, pd.DataFrame], voy: dict[str, pd.DataFrame]):
    pn = port_names()
    # real per-voyage error where model predictions exist (July test month)
    err_by_voyage: dict[str, float] = {}
    pfile = REPORTS / "test_predictions.parquet"
    if pfile.exists():
        pr = pd.read_parquet(pfile)
        pr["e"] = ((pr["p50"] - pr["y"]).abs() / pr["y"].clip(lower=0.5))
        err_by_voyage = pr.groupby("voyage_id")["e"].mean().round(3).to_dict()
    voyages_out = []
    for m, df in frames.items():
        v = voy[m]
        top = (v.sort_values("voyage_distance_nm", ascending=False)
                .drop_duplicates("mmsi").head(60))
        samples_by_voy = {k: d for k, d in df.groupby("voyage_id")}
        for _, row in top.iterrows():
            s = samples_by_voy.get(row["voyage_id"])
            if s is None or len(s) < 4:
                continue
            coords = [[round(float(a), 3), round(float(b), 3)]
                      for a, b in zip(s["lon"], s["lat"])]
            voyages_out.append({
                "voyage_id": row["voyage_id"],
                "vessel_type_group": row["vessel_type_group"],
                "dep_port": pn.get(int(row["dep_port_idx"]), f"port#{row['dep_port_idx']}"),
                "arr_port": pn.get(int(row["arr_port_idx"]), f"port#{row['arr_port_idx']}"),
                "duration_h": round(float(row["voyage_duration_h"]), 1),
                "region": row.get("region", ""),
                "coords": coords,
                "err_pct": err_by_voyage.get(row["voyage_id"]),
            })
    # lanes for globe: aggregate 2° bins of all sample points
    lanes = []
    for m, df in frames.items():
        lat = (df["lat"] // 2 * 2).round(1)
        lon = (df["lon"] // 2 * 2).round(1)
        g = pd.DataFrame({"la": lat, "lo": lon}).value_counts().head(800)
        lanes = [[float(a), float(b), int(n)] for (a, b), n in g.items()]
    (OUT / "map.json").write_text(json.dumps({
        "voyages": voyages_out, "lanes": lanes[:900],
    }))
    print("map.json:", len(voyages_out), "showcase voyages")


def export_voyages_api(frames: dict[str, pd.DataFrame], voy: dict[str, pd.DataFrame]):
    pn = port_names()
    items = []
    for m, v in voy.items():
        for _, row in v.head(400).iterrows():
            items.append({
                "voyage_id": row["voyage_id"], "mmsi": int(row["mmsi"]),
                "vessel_type_group": row["vessel_type_group"],
                "dep_port": pn.get(int(row["dep_port_idx"]), str(row["dep_port_idx"])),
                "arr_port": pn.get(int(row["arr_port_idx"]), str(row["arr_port_idx"])),
                "dep_ts": str(row["dep_ts"]), "arr_ts": str(row["arr_ts"]),
                "duration_h": round(float(row["voyage_duration_h"]), 2),
                "distance_nm": round(float(row["voyage_distance_nm"]), 1),
                "region": "",
                "month": m,
            })
    (REPORTS / "voyages.json").write_text(json.dumps({"count": len(items), "voyages": items}))
    print("voyages.json (API):", len(items))


def main():
    months = ["2024-01", "2024-04", "2024-07"]
    frames, voy = {}, {}
    for m in months:
        f = INTERIM / f"features-{m}.parquet"
        v = INTERIM / f"voyages-{m}.parquet"
        if f.exists():
            frames[m] = pd.read_parquet(f)
        if v.exists():
            voy[m] = pd.read_parquet(v)
    if not frames:
        print("no features yet — run make data first")
        return
    export_stats(frames)
    export_map(frames, voy)
    export_voyages_api(frames, voy)
    # model CI ribbon: daily mean P10/P50/P90 from real test predictions
    pf = REPORTS / "test_predictions.parquet"
    if pf.exists():
        pr = pd.read_parquet(pf)
        pr["d"] = pd.to_datetime(pr["ts"], utc=True).dt.date
        g = pr.groupby("d")[["p10", "p50", "p90"]].mean().reset_index()
        (OUT / "ribbon.json").write_text(json.dumps({
            "dates": [str(x) for x in g["d"]],
            "p10": [round(float(x), 2) for x in g["p10"]],
            "p50": [round(float(x), 2) for x in g["p50"]],
            "p90": [round(float(x), 2) for x in g["p90"]]}))
        print("ribbon.json written")

    for name in ("eval.json", "drift_summary.json"):
        src = REPORTS / name
        if src.exists():
            dst = OUT / ("drift.json" if name.startswith("drift") else name)
            dst.write_text(src.read_text())
            print(f"copied {name} -> {dst.name}")


if __name__ == "__main__":
    main()
