"""Tests der physikalischen Basisfunktionen."""

from __future__ import annotations

import numpy as np
import pytest

from wufi2d import physics


def test_p_sat_reference_values():
    # Saettigungsdampfdruck: Literaturwerte (Magnus-Formel)
    assert physics.p_sat(0.0) == pytest.approx(611.0, rel=1e-6)
    assert physics.p_sat(20.0) == pytest.approx(2340.0, rel=0.01)
    assert physics.p_sat(10.0) == pytest.approx(1228.0, rel=0.01)
    assert physics.p_sat(30.0) == pytest.approx(4245.0, rel=0.01)
    assert physics.p_sat(-10.0) == pytest.approx(260.0, rel=0.02)


def test_p_sat_monotone_and_vectorised():
    theta = np.linspace(-20.0, 50.0, 200)
    values = physics.p_sat(theta)
    assert values.shape == theta.shape
    assert np.all(np.diff(values) > 0.0)


def test_dp_sat_matches_numerical_derivative():
    for theta in (-15.0, -0.5, 0.5, 10.0, 25.0, 40.0):
        h = 1e-4
        numerical = (physics.p_sat(theta + h) - physics.p_sat(theta - h)) / (2 * h)
        assert physics.dp_sat_dtheta(theta) == pytest.approx(numerical, rel=1e-4)


def test_delta_a_magnitude():
    # Wasserdampfleitfaehigkeit ruhender Luft: ca. 2e-10 kg/(m s Pa)
    assert physics.delta_a(20.0) == pytest.approx(1.97e-10, rel=0.05)
    assert physics.delta_a(0.0) < physics.delta_a(40.0)


def test_dew_point_roundtrip():
    for theta in (-5.0, 5.0, 20.0, 35.0):
        for phi in (0.3, 0.6, 0.95):
            td = physics.dew_point(theta, phi)
            assert td <= theta + 1e-6
            # Am Taupunkt ist die Luft gesaettigt
            assert physics.p_sat(td) == pytest.approx(
                physics.vapour_pressure(theta, phi), rel=1e-3)


def test_relative_humidity_roundtrip():
    p_v = physics.vapour_pressure(18.0, 0.62)
    assert physics.relative_humidity(18.0, p_v) == pytest.approx(0.62)


def test_suction_pressure_roundtrip():
    for phi in (0.5, 0.8, 0.99):
        p_c = physics.suction_pressure(20.0, phi)
        assert p_c < 0.0
        assert physics.phi_from_suction(20.0, p_c) == pytest.approx(phi, rel=1e-9)


def test_vapour_concentration_matches_ideal_gas():
    # 20 degC, 100 % rF -> ca. 17.3 g/m3
    assert physics.vapour_concentration(20.0, 1.0) == pytest.approx(0.0173, rel=0.02)


def test_harmonic_face_value_series_resistance():
    # Reihenschaltung: gleiche Leitwerte -> unveraendert
    assert physics.harmonic_face_value(2.0, 2.0, 0.1, 0.1) == pytest.approx(2.0)
    # Ein sperrender Teil -> Grenzflaeche sperrt
    assert physics.harmonic_face_value(2.0, 0.0, 0.1, 0.1) == pytest.approx(0.0)
    # Analytisch: (d_a + d_b) / (d_a/k_a + d_b/k_b)
    value = physics.harmonic_face_value(1.0, 3.0, 0.02, 0.04)
    assert value == pytest.approx(0.06 / (0.02 / 1.0 + 0.04 / 3.0))


def test_humidity_ratio_reference():
    # 20 degC, 50 % rF -> ca. 7.3 g/kg
    assert physics.humidity_ratio(20.0, 0.5) == pytest.approx(0.00727, rel=0.02)
