"""Live open-data adapters — every source free, keyless, no signup.

- Digitraffic Finland Marine AIS (CC BY 4.0): live vessel positions, no key
- Open-Meteo forecast + marine (CC BY 4.0): live weather/waves
- NOAA National Weather Service api.weather.gov: US point forecasts
- NOAA NDBC realtime buoy text files: wave stations
- USGS Earthquake Hazards GeoJSON feeds
- OBIS + GBIF occurrence APIs (biodiversity overlays)
- NOAA ERDDAP (etopo180 grid): bathymetry depth sampling
- Marine Regions WFS: maritime protected-area polygons
"""
from __future__ import annotations

import time
from functools import lru_cache

import numpy as np
import requests

UA = {"User-Agent": "voyance2/2.0 (open-source maritime terminal)"}
TTL: dict[str, float] = {}
_CACHE: dict[str, object] = {}


def cached(key: str, ttl_s: int, fn):
    """Tiny TTL cache so the live API never hammers upstreams."""
    now = time.time()
    if key in _CACHE and now - TTL.get(key, 0) < ttl_s:
        return _CACHE[key]
    val = fn()
    _CACHE[key] = val
    TTL[key] = now
    return val


def _get(url: str, params: dict | None = None, timeout: int = 20):
    r = requests.get(url, params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r


# ---------- Live AIS: Digitraffic Finland (keyless, CC BY 4.0) ----------

def digitraffic_vessels(limit: int = 400) -> list[dict]:
    """Live AIS positions (Finnish waters). Returns compact vessel records."""

    def fetch():
        r = _get("https://meri.digitraffic.fi/api/ais/v1/locations", timeout=15)
        out = []
        for feat in r.json().get("features", [])[: limit * 3]:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            c = geom.get("coordinates", [None, None])
            if c[0] is None:
                continue
            out.append({
                "mmsi": props.get("mmsi"),
                "lat": round(c[1], 4), "lon": round(c[0], 4),
                "sog": props.get("sog"), "cog": props.get("cog"),
                "heading": props.get("heading"),
                "ts": props.get("timestampExternal"),
            })
            if len(out) >= limit:
                break
        return out

    return cached("ais", 20, fetch)


def digitraffic_vessel_metadata() -> dict[int, dict]:
    def fetch():
        r = _get("https://meri.digitraffic.fi/api/ais/v1/vessels", timeout=20)
        return {v.get("mmsi"): v for v in r.json() if v.get("mmsi")}

    return cached("ais-meta", 3600, fetch)


# ---------- Weather: Open-Meteo (forecast, keyless) ----------

FORECAST_VARS = ["wind_speed_10m", "wind_gusts_10m", "precipitation",
                 "temperature_2m", "relative_humidity_2m"]


def open_meteo_forecast(lat: float, lon: float) -> dict:
    def fetch():
        r = _get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "current": ",".join(FORECAST_VARS),
            "wind_speed_unit": "kn", "timezone": "UTC",
        }, timeout=15)
        return r.json().get("current", {})

    return cached(f"omf-{lat:.2f}-{lon:.2f}", 600, fetch)


def open_meteo_marine(lat: float, lon: float) -> dict:
    def fetch():
        r = _get("https://marine-api.open-meteo.com/v1/marine", params={
            "latitude": lat, "longitude": lon,
            "current": "wave_height,wave_period,wave_direction,swell_wave_height",
            "timezone": "UTC", "length_unit": "metric",
        }, timeout=15)
        return r.json().get("current", {})

    return cached(f"omm-{lat:.2f}-{lon:.2f}", 600, fetch)


# ---------- NOAA NWS point forecast (keyless) ----------

def nws_point_forecast(lat: float, lon: float) -> dict:
    def fetch():
        try:
            p = _get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}",
                     timeout=15).json()
            url = p.get("properties", {}).get("forecast")
            if not url:
                return {"available": False}
            f = _get(url, timeout=15).json()
            periods = f.get("properties", {}).get("periods", [])[:8]
            return {"available": True,
                    "periods": [{"name": x.get("name"), "temp_c": (x.get("temperature", 0) - 32) * 5 / 9,
                                 "wind_kn": x.get("windSpeed"), "dir": x.get("windDirection"),
                                 "short": x.get("shortForecast")} for x in periods]}
        except requests.RequestException:
            return {"available": False}

    return cached(f"nws-{lat:.2f}-{lon:.2f}", 1800, fetch)


# ---------- NOAA NDBC realtime buoys (keyless text files) ----------

NDBC_STATIONS = ["41009", "42035", "44025", "46042", "46013", "51101", "42001", "44017", "46050"]


def ndbc_station(station: str) -> dict | None:
    def fetch():
        try:
            txt = _get(f"https://www.ndbc.noaa.gov/data/realtime2/{station}.txt",
                       timeout=12).text.splitlines()
            hdr = txt[0].split()
            vals = txt[2].split()  # most recent
            row = dict(zip(hdr, vals))
            return {"station": station, "year": row.get("#YY"), "month": row.get("MM"),
                    "day": row.get("DD"), "hour": row.get("hh"),
                    "wind_speed_ms": row.get("WSPD"), "gust_ms": row.get("GST"),
                    "wave_height_m": row.get("WVHT"), "dominant_period_s": row.get("DPD"),
                    "sea_temp_c": row.get("WTMP")}
        except requests.RequestException:
            return None

    return cached(f"ndbc-{station}", 1800, fetch)


def ndbc_all() -> list[dict]:
    return [s for s in (ndbc_station(x) for x in NDBC_STATIONS) if s]


# ---------- USGS earthquakes (keyless GeoJSON) ----------

def usgs_quakes(day: bool = True) -> list[dict]:
    def fetch():
        url = ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
               + ("all_day" if day else "all_hour") + ".geojson")
        feats = _get(url, timeout=15).json().get("features", [])
        return [{"mag": f["properties"]["mag"], "place": f["properties"]["place"],
                 "ts": f["properties"]["time"],
                 "lon": f["geometry"]["coordinates"][0],
                 "lat": f["geometry"]["coordinates"][1],
                 "depth_km": f["geometry"]["coordinates"][2]}
                for f in feats if f.get("geometry")]

    return cached("quakes", 300, fetch)


# ---------- OBIS / GBIF (keyless occurrence APIs) ----------

def obis_occurrences(lat: float, lon: float, radius_deg: float = 1.0, size: int = 50) -> list[dict]:
    def fetch():
        try:
            r = _get("https://api.obis.org/v3/occurrence", params={
                "geometry": f"POLYGON(({lon - radius_deg} {lat - radius_deg}, {lon + radius_deg} {lat - radius_deg}, "
                            f"{lon + radius_deg} {lat + radius_deg}, {lon - radius_deg} {lat + radius_deg}, {lon - radius_deg} {lat - radius_deg}))",
                "size": size}, timeout=20)
            return [{"scientificName": f.get("scientificName"),
                     "lat": f.get("decimalLatitude"), "lon": f.get("decimalLongitude"),
                     "date": f.get("eventDate")}
                    for f in r.json().get("results", [])]
        except requests.RequestException:
            return []

    return cached(f"obis-{lat:.1f}-{lon:.1f}", 86400, fetch)


def gbif_occurrences(lat: float, lon: float, radius_deg: float = 0.5, size: int = 50) -> list[dict]:
    def fetch():
        try:
            r = _get("https://api.gbif.org/v1/occurrence/search", params={
                "decimalLatitude": f"{lat},{lat + radius_deg}",
                "decimalLongitude": f"{lon},{lon + radius_deg}",
                "limit": size}, timeout=20)
            return [{"scientificName": f.get("species", f.get("scientificName")),
                     "lat": f.get("decimalLatitude"), "lon": f.get("decimalLongitude")}
                    for f in r.json().get("results", [])]
        except requests.RequestException:
            return []

    return cached(f"gbif-{lat:.1f}-{lon:.1f}", 86400, fetch)


# ---------- Bathymetry: EMODnet 2018 DTM via OpenTopoData (keyless, batch) ----------

def bathy_depths(lats: list[float], lons: list[float]) -> list[float | None]:
    """Depth (m, positive down) per point. OpenTopoData free tier: 100 locs/call, 1 req/s."""
    if not lats:
        return []
    return etopo1_depths(lats, lons)


def etopo1_depths(lats: list[float], lons: list[float]) -> list[float | None]:
    """Global ETOPO1 depths via OpenTopoData (100 locs/call, 1 req/s). No coverage holes."""
    out: list[float | None] = []
    for i in range(0, len(lats), 100):
        chunk = [f"{a:.5f},{b:.5f}" for a, b in zip(lats[i:i + 100], lons[i:i + 100])]
        try:
            r = _get("https://api.opentopodata.org/v1/etopo1",
                     params={"locations": "|".join(chunk)}, timeout=40)
            for res in r.json().get("results", []):
                z = res.get("elevation")
                out.append(None if z is None else float(z))
        except requests.RequestException:
            out.extend([None] * len(chunk))
        if i + 100 < len(lats):
            time.sleep(1.1)   # free-tier 1 req/s
    return out


# ---------- Marine Regions MPAs (keyless WFS) ----------

def marine_regions_eez(south: float = 58.0, west: float = 14.0,
                       north: float = 66.0, east: float = 31.0,
                       limit: int = 20) -> dict:
    """Exclusive Economic Zone jurisdiction polygons — Marine Regions WFS (CC BY 4.0)."""
    def fetch():
        try:
            r = _get("https://geo.vliz.be/geoserver/MarineRegions/ows",
                     params={"service": "WFS", "version": "1.1.0", "request": "GetFeature",
                             "typeName": "MarineRegions:eez", "outputFormat": "application/json",
                             "bbox": f"{west},{south},{east},{north},urn:ogc:def:crs:EPSG::4326",
                             "count": limit, "srsName": "urn:ogc:def:crs:EPSG::4326"},
                     timeout=60)
            feats = r.json().get("features", [])
            for f in feats:
                props = f.get("properties") or {}
                props["name"] = props.get("geonameid") and props.get("mrgid") and props.get("name") or props.get("mrgid")
            return {"type": "FeatureCollection", "features": feats[:limit]}
        except requests.RequestException:
            return {"type": "FeatureCollection", "features": []}

    return cached(f"eez-{south:.0f}-{west:.0f}-{north:.0f}-{east:.0f}", 86400, fetch)


def marine_regions_mpas(south: float = 58.0, west: float = 14.0,
                        north: float = 66.0, east: float = 31.0,
                        limit: int = 30) -> dict:
    """Protected-area polygons via OSM Overpass (keyless; Marine Regions WFS has no
    eez_mpa layer — documented in sources2.overpass_protected_areas)."""
    from . import sources2
    return sources2.overpass_protected_areas(south, west, north, east, limit)
