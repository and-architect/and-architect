"""Tests fuer Modell-Serialisierung, Ergebnisexport und Auswertung."""

from __future__ import annotations

import numpy as np
import pytest

from wufi2d import analysis
from wufi2d import boundary as bnd
from wufi2d.climate import ConstantClimate, SineClimate
from wufi2d.grid import rectangle
from wufi2d.material import Material, MaterialLibrary
from wufi2d.model import Model
from wufi2d.results import Results
from wufi2d.solver import InitialConditions, SolverOptions

HOUR = 3600.0
DAY = 86400.0


# ---------------------------------------------------------------------------
# Hilfsmodelle
# ---------------------------------------------------------------------------

def _simple_model(duration=2 * DAY, output=DAY) -> Model:
    model = Model(name="Testwand", description="Zweischichtige Aussenwand")
    model.add_region("Vollziegel (Altbau)", rectangle(0.0, 0.0, 0.24, 0.05),
                     name="Mauerwerk")
    model.add_region("Kalkputz", rectangle(0.24, 0.0, 0.02, 0.05), name="Innenputz")
    model.grid_options.max_cell = 0.01
    model.grid_options.min_cell = 0.004
    model.grid_options.max_cell_y = 0.05
    model.grid_options.min_cell_y = 0.05
    model.add_boundary("links", bnd.exterior_surface(ConstantClimate(-5.0, 0.8),
                                                     solar_absorptance=0.0,
                                                     rain_absorption=0.0,
                                                     emissivity=0.0))
    model.add_boundary("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5)))
    model.options = SolverOptions(duration=duration, dt=HOUR, output_interval=output,
                                 latent_heat=True)
    model.initial = InitialConditions(temperature=10.0, rh=0.6)
    return model


# ---------------------------------------------------------------------------
# Modell
# ---------------------------------------------------------------------------

def test_model_json_roundtrip(tmp_path):
    model = _simple_model()
    path = model.save(tmp_path / "modell.json")
    reloaded = Model.load(path)
    assert reloaded.name == model.name
    assert len(reloaded.regions) == len(model.regions)
    assert reloaded.regions[0].material == "Vollziegel (Altbau)"
    assert len(reloaded.boundaries) == 2
    assert reloaded.options.duration == model.options.duration
    # Ergebnisse stimmen ueberein
    a = model.run().temperature[-1]
    b = reloaded.run().temperature[-1]
    assert np.allclose(np.nan_to_num(a), np.nan_to_num(b))


def test_model_roundtrip_with_custom_material_and_sine_climate(tmp_path):
    custom = Material(name="Sonderbaustoff", rho=800.0, cp=1000.0, lambda_dry=0.2,
                      mu=20.0, w_f=200.0, w_80=30.0, a_w=0.05,
                      lambda_moisture_supplement=5.0)
    model = Model(name="Sondermodell", materials=MaterialLibrary([custom]))
    model.add_region("Sonderbaustoff", rectangle(0.0, 0.0, 0.1, 0.05))
    model.add_boundary("links", bnd.exterior_surface(
        SineClimate(mean_temperature=8.0, amplitude_temperature=9.0)))
    model.add_boundary("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5), sd=0.5))
    path = model.save(tmp_path / "sonder.json")
    reloaded = Model.load(path)
    assert "Sonderbaustoff" in reloaded.library().names()
    assert reloaded.library().get("Sonderbaustoff").rho == 800.0
    condition = reloaded.boundaries[1][1]
    assert condition.transfer.sd == pytest.approx(0.5)
    assert isinstance(reloaded.boundaries[0][1].climate, SineClimate)


def test_model_roundtrip_with_polyline_selector(tmp_path):
    model = _simple_model()
    model.boundaries = []
    model.add_boundary(bnd.PolylineSelector([(0.0, 0.0), (0.0, 0.05)], tolerance=0.002),
                       bnd.exterior_surface(ConstantClimate(-5.0, 0.8)))
    reloaded = Model.load(model.save(tmp_path / "kurve.json"))
    selector = reloaded.boundaries[0][0]
    assert isinstance(selector, bnd.PolylineSelector)
    assert selector.tolerance == pytest.approx(0.002)


def test_model_validate_reports_missing_boundaries():
    model = Model(name="ohne Rand")
    model.add_region("Stahlbeton", rectangle(0.0, 0.0, 0.2, 0.2))
    warnings = model.validate()
    assert any("Randbedingung" in warning for warning in warnings)


def test_model_validate_accepts_complete_model():
    assert _simple_model().validate() == []


def test_model_rejects_newer_schema():
    with pytest.raises(ValueError):
        Model.from_dict({"schema": 99, "regions": []})


def test_model_describe_contains_regions():
    text = _simple_model().describe()
    assert "Mauerwerk" in text and "Innenputz" in text


# ---------------------------------------------------------------------------
# Ergebnisse
# ---------------------------------------------------------------------------

def test_results_npz_roundtrip(tmp_path):
    results = _simple_model().run()
    path = results.to_npz(tmp_path / "ergebnis.npz")
    reloaded = Results.from_npz(path)
    assert np.allclose(np.nan_to_num(reloaded.temperature),
                       np.nan_to_num(results.temperature))
    assert reloaded.grid.material_names == results.grid.material_names
    assert set(reloaded.surfaces) == set(results.surfaces)
    assert reloaded.total_water[-1] == pytest.approx(results.total_water[-1])


def test_results_csv_export(tmp_path):
    results = _simple_model().run()
    path = results.to_csv(tmp_path / "zeitreihen.csv")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("zeit_h;zeit_d;wasser_total_kg")
    assert len(lines) == results.n_steps + 1

    field_path = results.to_csv(tmp_path / "felder.csv", quantity="temperature")
    field_lines = field_path.read_text(encoding="utf-8").splitlines()
    assert len(field_lines) == results.n_steps + 1
    assert len(field_lines[0].split(";")) == results.grid.n_active + 1


def test_results_field_access_and_profile():
    results = _simple_model().run()
    assert results.field("temperature").shape == results.grid.shape
    assert results.field("rh", time=DAY).shape == results.grid.shape
    x, values = results.profile("temperature")
    assert len(x) == results.grid.nx == len(values)
    # Temperatur steigt von aussen nach innen
    assert values[0] < values[-1]
    with pytest.raises(KeyError):
        results.field("unbekannt")


def test_results_cell_series_and_mass_percent():
    results = _simple_model().run()
    series = results.cell_series(0.12, 0.025)
    assert len(series["temperature"]) == results.n_steps
    mass_percent = results.moisture_mass_percent()
    finite = mass_percent[results.grid.active]
    assert np.all(finite > 0.0) and np.all(finite < 30.0)
    with pytest.raises(ValueError):
        results.cell_series(5.0, 5.0)


def test_results_cell_values_matches_mesh():
    results = _simple_model().run()
    _, quads, _ = results.grid.mesh_data()
    values = results.cell_values("temperature")
    assert len(values) == len(quads)
    assert all(np.isfinite(v) for v in values)


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------

def test_thermal_coupling_coefficient_matches_u_value():
    """Bei einer ungestoerten Wand entspricht L2D dem U-Wert mal Hoehe."""
    materials = MaterialLibrary([Material(
        name="Homogen", rho=1000.0, cp=1000.0, lambda_dry=0.5, mu=1e5, w_f=100.0,
        w_80=1.0, a_w=0.0, lambda_moisture_supplement=0.0,
        sorption_table=[[0.0, 0.0], [1.0, 100.0]])])
    height = 1.0
    model = Model(name="Homogene Wand", materials=materials)
    model.add_region("Homogen", rectangle(0.0, 0.0, 0.25, height))
    model.grid_options.max_cell = 0.02
    model.grid_options.min_cell = 0.01
    model.grid_options.max_cell_y = 0.1
    model.grid_options.min_cell_y = 0.1
    model.add_boundary("links", bnd.exterior_surface(ConstantClimate(-5.0, 0.8),
                                                     alpha=25.0,
                                                     solar_absorptance=0.0,
                                                     rain_absorption=0.0,
                                                     emissivity=0.0))
    model.add_boundary("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5),
                                                      alpha=7.7))
    model.options = SolverOptions(duration=60 * DAY, dt=2 * HOUR,
                                  output_interval=60 * DAY, latent_heat=False)
    model.initial = InitialConditions(temperature=10.0, rh=0.5)
    results = model.run()

    u_value = 1.0 / (1 / 25.0 + 0.25 / 0.5 + 1 / 7.7)
    l2d = analysis.thermal_coupling_coefficient(results, "innen", 25.0)
    assert l2d == pytest.approx(u_value * height, rel=0.02)
    # Psi eines ungestoerten Aufbaus ist ~0
    assert analysis.psi_value(l2d, [(u_value, height)]) == pytest.approx(0.0, abs=0.02)


def test_temperature_factor_range():
    results = _simple_model(duration=10 * DAY, output=DAY).run()
    factor = analysis.temperature_factor(results, "innen", 20.0, -5.0)
    assert 0.0 < factor < 1.0


def test_moisture_balance_detects_drying_and_accumulation():
    results = _simple_model(duration=10 * DAY, output=DAY).run()
    balance = analysis.moisture_balance(results)
    assert balance.water_start > 0.0
    assert isinstance(balance.accumulating, bool)
    assert "Wassergehalt" in balance.summary()

    material_balance = analysis.moisture_balance(results, material="Kalkputz")
    assert material_balance.water_start > 0.0
    with pytest.raises(KeyError):
        analysis.moisture_balance(results, material="gibt es nicht")


def test_critical_rh_curve():
    assert float(analysis.critical_rh(20.0)) == pytest.approx(0.80, abs=1e-9)
    assert float(analysis.critical_rh(5.0)) > float(analysis.critical_rh(25.0))
    assert float(analysis.critical_rh(-5.0)) == 1.0  # kein Wachstum unter 0 degC


def test_mould_risk_series_counts_hours():
    times = np.arange(0, 10 * HOUR, HOUR, dtype=float)
    temperature = np.full(len(times), 20.0)
    rh = np.full(len(times), 0.85)  # ueber der kritischen Feuchte (0.80)
    risk = analysis.mould_risk_series(times, temperature, rh)
    assert risk.hours_critical == pytest.approx(9.0, abs=1.0)
    assert risk.fraction_critical == pytest.approx(1.0, abs=0.01)
    assert risk.max_exceedance == pytest.approx(0.05, abs=1e-9)

    dry = analysis.mould_risk_series(times, temperature, np.full(len(times), 0.5))
    assert dry.hours_critical == 0.0


def test_mould_risk_at_surface_and_point():
    results = _simple_model(duration=5 * DAY, output=HOUR * 6).run()
    surface = analysis.mould_risk_at_surface(results, "innen")
    assert surface.max_rh <= 1.0
    point = analysis.mould_risk_at_point(results, 0.25, 0.025)
    assert "Punkt" in point.location


def test_wood_moisture_check():
    materials = MaterialLibrary([Material(
        name="Holz", rho=450.0, cp=1500.0, lambda_dry=0.13, mu=200.0, w_f=600.0,
        w_80=75.0, a_w=0.004, lambda_moisture_supplement=1.5)])
    model = Model(name="Holzbauteil", materials=materials)
    model.add_region("Holz", rectangle(0.0, 0.0, 0.06, 0.05))
    model.grid_options.max_cell = 0.01
    model.grid_options.min_cell = 0.005
    model.grid_options.max_cell_y = 0.05
    model.grid_options.min_cell_y = 0.05
    model.add_boundary("links", bnd.exterior_surface(ConstantClimate(5.0, 0.95),
                                                     solar_absorptance=0.0,
                                                     rain_absorption=0.0,
                                                     emissivity=0.0))
    model.add_boundary("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5)))
    model.options = SolverOptions(duration=30 * DAY, dt=2 * HOUR,
                                  output_interval=DAY)
    model.initial = InitialConditions(temperature=10.0, rh=0.8)
    results = model.run()
    check = analysis.wood_moisture_check(results, "Holz", limit=20.0)
    assert check.max_mass_percent > 0.0
    assert "M.-%" in check.summary()
    with pytest.raises(KeyError):
        analysis.wood_moisture_check(results, "Beton C25/30")


def test_saturation_cells_and_report():
    results = _simple_model(duration=5 * DAY, output=DAY).run()
    saturation = analysis.saturation_cells(results)
    assert saturation["max_fraction"] <= 1.0
    text = analysis.report(results)
    assert "Bewertung" in text
    assert "Wassergehalt" in text


def test_moisture_balance_from_time_ignores_start():
    results = _simple_model(duration=20 * DAY, output=DAY).run()
    ganz = analysis.moisture_balance(results)
    spaeter = analysis.moisture_balance(results, from_time=10 * DAY)
    assert spaeter.water_start != ganz.water_start
    # Der Anfangszustand wirkt am staerksten -- der spaetere Trend ist flacher
    assert abs(spaeter.trend_per_year) <= abs(ganz.trend_per_year) + 1e-9


def test_annual_balance_uses_full_range_for_short_runs():
    results = _simple_model(duration=20 * DAY, output=DAY).run()
    assert (analysis.annual_balance(results).water_start
            == pytest.approx(analysis.moisture_balance(results).water_start))


def test_yearly_water_content_lists_year_ends():
    results = _simple_model(duration=20 * DAY, output=DAY).run()
    values = analysis.yearly_water_content(results)
    assert values[0][0] == 0.0
    assert len(values) == 1  # weniger als ein Jahr gerechnet


def test_worst_cell_finds_maximum():
    results = _simple_model(duration=10 * DAY, output=DAY).run()
    treffer = analysis.worst_cell(results, quantity="rh")
    assert 0.0 <= treffer["x"] <= 0.26
    assert treffer["wert"] == pytest.approx(float(np.nanmax(results.rh)))
    assert 0.0 <= treffer["zeit_d"] <= 10.0

    im_putz = analysis.worst_cell(results, material="Kalkputz", quantity="water_content")
    assert im_putz["x"] > 0.24  # Innenputz liegt aussen rechts
    with pytest.raises(KeyError):
        analysis.worst_cell(results, material="gibt es nicht")
