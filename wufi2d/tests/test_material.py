"""Tests des Materialmodells (Sorptionsisotherme, Transportkoeffizienten)."""

from __future__ import annotations

import numpy as np
import pytest

from wufi2d import physics
from wufi2d.material import (Material, MaterialError, MaterialLibrary, air_layer,
                            default_library, get_material, membrane,
                            variable_membrane)


def test_default_library_loads():
    library = default_library()
    assert len(library) > 15
    assert "Vollziegel (Altbau)" in library.names()
    for material in library:
        material.validate()


def test_isotherm_matches_defining_points():
    material = get_material("Vollziegel (Altbau)")
    assert float(material.w(0.8)) == pytest.approx(material.w_80, rel=1e-9)
    assert float(material.w(1.0)) == pytest.approx(material.w_f, rel=1e-9)
    assert float(material.w(0.0)) == pytest.approx(0.0, abs=1e-12)


def test_isotherm_strictly_monotone():
    for name in default_library().names():
        material = get_material(name)
        phi = np.linspace(0.0, 1.0, 101)
        w = material.w(phi)
        assert np.all(np.diff(w) > 0.0), name


def test_dw_dphi_matches_numerical_derivative():
    material = get_material("Kalkputz")
    for phi in (0.2, 0.5, 0.8, 0.95):
        h = 1e-6
        numerical = (material.w(phi + h) - material.w(phi - h)) / (2 * h)
        assert float(material.dw_dphi(phi)) == pytest.approx(float(numerical), rel=1e-4)


def test_phi_from_w_roundtrip():
    for name in ("Beton C25/30", "Mineralwolle", "Fichte radial"):
        material = get_material(name)
        for phi in (0.1, 0.45, 0.8, 0.99):
            w = material.w(phi)
            assert float(material.phi_from_w(w)) == pytest.approx(phi, rel=1e-6)


def test_tabulated_isotherm(linear_material):
    assert float(linear_material.w(0.5)) == pytest.approx(50.0)
    assert float(linear_material.dw_dphi(0.5)) == pytest.approx(100.0, rel=1e-9)
    assert float(linear_material.phi_from_w(25.0)) == pytest.approx(0.25)


def test_liquid_transport_from_absorption_coefficient():
    material = get_material("Kalkputz")
    # Kuenzel: D_ws(w_f) = 3.8 * (A_w / w_f)^2
    expected = 3.8 * (material.a_w / material.w_f) ** 2
    assert float(material.dw_suction(material.w_f)) == pytest.approx(expected, rel=1e-9)
    # Faktor 1000 ueber den gesamten Feuchtebereich
    assert (float(material.dw_suction(material.w_f))
            / float(material.dw_suction(0.0))) == pytest.approx(1000.0, rel=1e-6)
    # Weiterverteilung ist langsamer als Saugen
    assert material.dw_redistribution(material.w_f) < material.dw_suction(material.w_f)


def test_no_liquid_transport_without_absorption_coefficient():
    material = get_material("Mineralwolle")
    assert float(material.dw_suction(50.0)) == 0.0
    assert float(material.d_phi(0.9)) == 0.0


def test_lambda_moisture_supplement():
    material = get_material("Vollziegel (Altbau)")
    # b = 15 %/M.-%, u = 100*w/rho
    w = 38.0  # -> u = 2 M.-%
    expected = material.lambda_dry * (1.0 + 15.0 / 100.0 * 100.0 * w / material.rho)
    assert float(material.lambda_moist(w)) == pytest.approx(expected)
    assert float(material.lambda_moist(0.0)) == pytest.approx(material.lambda_dry)


def test_heat_capacity_includes_water():
    material = get_material("Beton C25/30")
    dry = float(material.heat_capacity_moist(0.0))
    moist = float(material.heat_capacity_moist(50.0))
    assert dry == pytest.approx(material.rho * material.cp)
    assert moist == pytest.approx(dry + 50.0 * physics.C_WATER)


def test_delta_p_from_mu():
    material = get_material("Beton C25/30")
    assert float(material.delta_p(20.0)) == pytest.approx(
        physics.delta_a(20.0) / material.mu)


def test_moisture_dependent_mu():
    material = get_material("Fichte radial")
    dry = float(material.mu_value(0.1))
    wet = float(material.mu_value(0.95))
    assert dry > wet  # Dry-Cup-Wert groesser als Wet-Cup-Wert


def test_validation_rejects_inconsistent_isotherm():
    with pytest.raises(MaterialError):
        Material(name="x", rho=1000, cp=1000, lambda_dry=1.0, mu=10,
                 w_f=100.0, w_80=90.0)  # w_80 > 0.8 * w_f
    with pytest.raises(MaterialError):
        Material(name="x", rho=-1, cp=1000, lambda_dry=1.0, mu=10,
                 w_f=100.0, w_80=10.0)


def test_serialisation_roundtrip():
    material = get_material("Calciumsilikat (Innendaemmung)")
    clone = Material.from_dict(material.to_dict())
    assert clone.name == material.name
    assert float(clone.w(0.8)) == pytest.approx(float(material.w(0.8)))


def test_library_json_roundtrip(tmp_path):
    library = default_library()
    path = library.to_json(tmp_path / "db.json") or (tmp_path / "db.json")
    reloaded = MaterialLibrary.from_json(path)
    assert reloaded.names() == library.names()


def test_air_layer_equivalent_conductivity():
    layer = air_layer(0.02, thermal_resistance=0.18)
    assert layer.lambda_dry == pytest.approx(0.02 / 0.18)
    assert layer.mu == 1.0
    layer.validate()


def test_membrane_sd_value():
    foil = membrane(2.0, thickness=0.001)
    assert foil.sd_value(0.001) == pytest.approx(2.0)
    variable = variable_membrane(10.0, 0.25, thickness=0.001)
    assert variable.mu_value(0.1) > variable.mu_value(0.9)


def test_missing_material_raises():
    with pytest.raises(MaterialError):
        default_library().get("Gibt es nicht")
