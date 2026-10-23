"""Train LightGBM quantile models for remaining voyage time (ETA) + baselines.

Inputs : data/interim/features-*.parquet (real AIS + Open-Meteo reanalysis)
Outputs: models/eta-p10|p50|p90.txt, models/speed.txt
        reports/eval.json, reports/benchmark.json, reports/metrics_summary.json
Split  : temporal — train Jan+Apr, test Jul (real deployment realism).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).parent))
from geo import haversine_nm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
MODELS = ROOT / "models"
REPORTS = ROOT / "reports"

NUMERIC = [
    "lat", "lon", "remaining_distance_nm", "speed_kn", "sog_median_6h",
    "distance_traveled_nm", "elapsed_h", "wind_speed_10m", "wind_gusts_10m",
    "precipitation", "temperature_2m", "relative_humidity_2m",
    "wave_height", "wave_period", "swell_wave_height",
    "cos_wave_dir", "sin_wave_dir", "month_sin", "month_cos",
    "hour_sin", "hour_cos", "vessel_length", "vessel_draft",
    # physics-informed ratios: trees approximate dist/speed poorly as additive
    # splits, so hand them the quotient (standard ETA feature engineering)
    "hours_at_current_speed", "hours_at_type_speed", "hours_at_sog6",
]
CATEGORICAL = ["vessel_type_group", "region", "arr_port_idx", "dep_port_idx"]
MODEL_TYPES = ["cargo", "tanker", "passenger"]  # idealab segments: liner/tanker/dry-bulk + cruise
TARGET = "remaining_time_h"


def load_months(months: list[str]) -> pd.DataFrame:
    frames = [pd.read_parquet(INTERIM / f"features-{m}.parquet") for m in months]
    df = pd.concat(frames, ignore_index=True)
    df = df[df["weather_ok"] == True].copy()  # noqa: E712 — weather-joined rows only
    return df


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["speed_kn"] = df["sog"]  # AIS speed over ground
    wd = np.deg2rad(df.get("wave_direction", pd.Series(np.nan, index=df.index)))
    df["cos_wave_dir"] = np.cos(wd)
    df["sin_wave_dir"] = np.sin(wd)
    df["month"] = pd.to_datetime(df["ts"], utc=True).dt.month
    df["hour"] = pd.to_datetime(df["ts"], utc=True).dt.hour
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["vessel_type_group"] = df["vessel_type_group"].astype("category")
    df["region"] = df["region"].astype("category")
    return df


def X_of(df: pd.DataFrame) -> pd.DataFrame:
    return df[NUMERIC + CATEGORICAL].copy()


def baseline_speed_prior(df: pd.DataFrame) -> np.ndarray:
    """Great-circle distance / median speed of same vessel-type group."""
    med = df.groupby("vessel_type_group")["speed_kn"].median()
    eff = (med * 0.8).clip(3, 22)  # 80% of cruise median as effective speed
    return df["remaining_distance_nm"].to_numpy() / df["vessel_type_group"].map(eff).to_numpy()


def metrics(y, p):
    err = p - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    mape = float(np.mean(np.abs(err) / np.maximum(y, 0.5)))
    return {"mae_h": mae, "rmse_h": rmse, "mape": mape}


def breakdown(df: pd.DataFrame, y: np.ndarray, p: np.ndarray) -> dict:
    out = {}
    err = np.abs(p - y)
    for col, keys in (
        ("beaufort_class", None),
        ("region", None),
        ("vessel_type_group", None),
        ("dist_bucket", None),
    ):
        if col == "dist_bucket":
            b = pd.cut(df["remaining_distance_nm"], [0, 100, 300, 800, 2000, 1e9],
                       labels=["<100nm", "100-300nm", "300-800nm", "800-2000nm", ">2000nm"])
            groups = b
        else:
            groups = df[col]
        g = pd.DataFrame({"g": groups.astype(str).to_numpy(), "e": err}).groupby("g")["e"]
        out[col] = {str(k): {"mae_h": float(v.mean()), "n": int(v.count()),
                             "p90_err_h": float(v.quantile(0.9))}
                    for k, v in g}
    return out


def main():
    MODELS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    train = add_derived(load_months(["2024-01", "2024-04"]))
    test = add_derived(load_months(["2024-07"]))

    # commercial-vessel scope (tug/fishing loitering is not an ETA problem)
    train = train[train["vessel_type_group"].isin(MODEL_TYPES)].copy()
    test = test[test["vessel_type_group"].isin(MODEL_TYPES)].copy()

    # physics features; type medians come from TRAIN only (no test leakage)
    type_speed = train.groupby("vessel_type_group")["sog"].median().clip(2, 25)
    (MODELS / "type_speeds.json").write_text(json.dumps(type_speed.to_dict()))
    for d in (train, test):
        d["hours_at_current_speed"] = d["remaining_distance_nm"] / d["speed_kn"].clip(lower=1)
        d["hours_at_type_speed"] = d["remaining_distance_nm"] / d["vessel_type_group"].map(type_speed)
        d["hours_at_sog6"] = d["remaining_distance_nm"] / d["sog_median_6h"].clip(lower=1)

    # deterministic int codes shared by train/test/serving
    cat_levels = {c: sorted(set(train[c].astype(str)) | set(test[c].astype(str)))
                  for c in CATEGORICAL}
    for c in ("arr_port_idx", "dep_port_idx"):
        if "-1" not in cat_levels[c]:   # reserved "unknown port" bucket for serving
            cat_levels[c] = sorted(cat_levels[c] + ["-1"])
    (MODELS / "categoricals.json").write_text(json.dumps(cat_levels))
    for d in (train, test):
        for c, levels in cat_levels.items():
            d[c] = pd.Categorical(d[c].astype(str), categories=levels)
    print(f"model rows: train {len(train):,} test {len(test):,}")

    # voyage-level hash split so a voyage never straddles train/validate
    import hashlib
    h = train["voyage_id"].astype(str).map(
        lambda x: int(hashlib.md5(x.encode()).hexdigest(), 16) % 10)
    va = (h < 2).to_numpy()

    ytr, yva = train[TARGET].to_numpy()[~va], train[TARGET].to_numpy()[va]
    Xtr = X_of(train[~va]).reset_index(drop=True)
    Xva = X_of(train[va]).reset_index(drop=True)
    Xte = X_of(test).reset_index(drop=True)

    # GPU-trained served models: XGBoost CUDA quantile regression (RTX 4060)
    xgb_params = dict(objective="reg:quantileerror", tree_method="hist",
                      device="cuda", learning_rate=0.05, max_depth=8,
                      subsample=0.8, colsample_bytree=0.8,
                      min_child_weight=40, n_estimators=2000)
    models, preds, va_pred = {}, {}, {}
    for q, name in ((0.1, "p10"), (0.5, "p50"), (0.9, "p90")):
        m = xgb.XGBRegressor(**{**xgb_params, "quantile_alpha": q},
                             early_stopping_rounds=100, eval_metric="mae")
        m.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
        m.save_model(str(MODELS / f"eta-{name}.json"))
        models[name] = m
        preds[name] = m.predict(Xte)
        va_pred[name] = m.predict(Xva)
        print(f"{name}: best iter {m.best_iteration}")

    # Conformalized Quantile Regression (Romano et al., NeurIPS 2019):
    # widen the P10-P90 band by the (1-alpha) quantile of holdout
    # miscoverage so empirical coverage matches the nominal 80%.
    alpha = 0.20
    e_lo = va_pred["p10"] - yva
    e_hi = yva - va_pred["p90"]
    e = np.maximum(np.maximum(e_lo, e_hi), 0)
    q_level = np.ceil((len(e) + 1) * (1 - alpha)) / len(e)
    conf_q = float(np.quantile(e, min(q_level, 1.0)))
    (MODELS / "conformal_q.json").write_text(json.dumps({"q": conf_q, "alpha": alpha}))
    print(f"CQR adjustment: +{conf_q:.2f} h on each side (holdout n={len(e)})")
    preds["p10"], preds["p90"] = preds["p10"] - conf_q, preds["p90"] + conf_q
    va_pred["p10"], va_pred["p90"] = va_pred["p10"] - conf_q, va_pred["p90"] + conf_q

    # CPU LightGBM median model: published benchmark row vs the GPU model
    lgb_cpu = lgb.LGBMRegressor(objective="quantile", alpha=0.5, learning_rate=0.05,
                                num_leaves=63, min_child_samples=40,
                                feature_fraction=0.8, bagging_fraction=0.8,
                                bagging_freq=5, n_estimators=600, num_threads=14,
                                verbosity=-1)
    lgb_cpu.fit(Xtr, ytr, categorical_feature=CATEGORICAL)
    lgb_cpu.booster_.save_model(str(MODELS / "lightgbm-cpu-p50.txt"))
    lgb_pred = lgb_cpu.predict(Xte)

    # GPU-trained boosters don't populate the sklearn importance cache —
    # score directly from the booster on gain
    _scores = models["p50"].get_booster().get_score(importance_type="gain")
    imp = sorted(((f, float(_scores.get(f, 0.0))) for f in Xtr.columns),
                 key=lambda kv: -kv[1])[:15]
    # GPU-trained boosters don't populate the sklearn importance cache —
    # score directly from the booster on gain
    _scores = models["p50"].get_booster().get_score(importance_type="gain")
    imp = sorted(((f, float(_scores.get(f, 0.0))) for f in Xtr.columns),
                 key=lambda kv: -kv[1])[:15]
    spm = lgb.LGBMRegressor(objective="regression_l1", learning_rate=0.05,
                            num_leaves=63, n_estimators=500, num_threads=14,
                            verbosity=-1)
    sp_target = np.log1p(train["sog_median_6h"].to_numpy()[~va].clip(0.1, 40))
    spm.fit(Xtr.drop(columns=["sog_median_6h", "speed_kn"], errors="ignore"),
            sp_target, categorical_feature=CATEGORICAL)
    spm.booster_.save_model(str(MODELS / "speed.txt"))

    yte = test[TARGET].to_numpy()
    base = baseline_speed_prior(test)
    eval_json = {
        "model": "xgboost-cuda-quantile-eta v1.2.0",
        "hardware": "NVIDIA GeForce RTX 4060 Laptop GPU (CUDA, tree_method=hist, device=cuda)",
        "scope": "cargo + tanker + passenger vessels (NOAA AIS)",
        "trained_on": ["2024-01", "2024-04"],
        "test_on": ["2024-07"],
        "train_rows": int(len(train)), "test_rows": int(len(test)),
        "global": {"p50": metrics(yte, preds["p50"]),
                   "baseline_speed_prior": metrics(yte, base)},
        "benchmark": {
            "xgboost_gpu_p50": metrics(yte, preds["p50"]),
            "lightgbm_cpu_p50": metrics(yte, lgb_pred),
            "speed_prior_baseline": metrics(yte, base),
        },
        "coverage_p10_p90": float(np.mean((yte >= preds["p10"]) & (yte <= preds["p90"]))),
        "mean_interval_width_h": float(np.mean(preds["p90"] - preds["p10"])),
        "conformal_adjustment_h": conf_q,
        "feature_importance": [{"feature": f, "gain": round(g, 1)} for f, g in imp],
        "breakdown_p50": breakdown(test, yte, preds["p50"]),
        "breakdown_baseline": breakdown(test, yte, base),
    }
    ts = pd.to_datetime(test["ts"], utc=True)
    daily = pd.DataFrame({"d": ts.dt.date, "e": np.abs(preds["p50"] - yte)}) \
        .groupby("d")["e"].mean()
    eval_json["daily_mae"] = {str(k): float(v) for k, v in daily.items()}

    pd.DataFrame({
        "voyage_id": test["voyage_id"].to_numpy(), "ts": test["ts"].to_numpy(),
        "y": yte, "p10": preds["p10"], "p50": preds["p50"], "p90": preds["p90"],
    }).to_parquet(REPORTS / "test_predictions.parquet", index=False)

    # April predictions: second drift-monitor slice (April is in the training
    # months, but the monitor measures distribution + error behaviour, not fit)
    apr = add_derived(load_months(["2024-04"]))
    apr = apr[apr["vessel_type_group"].isin(MODEL_TYPES)].copy()
    for d in (apr,):
        d["hours_at_current_speed"] = d["remaining_distance_nm"] / d["speed_kn"].clip(lower=1)
        d["hours_at_type_speed"] = d["remaining_distance_nm"] / d["vessel_type_group"].map(type_speed)
        d["hours_at_sog6"] = d["remaining_distance_nm"] / d["sog_median_6h"].clip(lower=1)
        for c, levels in cat_levels.items():
            d[c] = pd.Categorical(d[c].astype(str), categories=levels)
    ap = models["p50"].predict(X_of(apr))
    pd.DataFrame({
        "voyage_id": apr["voyage_id"].to_numpy(), "ts": apr["ts"].to_numpy(),
        "y": apr[TARGET].to_numpy(), "p10": np.nan, "p50": ap, "p90": np.nan,
    }).to_parquet(REPORTS / "april_predictions.parquet", index=False)

    (REPORTS / "eval.json").write_text(json.dumps(eval_json, indent=2))
    print("XGB-GPU p50 MAE:", eval_json["global"]["p50"]["mae_h"], "h | LGBM-CPU:",
          eval_json["benchmark"]["lightgbm_cpu_p50"]["mae_h"], "h | baseline:",
          eval_json["global"]["baseline_speed_prior"]["mae_h"], "h")
    print("P10-P90 coverage:", eval_json["coverage_p10_p90"])


if __name__ == "__main__":
    main()
