"""Voyance FastAPI service — serves quantile ETA predictions, metrics, drift.

Real artifacts only: models from models/, metrics from reports/. If artifacts
are missing the endpoints return 503 with a pointer to the pipeline command.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import xgboost as xgb
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
REPORTS = ROOT / "reports"
WEB_DIST = ROOT / "web" / "dist"

NUMERIC = [
    "lat", "lon", "remaining_distance_nm", "speed_kn", "sog_median_6h",
    "distance_traveled_nm", "elapsed_h", "wind_speed_10m", "wind_gusts_10m",
    "precipitation", "temperature_2m", "relative_humidity_2m",
    "wave_height", "wave_period", "swell_wave_height",
    "cos_wave_dir", "sin_wave_dir", "month_sin", "month_cos",
    "hour_sin", "hour_cos", "vessel_length", "vessel_draft",
    "hours_at_current_speed", "hours_at_type_speed", "hours_at_sog6",
]
CATEGORICAL = ["vessel_type_group", "region", "arr_port_idx", "dep_port_idx"]
BOUNDS = [1, 3, 6, 10, 16, 21, 27, 33, 40, 47, 55, 63]

app = FastAPI(
    title="Voyance API",
    version="1.0.0",
    description="Open-source maritime voyage intelligence: quantile ETA on AIS + ERA5.",
)
Instrumentator().instrument(app).expose(app)

from backend.live.service import router as live_router, _usage  # noqa: E402
app.include_router(live_router)


class _UsageMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            _usage["requests"] += 1
            p = scope.get("path", "")
            if "predict" in p:
                _usage["predict"] += 1
            if p.startswith("/v2/live"):
                _usage["live"] += 1
            if p.startswith("/v2/analytics"):
                _usage["analytics"] += 1
        await self.app(scope, receive, send)


app.add_middleware(_UsageMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class PredictReq(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    dest_lat: float = Field(..., ge=-90, le=90)
    dest_lon: float = Field(..., ge=-180, le=180)
    vessel_type_group: str = "cargo"
    dep_port_idx: int | None = None
    arr_port_idx: int | None = None
    vessel_length: float | None = None
    vessel_draft: float | None = None
    sog: float | None = None
    sog_median_6h: float | None = None
    distance_traveled_nm: float | None = None
    elapsed_h: float | None = None
    month: int = Field(..., ge=1, le=12)
    hour: int = Field(..., ge=0, le=23)
    wind_speed_10m: float | None = None
    wind_gusts_10m: float | None = None
    precipitation: float | None = None
    temperature_2m: float | None = None
    relative_humidity_2m: float | None = None
    wave_height: float | None = None
    wave_period: float | None = None
    wave_direction: float | None = None
    swell_wave_height: float | None = None
    region: str | None = None


class PredictResp(BaseModel):
    p50_h: float
    p10_h: float
    p90_h: float
    remaining_distance_nm: float
    beaufort_class: int
    model_version: str


@lru_cache(maxsize=1)
def load_type_speeds() -> dict[str, float]:
    p = MODELS / "type_speeds.json"
    return json.loads(p.read_text()) if p.exists() else {}


@lru_cache(maxsize=1)
def load_conformal_q() -> float:
    p = MODELS / "conformal_q.json"
    return float(json.loads(p.read_text())["q"]) if p.exists() else 0.0


@lru_cache(maxsize=1)
def load_cat_levels() -> dict[str, list[str]]:
    p = MODELS / "categoricals.json"
    return json.loads(p.read_text()) if p.exists() else {}


@lru_cache(maxsize=1)
def load_models() -> dict[str, xgb.XGBRegressor]:
    out = {}
    for name in ("p10", "p50", "p90"):
        p = MODELS / f"eta-{name}.json"
        if not p.exists():
            raise FileNotFoundError(f"missing {p}")
        m = xgb.XGBRegressor()
        m.load_model(str(p))
        out[name] = m
    return out


def haversine_nm(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * 3440.065 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def beaufort(ws: float) -> int:
    return int(np.searchsorted(BOUNDS, ws, side="right"))


@app.get("/health")
def health():
    detail = None
    try:
        load_models()
        model_ok = True
    except FileNotFoundError as e:
        model_ok = False
        detail = str(e)
    return {"status": "ok" if model_ok else "degraded", "models": model_ok,
            "detail": detail if not model_ok else None}


@app.post("/v1/predict", response_model=PredictResp)
def predict(req: PredictReq):
    try:
        models = load_models()
    except FileNotFoundError as e:
        raise HTTPException(503, f"model artifacts missing — run `make train` ({e})")

    rem = float(haversine_nm(req.lat, req.lon, req.dest_lat, req.dest_lon))
    wd = np.deg2rad(req.wave_direction) if req.wave_direction is not None else np.nan
    row = {
        "lat": req.lat, "lon": req.lon, "remaining_distance_nm": rem,
        "speed_kn": req.sog if req.sog is not None else 10.0,
        "sog_median_6h": req.sog_median_6h if req.sog_median_6h is not None else req.sog or 10.0,
        "distance_traveled_nm": req.distance_traveled_nm or 0.0,
        "elapsed_h": req.elapsed_h or 0.0,
        "wind_speed_10m": req.wind_speed_10m or 0.0,
        "wind_gusts_10m": req.wind_gusts_10m or 0.0,
        "precipitation": req.precipitation or 0.0,
        "temperature_2m": req.temperature_2m if req.temperature_2m is not None else 15.0,
        "relative_humidity_2m": req.relative_humidity_2m or 70.0,
        "wave_height": req.wave_height or 0.0,
        "wave_period": req.wave_period or 0.0,
        "swell_wave_height": req.swell_wave_height or 0.0,
        "cos_wave_dir": float(np.cos(wd)) if np.isfinite(wd) else 0.0,
        "sin_wave_dir": float(np.sin(wd)) if np.isfinite(wd) else 0.0,
        "month_sin": float(np.sin(2 * np.pi * req.month / 12)),
        "month_cos": float(np.cos(2 * np.pi * req.month / 12)),
        "hour_sin": float(np.sin(2 * np.pi * req.hour / 24)),
        "hour_cos": float(np.cos(2 * np.pi * req.hour / 24)),
        "vessel_length": req.vessel_length if req.vessel_length is not None else np.nan,
        "vessel_draft": req.vessel_draft if req.vessel_draft is not None else np.nan,
        "vessel_type_group": req.vessel_type_group,
        "region": req.region or "other_us_waters",
        "dep_port_idx": str(req.dep_port_idx) if req.dep_port_idx is not None else "-1",
        "arr_port_idx": str(req.arr_port_idx) if req.arr_port_idx is not None else "-1",
    }
    row["hours_at_current_speed"] = rem / max(row["speed_kn"], 1.0)
    ts_med = load_type_speeds().get(req.vessel_type_group, 8.0)
    row["hours_at_type_speed"] = rem / max(ts_med, 2.0)
    row["hours_at_sog6"] = rem / max(row["sog_median_6h"], 1.0)
    levels = load_cat_levels()
    X = pd.DataFrame([{c: str(row[c]) if c in CATEGORICAL else row[c]
                       for c in NUMERIC + CATEGORICAL}])
    for c in CATEGORICAL:
        X[c] = pd.Categorical(X[c], categories=levels[c])
    p10, p50, p90 = (float(models[k].predict(X)[0]) for k in ("p10", "p50", "p90"))
    q = load_conformal_q()
    p10, p90 = p10 - q, p90 + q
    p10 = max(p10, 0.1)  # remaining time is non-negative
    if not (p10 <= p50 <= p90):
        p10, p90 = min(p10, p90), max(p10, p90)
        p10 = max(p10, 0.1)
    ws = row["wind_speed_10m"]
    return PredictResp(
        p50_h=round(p50, 3), p10_h=round(p10, 3), p90_h=round(p90, 3),
        remaining_distance_nm=round(rem, 2), beaufort_class=beaufort(ws),
        model_version="xgboost-cuda-quantile-eta v1.2.0",
    )


@app.get("/v1/metrics")
def metrics():
    p = REPORTS / "eval.json"
    if not p.exists():
        raise HTTPException(503, "evaluation missing — run `make train`")
    return json.loads(p.read_text())


@app.get("/v1/drift")
def drift():
    p = REPORTS / "drift_summary.json"
    if not p.exists():
        raise HTTPException(503, "drift reports missing — run `make drift`")
    return json.loads(p.read_text())


@app.get("/v1/voyages")
def voyages(region: str | None = None, type: str | None = None, limit: int = 200):
    p = REPORTS / "voyages.json"
    if not p.exists():
        raise HTTPException(503, "voyage export missing — run `make web-data`")
    data = json.loads(p.read_text())
    items = data["voyages"]
    if region:
        items = [v for v in items if v.get("region") == region]
    if type:
        items = [v for v in items if v.get("vessel_type_group") == type]
    return {"count": len(items), "voyages": items[:limit]}


# ---- static web (production) ----
if WEB_DIST.exists():
    if (WEB_DIST / "data").exists():
        app.mount("/data", StaticFiles(directory=WEB_DIST / "data"), name="data")

    @app.get("/")
    @app.get("/dashboard")
    @app.get("/live")
    @app.get("/analytics")
    @app.get("/research")
    @app.get("/docs")
    def spa():
        return FileResponse(WEB_DIST / "index.html")

    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
