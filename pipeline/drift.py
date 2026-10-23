"""Drift monitoring: monthly slices vs the January baseline.

Evidently DataDrift reports (per-feature PSI/KS) + real model MAE ratio from
saved test predictions. Alert: any feature PSI > 0.2 OR weekly MAE ratio > 1.25.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

FEATURES = [
    "remaining_distance_nm", "sog", "sog_median_6h", "wind_speed_10m",
    "wind_gusts_10m", "precipitation", "wave_height", "wave_period",
    "temperature_2m", "relative_humidity_2m",
]


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    qs = np.nanquantile(expected, np.linspace(0, 1, bins + 1))
    qs[0], qs[-1] = -np.inf, np.inf
    e = np.histogram(expected, qs)[0] / max(len(expected), 1)
    a = np.histogram(actual, qs)[0] / max(len(actual), 1)
    e, a = np.clip(e, 1e-6, None), np.clip(a, 1e-6, None)
    return float(np.sum((a - e) * np.log(a / e)))


def main():
    from evidently.legacy.report import Report
    from evidently.legacy.metric_preset import DataDriftPreset

    base = pd.read_parquet(INTERIM / "features-2024-01.parquet")
    base = base[base["vessel_type_group"].isin(["cargo", "tanker", "passenger"])]
    preds = pd.concat([
        pd.read_parquet(REPORTS / "test_predictions.parquet"),
        pd.read_parquet(REPORTS / "april_predictions.parquet"),
    ], ignore_index=True)
    preds["month"] = pd.to_datetime(preds["ts"], utc=True).dt.strftime("%Y-%m")

    base_mae = float(preds[preds["month"] == "2024-07"].groupby("month")["y"].size().iloc[0] * 0)  # placeholder replaced below
    # baseline MAE = mean |y - p50| for the monitor reference chosen as the
    # model's own test performance — reported per slice vs the first monitor
    out = []
    for month in ("2024-04", "2024-07"):
        mon = pd.read_parquet(INTERIM / f"features-{month}.parquet")
        mon = mon[mon["vessel_type_group"].isin(["cargo", "tanker", "passenger"])]
        m_pred = preds[preds["month"] == month]
        if m_pred.empty:
            continue
        mae = float((m_pred["p50"] - m_pred["y"]).abs().mean())

        rep = Report(metrics=[DataDriftPreset(columns=FEATURES)])
        rep.run(current_data=mon[FEATURES], reference_data=base[FEATURES])
        rep_html = REPORTS / "drift" / f"{month}.html"
        rep_html.parent.mkdir(exist_ok=True)
        rep.save_html(str(rep_html))
        ej = rep.as_dict()
        drifted = []
        for m in ej.get("metrics", []):
            res = m.get("result", {})
            for col, d in (res.get("drift_by_columns") or {}).items():
                if d.get("drift_detected"):
                    v = d.get("psi") or d.get("stattest_value") or 0
                    if v and v > 0.2:
                        drifted.append({"feature": col, "psi": round(float(v), 3)})
        # own PSI for a machine-readable cross-check
        own = {f: round(psi(base[f].dropna().to_numpy(), mon[f].dropna().to_numpy()), 3)
               for f in FEATURES}
        ref_mae = json.loads((REPORTS / "eval.json").read_text())["global"]["p50"]["mae_h"]
        for row in out:
            row["mae_ratio_vs_test_overall"] = round(row["mae_h"] / ref_mae, 2)
        alert = bool(drifted) or (mae / ref_mae > 1.25 if mae else False)
        out.append({
            "slice": month, "n": int(len(mon)), "mae_h": round(mae, 2),
            "mae_ratio_vs_test_overall": None,
            "drifted_features": drifted, "psi_own": own, "alert": alert,
        })
        print(f"  {month}: n={len(mon):,} mae={mae:.2f} drifted={len(drifted)} alert={alert}")

    summary = {
        "baseline": "2024-01 (feature distribution reference)",
        "monitor": ["2024-04", "2024-07"],
        "reference_mae_h": None,
        "weeks": out,
        "reference_mae_h": json.loads((REPORTS / "eval.json").read_text())["global"]["p50"]["mae_h"],
        "n_drifted_features_total": len({d["feature"] for w in out for d in w["drifted_features"]}),
    }
    (REPORTS / "drift_summary.json").write_text(json.dumps(summary, indent=2))
    print("drift summary written")


if __name__ == "__main__":
    main()
