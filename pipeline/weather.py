"""Open-Meteo historical weather fetcher (ERA5 atmosphere + ERA5 marine waves).

Free, keyless, CC BY 4.0. Batches up to 1,000 grid cells per call and caches
every response to disk so reruns never re-bill the daily quota.
Docs: https://open-meteo.com/en/docs/historical-weather-api
      https://open-meteo.com/en/docs/marine-weather-api
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "interim" / "weather"
CACHE.mkdir(parents=True, exist_ok=True)

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
MARINE = "https://marine-api.open-meteo.com/v1/marine"
ATMOS_VARS = ["wind_speed_10m", "wind_gusts_10m", "precipitation",
              "temperature_2m", "relative_humidity_2m"]
MARINE_VARS = ["wave_height", "wave_period", "wave_direction", "swell_wave_height"]
SNAP = 0.5  # degrees per weather cell (memory/quota friendly, ERA5 is 0.25)


def snap(lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return (np.floor(lat / SNAP) * SNAP + SNAP / 2,
            np.floor(lon / SNAP) * SNAP + SNAP / 2)


def cell_key(lat: float, lon: float, month: str) -> str:
    return f"{lat:.2f}_{lon:.2f}_{month}"


def fetch_cells(cells: list[tuple[float, float]], month: str,
                start: str, end: str) -> dict[str, dict]:
    """Fetch hourly atmosphere+marine for each (lat, lon) cell for a month.

    Returns mapping cell_key -> {"hourly": {var: [...]}, ...} (atmos + marine merged).
    """
    out: dict[str, dict] = {}
    todo = []
    for lat, lon in cells:
        ck = cell_key(lat, lon, month)
        f = CACHE / f"{ck}.json"
        if f.exists():
            out[ck] = json.loads(f.read_text())
        else:
            todo.append((lat, lon, ck))
    if not todo:
        return out

    for kind, url, vars_ in (("atmos", ARCHIVE, ATMOS_VARS), ("marine", MARINE, MARINE_VARS)):
        for i in range(0, len(todo), 500):
            batch = todo[i:i + 500]
            lats = ",".join(f"{c[0]:.2f}" for c in batch)
            lons = ",".join(f"{c[1]:.2f}" for c in batch)
            params = {
                "latitude": lats, "longitude": lons,
                "start_date": start, "end_date": end,
                "hourly": ",".join(vars_),
                "wind_speed_unit": "kn", "timezone": "UTC",
            }
            if kind == "marine":
                params["length_unit"] = "metric"
            for attempt in range(5):
                try:
                    r = requests.get(url, params=params, timeout=120)
                    if r.status_code == 429:
                        wait = 120 * (attempt + 1)
                        print(f"  rate limited; sleeping {wait}s", flush=True)
                        time.sleep(wait)
                        continue
                    r.raise_for_status()
                    data = r.json()
                    break
                except requests.RequestException as e:
                    print(f"  retry {attempt + 1}: {e}", flush=True)
                    time.sleep(20 * (attempt + 1))
            else:
                raise RuntimeError(f"{kind} fetch failed for batch {i}")
            arr = data if isinstance(data, list) else [data]
            for (lat, lon, ck), d in zip(batch, arr):
                f = CACHE / f"{ck}.json"
                merged = json.loads(f.read_text()) if f.exists() else {}
                h = merged.setdefault("hourly", {})
                h.update(d.get("hourly", {}))
                merged["elevation"] = d.get("elevation")
                f.write_text(json.dumps(merged))
                out[ck] = merged
            print(f"  {kind} batch {i // 500}: {len(batch)} cells", flush=True)
            time.sleep(1.5)  # be polite
    return out


def weather_table(cells: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for ck, d in cells.items():
        h = d.get("hourly", {})
        if not h.get("time"):
            continue
        n = len(h["time"])
        row = {"cell": ck, "time": h["time"]}
        for var in ATMOS_VARS + MARINE_VARS:
            vals = h.get(var)
            row[var] = (np.asarray(vals, dtype=np.float64)
                        if vals and len(vals) == n else np.full(n, np.nan))
        rows.append(pd.DataFrame(row))
    if not rows:
        return pd.DataFrame()
    wide = pd.concat(rows, ignore_index=True)
    wide["time"] = pd.to_datetime(wide.pop("time").str.slice(0, 13), utc=True,
                                  format="%Y-%m-%dT%H")
    return wide.set_index(["cell", "time"])


def attach_weather(samples: pd.DataFrame, month: str) -> pd.DataFrame:
    """Join hourly weather onto voyage samples by snapped cell + hour."""
    lat = samples["lat"].to_numpy(np.float64)
    lon = samples["lon"].to_numpy(np.float64)
    clat, clon = snap(lat, lon)
    samples = samples.copy()
    samples["cell"] = [f"{a:.2f}_{b:.2f}_{month}" for a, b in zip(clat, clon)]
    ts = pd.to_datetime(samples["ts"], utc=True).dt.floor("h")
    samples["hour"] = ts

    month_start = pd.Timestamp(f"{month}-01", tz="UTC")
    month_end = month_start + pd.offsets.MonthEnd(0)
    cells = sorted({tuple(c.split("_")[:2]) for c in samples["cell"].unique()})
    cells = [(float(a), float(b)) for a, b in cells]
    print(f"  fetching weather for {len(cells)} cells ({month})", flush=True)
    data = fetch_cells(cells, month, month_start.strftime("%Y-%m-%d"),
                       month_end.strftime("%Y-%m-%d"))
    wide = weather_table(data)
    if wide.empty:
        samples["weather_ok"] = False
        return samples

    wide = wide.reset_index()
    merged = samples.merge(
        wide, left_on=["cell", "hour"], right_on=["cell", "time"], how="left")
    merged["weather_ok"] = merged["wind_speed_10m"].notna()
    merged["beaufort_class"] = None
    return merged


def main():
    month = sys.argv[1] if len(sys.argv) > 1 else "2024-07"
    samples = pd.read_parquet(ROOT / "data" / "interim" / f"samples-{month}.parquet")
    out = attach_weather(samples, month)
    from geo import beaufort_from_wind_kn
    ok = out["wind_speed_10m"].notna()
    out.loc[ok, "beaufort_class"] = beaufort_from_wind_kn(
        out.loc[ok, "wind_speed_10m"].to_numpy())
    out.to_parquet(ROOT / "data" / "interim" / f"features-{month}.parquet", index=False)
    print(f"{month}: weather_ok={out['weather_ok'].mean():.3f}")


if __name__ == "__main__":
    main()
