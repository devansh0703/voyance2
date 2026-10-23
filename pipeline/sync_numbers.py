"""Sync README/model-card headline numbers from reports/eval.json (single source of truth)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
e = json.loads((ROOT / "reports" / "eval.json").read_text())

gpu = e["benchmark"]["xgboost_gpu_p50"]["mae_h"]
cpu = e["benchmark"]["lightgbm_cpu_p50"]["mae_h"]
prior = e["benchmark"]["speed_prior_baseline"]["mae_h"]
cov = e["coverage_p10_p90"] * 100
imp = 100 * (1 - gpu / prior)

readme = ROOT / "README.md"
t = readme.read_text()
t = t.replace("**6.59**", f"**{gpu:.2f}**").replace("**7.74**", f"**{cpu:.2f}**")
t = t.replace("**7.42**", f"**{prior:.2f}**")
readme.write_text(t)

card = ROOT / "reports" / "model-card.md"
c = card.read_text()
c = c.replace("XGBoost GPU 6.59", f"XGBoost GPU {gpu:.2f}")
c = c.replace("LightGBM CPU 7.74", f"LightGBM CPU {cpu:.2f}")
c = c.replace("speed prior 7.42", f"speed prior {prior:.2f}")
c = re.sub(r"P10–P90 empirical coverage after CQR: see", "P10–P90 empirical coverage after CQR: see", c)
card.write_text(c)
print(f"synced: gpu={gpu:.2f} cpu={cpu:.2f} prior={prior:.2f} coverage={cov:.1f}% improvement={imp:.1f}%")
