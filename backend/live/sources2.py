"""Voyance II — second wave of keyless open data sources.

- Danish Maritime Authority live AIS (keyless public endpoints)
- Argo floats (NOAA PMEL / IFREMER ERDDAP tabledap)
- USGS Water Services instantaneous values
- OpenStreetMap Overpass (harbors / anchorages)
- Natural Earth coastline GeoJSON mirrors
- GEBCO WMS map service (bathymetric chart basemap + contours)
- EMODnet Geology WFS (seabed substrate)
- RainViewer public radar (animation frames, keyless)
- World Port Index (NGA) via community GeoJSON mirror
Every adapter degrades to an honest empty result; nothing is fabricated.
"""
from __future__ import annotations

import requests

from .sources import _get, cached

UA = {"User-Agent": "voyance2/2.0 (open-source maritime terminal)"}


# ---------- Danish Maritime Authority live AIS ----------

def dma_ais_vessels(limit: int = 200) -> list[dict]:
    """DMA live AIS (5-minute snapshot endpoints are keyless)."""

    def fetch():
        try:
            r = _get("https://api.ais.dma.dk/public/v1/aislist/S jutland", timeout=20)
            rows = r.json() if isinstance(r.json(), list) else []
            out = []
            for x in rows[:limit]:
                out.append({"mmsi": x.get("MMSI"), "lat": x.get("Latitude"),
                            "lon": x.get("Longitude"), "sog": x.get("SOG"),
                            "cog": x.get("COG"), "name": x.get("Name"),
                            "ship_type": x.get("ShipType")})
            return [x for x in out if x["lat"] is not None]
        except requests.RequestException:
            return []

    return cached("dma-ais", 60, fetch)


# ---------- Argo floats (keyless ERDDAP) ----------

def argo_floats(limit: int = 150) -> list[dict]:
    """Recent Argo float profile records — IFREMER GDAC via ERDDAP (verified non-empty)."""

    def fetch():
        try:
            # date is the index table's time column (no 'time' variable here)
            r = _get("https://erddap.ifremer.fr/erddap/tabledap/ArgoFloats-index.json"
                     "?file,date,latitude,longitude&date>=2026-09-01&distinct()",
                     timeout=60)
            tbl = r.json().get("table", {})
            cols = tbl.get("columnNames", [])
            i_lat, i_lon, i_file, i_date = (cols.index("latitude"), cols.index("longitude"),
                                            cols.index("file"), cols.index("date"))
            rows = tbl.get("rows", [])[:limit]
            return [{"file": row[i_file], "lat": row[i_lat], "lon": row[i_lon],
                     "date": row[i_date]} for row in rows]
        except requests.RequestException:
            return []

    return cached("argo", 3600, fetch)


def sar_granules(lat: float, lon: float, days: int = 4, limit: int = 6) -> list[dict]:
    """Sentinel-1 SAR GRD products over a point — Copernicus Data Space OData catalog
    (metadata search is keyless; imagery download needs free registration)."""
    import datetime as dt
    start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    poly = (f"geography'SRID=4326;POLYGON(({lon - 1} {lat - 1}, {lon + 1} {lat - 1}, "
            f"{lon + 1} {lat + 1}, {lon - 1} {lat + 1}, {lon - 1} {lat - 1}))'")
    flt = (f"Collection/Name eq 'SENTINEL-1' and contains(Name,'GRD') and "
           f"OData.CSC.Intersects(area={poly}) and "
           f"ContentDate/Start gt {start}")
    def fetch():
        try:
            r = _get("https://catalogue.dataspace.copernicus.eu/odata/v1/Products",
                     params={"$filter": flt, "$top": limit,
                             "$orderby": "ContentDate/Start desc"}, timeout=40)
            out = []
            for v in r.json().get("value", []):
                out.append({"name": v.get("Name"), "id": v.get("Id"),
                            "date": (v.get("ContentDate") or {}).get("Start"),
                            "size_mb": round((v.get("ContentLength") or 0) / 1e6, 1),
                            "browser": f"https://catalogue.dataspace.copernicus.eu/details?product={v.get('Id')}"})
            return out
        except requests.RequestException:
            return []

    return cached(f"sar-{lat:.1f}-{lon:.1f}", 1800, fetch)


# ---------- USGS Water Services (keyless instantaneous values) ----------

def usgs_water_stations(state: str = "fl", limit: int = 25) -> list[dict]:
    def fetch():
        try:
            r = _get("https://waterservices.usgs.gov/nwis/iv/", params={
                "stateCd": state, "parameterCd": "00060",  # discharge cfs
                "format": "json", "siteStatus": "active"}, timeout=30)
            vals = (r.json().get("value", {}).get("timeSeries", []))[:limit]
            out = []
            for t in vals:
                site = t.get("sourceInfo", {})
                loc = site.get("geoLocation", {}).get("geogLocation", {})
                out.append({"site": site.get("siteCode", [{}])[0].get("value"),
                            "name": site.get("siteName"),
                            "lat": loc.get("latitude"), "lon": loc.get("longitude"),
                            "discharge_cfs": (t.get("values", [{}])[0].get("value", [{}]) or [{}])[0].get("value")})
            return out
        except requests.RequestException:
            return []

    return cached(f"usgs-water-{state}", 1800, fetch)


# ---------- OpenStreetMap Overpass (keyless) ----------

def overpass_protected_areas(south: float, west: float, north: float, east: float,
                             limit: int = 60) -> dict:
    """Marine/terrestrial protected-area polygons from OSM (protect_class) with real
    geometries — Overpass `out geom` (ODbL). Marine ones carry marine=yes."""

    def fetch():
        q = ('[out:json][timeout:60];('
             f'way["protect_class"]({south},{west},{north},{east});'
             f'relation["protect_class"]({south},{west},{north},{east}););'
             f'out geom {limit};')
        try:
            r = requests.post("https://overpass-api.de/api/interpreter",
                              data={"data": q}, headers=UA, timeout=90)
            r.raise_for_status()
            feats = []
            for e in r.json().get("elements", [])[:limit]:
                tags = e.get("tags") or {}
                geom = e.get("geometry") or []
                coords = [[g["lon"], g["lat"]] for g in geom]
                if len(coords) < 3:
                    continue
                closed = coords[0] == coords[-1]
                feats.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon" if closed else "LineString",
                                 "coordinates": [coords] if closed else coords},
                    "properties": {"name": tags.get("name") or "protected area",
                                   "protect_class": tags.get("protect_class"),
                                   "marine": tags.get("marine", "no")},
                })
            return {"type": "FeatureCollection", "features": feats}
        except requests.RequestException:
            return {"type": "FeatureCollection", "features": []}

    return cached(f"prot-{south:.1f}-{west:.1f}-{north:.1f}-{east:.1f}", 86400, fetch)


def overpass_harbors(south: float, west: float, north: float, east: float) -> list[dict]:
    def fetch():
        q = (f"[out:json][timeout:40];"
             f"node[\"harbour\"]({south},{west},{north},{east});"
             f"node[\"seamark:harbour:category\"]({south},{west},{north},{east});out {300};")
        try:
            r = requests.post("https://overpass-api.de/api/interpreter",
                              data={"data": q}, headers=UA, timeout=60)
            r.raise_for_status()
            feats = r.json().get("elements", [])
            return [{"id": f.get("id"), "lat": f.get("lat"), "lon": f.get("lon"),
                     "name": (f.get("tags") or {}).get("name")}
                    for f in feats if f.get("lat")]
        except requests.RequestException:
            return []

    return cached(f"overpass-{south:.1f}-{west:.1f}", 86400, fetch)


# ---------- Natural Earth (keyless mirrors) ----------

def natural_earth_coastline(scale: str = "110m") -> dict:
    def fetch():
        url = (f"https://raw.githubusercontent.com/martynafford/natural-earth-geojson/master/"
               f"{scale}/physical/ne_{scale}_coastline.json")
        try:
            return _get(url, timeout=40).json()
        except requests.RequestException:
            return {"type": "FeatureCollection", "features": []}

    return cached(f"ne-coast-{scale}", 86400, fetch)


# ---------- GEBCO WMS (keyless bathymetric chart imagery) ----------

GEBCO_WMS_URL = ("https://wms.gebco.net/mapserv?request=GetMap&service=WMS&version=1.1.1"
                 "&format=image/png&STYLES=default&layers=GEBCO_LATEST_SUB_ICE_TOPO")


# ---------- EMODnet Geology WFS (keyless seabed substrate) ----------

def emodnet_geology(west: float, south: float, east: float, north: float, limit: int = 40) -> list[dict]:
    def fetch():
        try:
            r = _get("https://geo.vliz.be/geoserver/Emodnetnet/ows",
                     params={"service": "WFS", "version": "1.1.0", "request": "GetFeature",
                             "typeName": "Emodnetnet:seabed_substrate_1m",
                             "outputFormat": "application/json",
                             "bbox": f"{west},{south},{east},{north},urn:ogc:def:crs:EPSG::4326",
                             "count": limit}, timeout=40)
            feats = r.json().get("features", [])
            return [{"name": (f.get("properties") or {}).get("subtype"),
                     "coverage": (f.get("properties") or {}).get("coverage")}
                    for f in feats][:limit]
        except requests.RequestException:
            return []

    return cached(f"emodnet-geo-{west:.0f}-{south:.0f}", 86400, fetch)


# ---------- RainViewer public radar (keyless, animation frames) ----------

def rainviewer_frames() -> dict:
    def fetch():
        try:
            j = _get("https://api.rainviewer.com/public/weather-maps.json", timeout=15).json()
            host = j.get("host", "")
            past = j.get("radar", {}).get("past", [])[-6:]
            return {"host": host, "frames": [
                {"time": f.get("time"), "path": host + f.get("path", "")} for f in past]}
        except requests.RequestException:
            return {"host": "", "frames": []}

    return cached("rainviewer", 300, fetch)


# ---------- World Port Index (community mirror) ----------

def wpi_ports(limit: int = 4000) -> list[dict]:
    def fetch():
        for url in ("https://raw.githubusercontent.com/dwillis/nga-wpi/main/wpi.geojson",
                    "https://raw.githubusercontent.com/OpenHistoricalData/WPI/main/wpi.geojson"):
            try:
                feats = _get(url, timeout=60).json().get("features", [])
                return [{"index": (f.get("properties") or {}).get("INDEX_NO"),
                         "name": (f.get("properties") or {}).get("PORT_NAME"),
                         "lat": f["geometry"]["coordinates"][1],
                         "lon": f["geometry"]["coordinates"][0]}
                        for f in feats if f.get("geometry")][:limit]
            except requests.RequestException:
                continue
        return []

    return cached("wpi", 86400, fetch)
