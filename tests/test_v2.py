"""Voyance II algorithm tests — offline, deterministic."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from backend.live import analytics as an  # noqa: E402
from backend.live import kinematics as k  # noqa: E402


def test_dcpa_head_on_is_zero():
    # two vessels driving straight at each other along the same line
    dcpa, tcpa = k.dcpa_tcpa(60.0, 25.0, 0, 10, 60.2, 25.0, 180, 10)
    assert dcpa == pytest.approx(0.0, abs=0.05)
    assert tcpa is not None and tcpa > 0


def test_dcpa_parallel_never_close():
    dcpa, tcpa = k.dcpa_tcpa(60.0, 25.0, 90, 10, 60.0, 25.05, 90, 10)
    assert dcpa == pytest.approx(1.62, abs=0.2)   # 0.05° lon ≈ 1.6 nm at 60°N
    assert tcpa is None


def test_fuzzy_cri_monotonic_in_tcpa():
    near = k.fuzzy_cri(0.3, 2.0, 12)
    far = k.fuzzy_cri(0.3, 14.0, 12)
    assert near > far
    assert k.fuzzy_cri(6.0, 40.0, 12) == 0.0


def test_goodwin_stanton_ellipse_contains_close_contact():
    assert k.in_goodwin_stanton(0.1, 0.0, 12)          # dead ahead, very close
    assert not k.in_goodwin_stanton(3.0, 90.0, 12)     # abeam, far


def test_name_similarity_orders_correctly():
    a = k.name_similarity("Helsinki", "Helsinki (VUOSAARI)")
    b = k.name_similarity("Helsinki", "Casablanca")
    assert a["jaro_winkler"] > b["jaro_winkler"]
    assert a["levenshtein_ratio"] > b["levenshtein_ratio"]


def test_littles_and_mmc():
    assert an.littles_law(3.0, 2.0) == pytest.approx(6.0)
    m = an.mmc_metrics(1.5, 1.0, 2)
    assert m["utilization"] == pytest.approx(0.75)
    assert m["mean_wait_h"] > 0
    assert an.mmc_metrics(3.0, 1.0, 2)["unstable"] is True


def test_ittc_cf_reasonable():
    cf = an.ittc_friction_coeff(1e8)
    assert 0.0012 < cf < 0.0025


def test_fuel_grows_with_wave_height():
    calm = an.fuel_consumption_t_per_day(12, 0.0, 180, 50000)
    rough = an.fuel_consumption_t_per_day(12, 4.0, 180, 50000)
    assert rough["fuel_t_per_day"] > calm["fuel_t_per_day"]


def test_h3_bins_sum():
    cells = an.h3_hexbin([60.1, 60.1, 25.0], [25.0, 25.0, 25.1], resolution=7)
    assert sum(c["n"] for c in cells) == 3


def test_haversine_vs_vincenty_close():
    hv = float(k.haversine_nm_arr(59.9, 24.9, 60.1, 25.1)[0])
    vv = float(k.vincenty_nm(59.9, 24.9, 60.1, 25.1)[0])
    assert abs(hv - vv) / hv < 0.01   # <1% apart on short legs


def test_ekf_smooths_noise():
    rng = np.random.default_rng(0)
    n = 60
    truth_lat = 60 + np.linspace(0, 0.1, n)
    truth_lon = 25 + np.linspace(0, 0.1, n)
    noisy_lat = truth_lat + rng.normal(0, 0.0005, n)
    noisy_lon = truth_lon + rng.normal(0, 0.0005, n)
    dts = np.arange(n) * 60.0
    sm = k.ekf_track(noisy_lat.tolist(), noisy_lon.tolist(), dts.tolist())
    err_smooth = np.mean([abs(s[0] - t) for s, t in zip(sm[5:], truth_lat[5:])])
    err_raw = np.mean([abs(s - t) for s, t in zip(noisy_lat[5:], truth_lat[5:])])
    assert err_smooth < err_raw
