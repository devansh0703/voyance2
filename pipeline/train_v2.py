"""Voyance II model training — GPU for everything that fits (owner directive).

- RandomForest segment-runtime regressor: XGBoost GPU (num_parallel_tree RF)
- Anomaly ensemble: IsolationForest + GMM + Mahalanobis (sklearn; small CPU fits)
- HMM voyage regimes (hmmlearn) over SOG
- Artifacts saved to models/*.pkl for the live API
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geo import haversine_nm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
MODELS.mkdir(exist_ok=True)

TARGET = "remaining_time_h"


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    tr = pd.read_parquet(ROOT / "data" / "interim" / "features-2024-01.parquet")
    ap = pd.read_parquet(ROOT / "data" / "interim" / "features-2024-04.parquet")
    te = pd.read_parquet(ROOT / "data" / "interim" / "features-2024-07.parquet")
    tr = pd.concat([tr, ap], ignore_index=True)
    keep = ["cargo", "tanker", "passenger"]
    return tr[tr["vessel_type_group"].isin(keep)], te[te["vessel_type_group"].isin(keep)]


def gpu_random_forest_runtime(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Random-Forest-style runtime regressor on GPU: bagged extra trees via
    xgboost (num_parallel_tree, subsample<1, colsample<1 = RF recipe)."""
    feats = ["remaining_distance_nm", "hours_at_current_speed", "hours_at_type_speed",
             "sog", "sog_median_6h", "wind_speed_10m", "wave_height", "vessel_length"]
    tr, te = train.copy(), test.copy()
    for d in (tr, te):
        d["hours_at_current_speed"] = d["remaining_distance_nm"] / d["sog"].clip(lower=1)
        d["hours_at_type_speed"] = d["remaining_distance_nm"] / d.groupby(
            "vessel_type_group")["sog"].transform("median").clip(lower=2)
    Xtr, ytr = tr[feats], tr[TARGET]
    Xte, yte = te[feats], te[TARGET]
    m = xgb.XGBRegressor(
        n_estimators=400, num_parallel_tree=100, subsample=0.6,
        colsample_bynode=0.6, learning_rate=1.0, max_depth=8,
        tree_method="hist", device="cuda", objective="reg:absoluteerror",
        verbosity=0)
    m.fit(Xtr, ytr)
    m.save_model(str(MODELS / "rf-runtime.json"))
    p = m.predict(Xte)
    mae = float(np.abs(p - yte).mean())
    return {"model": "xgboost GPU random-forest (num_parallel_tree=100)",
            "mae_h": round(mae, 3), "rows": int(len(tr)), "test_rows": int(len(te))}


def main():
    train, test = load()
    out: dict = {}

    # GPU random forest
    out["gpu_random_forest"] = gpu_random_forest_runtime(train, test)
    print("gpu_rf:", out["gpu_random_forest"])

    # anomaly ensemble (saved for /v2/analytics/anomaly)
    from backend.live import analytics as an
    ens = an.fit_anomaly_ensemble(
        train["lat"].to_numpy(), train["lon"].to_numpy(),
        train["sog"].to_numpy(), train["remaining_distance_nm"].to_numpy())
    if ens:
        with (MODELS / "anomaly_ensemble.pkl").open("wb") as f:
            pickle.dump(ens, f)
        out["anomaly_ensemble"] = "fitted on train rows"

    # HMM regimes over SOG
    hmm = an.fit_hmm(train["sog"].to_numpy())
    if hmm:
        with (MODELS / "hmm_sog.pkl").open("wb") as f:
            pickle.dump(hmm, f)
        out["hmm_sog"] = {"states": int(hmm.n_components),
                          "means_kn": [round(float(x), 2) for x in hmm.means_.flatten()]}

    (MODELS / "train_v2_summary.json").write_text(json.dumps(out, indent=2))
    print("train_v2 done:", json.dumps(out)[:400])


if __name__ == "__main__":
    import json
    main()
