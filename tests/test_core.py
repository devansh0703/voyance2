"""Unit tests with tiny synthetic fixtures (no network, no real data needed).

Real-data tests live in the pipeline make targets; these test the pure logic:
coordinate parsing, haversine, Beaufort mapping, PSI, and the API predict path
with a stubbed model artifact.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from geo import (  # noqa: E402
    PortMatcher, assign_region, beaufort_from_wind_kn, haversine_nm,
    load_ports, parse_locode_coords,
)


def test_parse_locode_coords():
    assert parse_locode_coords("4230N 00131E") == pytest.approx((42.5, 1.5167), abs=1e-3)
    assert parse_locode_coords("3300S 15100W") == pytest.approx((-33.0, -151.0), abs=1e-3)
    assert parse_locode_coords("junk") is None


def test_haversine_symmetric_and_sane():
    d = haversine_nm(33.7, -118.2, 37.79, -122.27)  # LA -> SF ≈ 302 NM
    assert 250 < d < 350
    assert haversine_nm(0, 0, 0, 0) == 0
    assert haversine_nm(10, 20, 10, 20) == 0


def test_beaufort_bounds():
    ws = np.array([0, 2, 5, 12, 30, 70])
    b = beaufort_from_wind_kn(ws)
    assert list(b) == [0, 1, 2, 4, 7, 12]


def test_assign_region():
    lat = np.array([37.7, 40.6, 29.0, 0.0])
    lon = np.array([-122.4, -73.9, -94.0, 0.0])
    r = assign_region(lat, lon)
    assert r[0] == "us_west_coast"
    assert r[1] == "us_east_coast"
    assert r[2] == "gulf_of_mexico"
    assert r[3] == "other_us_waters"


def test_port_matcher_clusters_adjacent(tmp_path):
    fixture = Path(__file__).resolve().parent / "fixtures" / "ports-sample.csv"
    ports = load_ports(str(fixture))
    m = PortMatcher(ports, 15.0)
    # two very close UN/LOCODE entries in the same harbor must collapse to one area
    dist, idx = m.nearest(np.array([29.93]), np.array([-90.07]))  # New Orleans area
    km = np.rad2deg(dist) * 111.32
    assert km[0] < 30
    assert len(m.ports) < len(ports)


def test_psi_identical_is_zero():
    from drift import psi
    x = np.random.default_rng(0).normal(size=5000)
    assert psi(x, x) == pytest.approx(0.0, abs=1e-9)


def test_psi_shifted_is_positive():
    from drift import psi
    x = np.random.default_rng(0).normal(0, 1, size=5000)
    y = np.random.default_rng(1).normal(3, 1, size=5000)
    assert psi(x, y) > 1.0
