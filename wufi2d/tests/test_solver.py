"""Verifikation des Loesers.

Die Tests vergleichen mit analytischen Loesungen, fuer die die Modell-
gleichungen exakt loesbar sind:

* stationaerer 1D-Waermedurchgang -> Reihenschaltung der Waermewiderstaende
* stationaere Dampfdiffusion -> Reihenschaltung der s_d-Werte (Glaser-Fall)
* instationaere Erwaermung eines halbunendlichen Koerpers -> erf-Loesung
* instationaere Feuchteaufnahme bei linearer Isotherme -> erf-Loesung

Zusaetzlich werden Erhaltungssaetze, Symmetrie, Gitterkonvergenz und der
NumPy-Fallback des Gleichungsloesers geprueft.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from wufi2d import boundary as bnd
from wufi2d import physics
from wufi2d.grid import Region, build_grid, build_layered_grid, rectangle
from wufi2d.climate import ConstantClimate
from wufi2d.material import Material, MaterialLibrary, default_library
from wufi2d.solver import (InitialConditions, SolverOptions, SolverError,
                           Wufi2DSolver)

HOUR = 3600.0
DAY = 86400.0


# ---------------------------------------------------------------------------
# Hilfsmaterialien
# ---------------------------------------------------------------------------

def _dry_material(name="trocken", lambda_dry=1.0, rho=1000.0, cp=1000.0, mu=1e5):
    """Praktisch dampfdichtes Material mit konstanten Kennwerten."""
    return Material(name=name, rho=rho, cp=cp, lambda_dry=lambda_dry, mu=mu,
                    w_f=100.0, w_80=1.0, a_w=0.0, lambda_moisture_supplement=0.0,
                    sorption_table=[[0.0, 0.0], [1.0, 100.0]])


def _vapour_material(name="dampfoffen", w_f=1.0, mu=1.0):
    """Lineare Isotherme, reiner Dampftransport (kein Fluessigtransport)."""
    return Material(name=name, rho=1000.0, cp=1000.0, lambda_dry=1.0, mu=mu,
                    w_f=w_f, w_80=0.1, a_w=0.0, lambda_moisture_supplement=0.0,
                    sorption_table=[[0.0, 0.0], [1.0, w_f]])


def _one_dimensional_grid(layers, materials, height=0.05, max_cell=0.005,
                          min_cell=0.001):
    return build_layered_grid(layers, height=height, n_rows=1, max_cell=max_cell,
                              min_cell=min_cell, materials=materials)


# ---------------------------------------------------------------------------
# Stationaerer Waermedurchgang
# ---------------------------------------------------------------------------

def test_steady_state_heat_matches_series_resistance():
    """Waermestrom und Oberflaechentemperaturen der Reihenschaltung."""
    materials = MaterialLibrary([
        _dry_material("Beton trocken", lambda_dry=2.0),
        _dry_material("Daemmung trocken", lambda_dry=0.04),
    ])
    grid = _one_dimensional_grid([("Beton trocken", 0.2), ("Daemmung trocken", 0.16)],
                                materials)
    alpha_e, alpha_i = 25.0, 7.7
    boundaries = bnd.BoundarySet()
    boundaries.add("links", bnd.exterior_surface(ConstantClimate(-10.0, 0.8),
                                                 alpha=alpha_e, solar_absorptance=0.0,
                                                 rain_absorption=0.0, emissivity=0.0))
    boundaries.add("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5),
                                                  alpha=alpha_i))
    solver = Wufi2DSolver(grid, materials, boundaries,
                          initial=InitialConditions(temperature=5.0, rh=0.5),
                          options=SolverOptions(latent_heat=False))
    temperature, _ = solver.solve_steady_state()

    r_total = 1 / alpha_e + 0.2 / 2.0 + 0.16 / 0.04 + 1 / alpha_i
    q_expected = (20.0 - (-10.0)) / r_total
    t_se_expected = -10.0 + q_expected / alpha_e
    t_si_expected = 20.0 - q_expected / alpha_i

    # Randzellen-Temperaturen um den halben Zellwiderstand korrigieren
    dx = grid.dx
    t_left = temperature[0, 0] - q_expected * (0.5 * dx[0] / 2.0)
    t_right = temperature[0, -1] + q_expected * (0.5 * dx[-1] / 0.04)
    assert t_left == pytest.approx(t_se_expected, abs=0.05)
    assert t_right == pytest.approx(t_si_expected, abs=0.05)

    # Temperatur an der Schichtgrenze
    interface = -10.0 + q_expected * (1 / alpha_e + 0.2 / 2.0)
    index = int(np.argmin(np.abs(grid.x_edges - 0.2)))
    x_interface = grid.x_edges[index]
    left_cell = int(np.searchsorted(grid.x_edges, x_interface) - 1)
    t_interface = temperature[0, left_cell] + q_expected * 0.5 * dx[left_cell] / 2.0
    assert t_interface == pytest.approx(interface, abs=0.1)


def test_steady_state_heat_flux_balance():
    """Zufluss und Abfluss sind im stationaeren Zustand gleich gross."""
    materials = MaterialLibrary([_dry_material("Beton trocken", lambda_dry=2.0)])
    grid = _one_dimensional_grid([("Beton trocken", 0.24)], materials)
    boundaries = bnd.BoundarySet()
    boundaries.add("links", bnd.exterior_surface(ConstantClimate(-5.0, 0.8),
                                                 solar_absorptance=0.0,
                                                 rain_absorption=0.0, emissivity=0.0))
    boundaries.add("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5)))
    options = SolverOptions(duration=40 * DAY, dt=HOUR, output_interval=40 * DAY,
                           latent_heat=False)
    solver = Wufi2DSolver(grid, materials, boundaries,
                          initial=InitialConditions(temperature=20.0, rh=0.5),
                          options=options)
    results = solver.run()
    q_in = results.surfaces["innen"].heat_flux[-1]
    q_out = results.surfaces["aussen"].heat_flux[-1]
    assert q_in > 0.0 > q_out
    assert q_in + q_out == pytest.approx(0.0, abs=0.02 * abs(q_in))

    # Vergleich mit der Reihenschaltung (Flaeche = Hoehe x Tiefe)
    r_total = 1 / 17.0 + 0.24 / 2.0 + 1 / 8.0
    area = 0.05 * grid.depth
    assert q_in == pytest.approx(25.0 / r_total * area, rel=0.02)


# ---------------------------------------------------------------------------
# Stationaere Dampfdiffusion (Glaser-Fall)
# ---------------------------------------------------------------------------

def test_steady_state_vapour_profile_matches_sd_series():
    """Dampfdruckprofil folgt der Reihenschaltung der s_d-Werte."""
    materials = MaterialLibrary([
        _vapour_material("Schicht A", w_f=1.0, mu=10.0),
        _vapour_material("Schicht B", w_f=1.0, mu=100.0),
    ])
    grid = _one_dimensional_grid([("Schicht A", 0.1), ("Schicht B", 0.05)], materials,
                                max_cell=0.0025, min_cell=0.001)
    boundaries = bnd.BoundarySet()
    boundaries.add("links", bnd.FixedBoundary(20.0, 0.3, name="aussen"))
    boundaries.add("rechts", bnd.FixedBoundary(20.0, 0.9, name="innen"))
    options = SolverOptions(duration=200 * DAY, dt=6 * HOUR,
                            output_interval=200 * DAY, latent_heat=False,
                            liquid_transport=False)
    solver = Wufi2DSolver(grid, materials, boundaries,
                          initial=InitialConditions(temperature=20.0, rh=0.3),
                          options=options)
    results = solver.run()

    p_sat = physics.p_sat(20.0)
    p_left, p_right = 0.3 * p_sat, 0.9 * p_sat
    sd_total = 10.0 * 0.1 + 100.0 * 0.05

    x = grid.xc
    sd = np.where(x <= 0.1, 10.0 * x, 10.0 * 0.1 + 100.0 * (x - 0.1))
    expected = p_left + (p_right - p_left) * sd / sd_total
    computed = physics.vapour_pressure(results.temperature[-1, 0, :],
                                       results.rh[-1, 0, :])
    assert np.allclose(computed, expected, rtol=0.02, atol=5.0)


def test_vapour_tight_layer_blocks_diffusion():
    """Eine praktisch dampfdichte Schicht unterbindet den Dampftransport."""
    materials = MaterialLibrary([
        _vapour_material("offen", w_f=10.0, mu=1.0),
        _dry_material("Sperrschicht", mu=1e6),
    ])
    grid = _one_dimensional_grid([("offen", 0.05), ("Sperrschicht", 0.005),
                                  ("offen", 0.05)], materials,
                                 max_cell=0.0025, min_cell=0.001)
    boundaries = bnd.BoundarySet()
    boundaries.add("links", bnd.FixedBoundary(20.0, 0.95, name="feucht"))
    boundaries.add("rechts", bnd.FixedBoundary(20.0, 0.3, name="trocken"))
    options = SolverOptions(duration=30 * DAY, dt=6 * HOUR, output_interval=30 * DAY,
                            latent_heat=False, liquid_transport=False)
    solver = Wufi2DSolver(grid, materials, boundaries,
                          initial=InitialConditions(temperature=20.0, rh=0.3),
                          options=options)
    results = solver.run()
    rh = results.rh[-1, 0, :]
    x = grid.xc
    # Vor der Sperrschicht nahe 0.95, dahinter nahe 0.3
    assert rh[x < 0.05].min() > 0.9
    assert rh[x > 0.055].max() < 0.35


# ---------------------------------------------------------------------------
# Instationaer: halbunendlicher Koerper
# ---------------------------------------------------------------------------

def test_transient_heat_matches_semi_infinite_solution():
    """Temperatursprung an der Oberflaeche: Vergleich mit der erf-Loesung."""
    material = _dry_material("halbunendlich", lambda_dry=1.0, rho=1000.0, cp=1000.0)
    materials = MaterialLibrary([material])
    grid = _one_dimensional_grid([("halbunendlich", 0.6)], materials,
                                 max_cell=0.004, min_cell=0.001)
    t_0, t_surface, rh_0 = 20.0, 30.0, 0.5
    boundaries = bnd.BoundarySet()
    boundaries.add("links", bnd.FixedBoundary(t_surface, rh_0, name="oberflaeche"))
    duration = 6 * HOUR
    options = SolverOptions(duration=duration, dt=60.0, output_interval=duration,
                            latent_heat=False, liquid_transport=False)
    solver = Wufi2DSolver(grid, materials, boundaries,
                          initial=InitialConditions(temperature=t_0, rh=rh_0),
                          options=options)
    results = solver.run()

    # Waermespeicherfaehigkeit einschliesslich des Porenwassers
    w = float(material.w(rh_0))
    alpha = material.lambda_dry / (material.rho * material.cp + w * physics.C_WATER)
    x = grid.xc
    expected = t_surface + (t_0 - t_surface) * np.array(
        [math.erf(xi / (2.0 * math.sqrt(alpha * duration))) for xi in x])
    computed = results.temperature[-1, 0, :]
    assert np.max(np.abs(computed - expected)) < 0.15
    # Am fernen Rand (mehr als vier Eindringtiefen) ist die Temperatur noch
    # praktisch unveraendert -- das Gebiet wirkt halbunendlich
    assert computed[-1] == pytest.approx(t_0, abs=0.05)


def test_transient_moisture_matches_semi_infinite_solution():
    """Feuchtesprung bei linearer Isotherme: Vergleich mit der erf-Loesung."""
    material = _vapour_material("dampfoffen", w_f=1.0, mu=1.0)
    materials = MaterialLibrary([material])
    grid = _one_dimensional_grid([("dampfoffen", 0.5)], materials,
                                 max_cell=0.004, min_cell=0.001)
    theta, phi_0, phi_surface = 20.0, 0.4, 0.9
    boundaries = bnd.BoundarySet()
    boundaries.add("links", bnd.FixedBoundary(theta, phi_surface, name="oberflaeche"))
    duration = 4 * HOUR
    options = SolverOptions(duration=duration, dt=60.0, output_interval=duration,
                            latent_heat=False, liquid_transport=False)
    solver = Wufi2DSolver(grid, materials, boundaries,
                          initial=InitialConditions(temperature=theta, rh=phi_0),
                          options=options)
    results = solver.run()

    # Reine Dampfdiffusion bei konstanter Temperatur:
    #   dw/dphi * dphi/dt = delta_p * p_sat * d2phi/dx2
    diffusivity = (material.delta_p(theta) * physics.p_sat(theta)
                   / float(material.dw_dphi(0.5)))
    x = grid.xc
    expected = phi_surface + (phi_0 - phi_surface) * np.array(
        [math.erf(xi / (2.0 * math.sqrt(diffusivity * duration))) for xi in x])
    computed = results.rh[-1, 0, :]
    assert np.max(np.abs(computed - expected)) < 0.02
    assert results.temperature[-1, 0, :].max() == pytest.approx(theta, abs=1e-6)


def test_grid_convergence_of_transient_solution():
    """Feineres Gitter naehert die analytische Loesung besser an."""
    material = _dry_material("halbunendlich")
    materials = MaterialLibrary([material])
    duration = 3 * HOUR
    errors = []
    for cell in (0.02, 0.005):
        grid = _one_dimensional_grid([("halbunendlich", 0.6)], materials,
                                     max_cell=cell, min_cell=cell)
        boundaries = bnd.BoundarySet()
        boundaries.add("links", bnd.FixedBoundary(30.0, 0.5, name="oberflaeche"))
        solver = Wufi2DSolver(
            grid, materials, boundaries,
            initial=InitialConditions(temperature=20.0, rh=0.5),
            options=SolverOptions(duration=duration, dt=60.0,
                                  output_interval=duration, latent_heat=False,
                                  liquid_transport=False))
        results = solver.run()
        w = float(material.w(0.5))
        alpha = material.lambda_dry / (material.rho * material.cp + w * physics.C_WATER)
        expected = 30.0 + (20.0 - 30.0) * np.array(
            [math.erf(xi / (2.0 * math.sqrt(alpha * duration))) for xi in grid.xc])
        errors.append(float(np.max(np.abs(results.temperature[-1, 0, :] - expected))))
    assert errors[1] < errors[0]


# ---------------------------------------------------------------------------
# Erhaltungssaetze
# ---------------------------------------------------------------------------

def test_mass_conservation_in_closed_domain_linear_isotherm():
    """Geschlossenes Gebiet: der Gesamtwassergehalt bleibt erhalten."""
    materials = MaterialLibrary([_vapour_material("A", w_f=20.0, mu=1.0),
                                 _vapour_material("B", w_f=20.0, mu=1.0)])
    grid = _one_dimensional_grid([("A", 0.05), ("B", 0.05)], materials,
                                 max_cell=0.005, min_cell=0.005)
    initial = InitialConditions(temperature=20.0, rh=0.5,
                                per_material={"A": {"rh": 0.9}, "B": {"rh": 0.3}})
    options = SolverOptions(duration=5 * DAY, dt=HOUR, output_interval=DAY,
                            latent_heat=False, liquid_transport=False)
    solver = Wufi2DSolver(grid, materials, boundaries=bnd.BoundarySet(),
                          initial=initial, options=options)
    results = solver.run()
    water = results.total_water
    assert water[-1] == pytest.approx(water[0], rel=1e-9)
    # Ausgleich hat stattgefunden
    assert np.ptp(results.rh[-1, 0, :]) < 0.05


def test_mass_conservation_with_nonlinear_isotherm():
    """Auch bei realer Sorptionsisotherme ist die Massenbilanz geschlossen.

    Das ist die Eigenschaft der modifizierten Picard-Iteration; die reine
    Kapazitaetsform wuerde hier driften.
    """
    materials = MaterialLibrary([default_library().get("Kalkputz"),
                                 default_library().get("Vollziegel (Altbau)")])
    grid = _one_dimensional_grid([("Kalkputz", 0.02), ("Vollziegel (Altbau)", 0.1)],
                                 materials, max_cell=0.005, min_cell=0.002)
    initial = InitialConditions(temperature=20.0, rh=0.5,
                                per_material={"Kalkputz": {"rh": 0.95}})
    options = SolverOptions(duration=20 * DAY, dt=HOUR, output_interval=DAY,
                            latent_heat=False)
    solver = Wufi2DSolver(grid, materials, boundaries=bnd.BoundarySet(),
                          initial=initial, options=options)
    results = solver.run()
    water = results.total_water
    assert water[-1] == pytest.approx(water[0], rel=1e-4)


def test_energy_conservation_in_closed_domain():
    """Geschlossenes Gebiet: die Enthalpie bleibt (bis auf Latentwaerme) erhalten."""
    materials = MaterialLibrary([_dry_material("A", lambda_dry=1.0),
                                 _dry_material("B", lambda_dry=1.0)])
    grid = _one_dimensional_grid([("A", 0.05), ("B", 0.05)], materials,
                                 max_cell=0.005, min_cell=0.005)
    initial = InitialConditions(temperature=20.0, rh=0.5,
                                per_material={"A": {"temperature": 30.0},
                                              "B": {"temperature": 10.0}})
    options = SolverOptions(duration=2 * DAY, dt=HOUR, output_interval=DAY,
                            latent_heat=False, liquid_transport=False)
    solver = Wufi2DSolver(grid, materials, boundaries=bnd.BoundarySet(),
                          initial=initial, options=options)
    results = solver.run()
    volume = grid.cell_volume[grid.active]
    start = np.nansum(results.temperature[0][grid.active] * volume)
    end = np.nansum(results.temperature[-1][grid.active] * volume)
    assert end == pytest.approx(start, rel=1e-6)
    assert np.ptp(results.temperature[-1][grid.active]) < 0.5  # ausgeglichen


# ---------------------------------------------------------------------------
# 2D-Eigenschaften
# ---------------------------------------------------------------------------

def test_symmetric_geometry_gives_symmetric_result():
    """Symmetrisches Modell -> symmetrisches Temperaturfeld."""
    materials = MaterialLibrary([_dry_material("Beton", lambda_dry=2.0),
                                 _dry_material("Daemmung", lambda_dry=0.04)])
    regions = [
        Region("Beton", rectangle(0.0, 0.0, 0.2, 0.4)),
        Region("Daemmung", rectangle(0.0, 0.15, 0.2, 0.1)),  # mittige Stoerung
    ]
    grid = build_grid(regions, materials=materials, max_cell=0.02, min_cell=0.01)
    boundaries = bnd.BoundarySet()
    boundaries.add("links", bnd.exterior_surface(ConstantClimate(-5.0, 0.8),
                                                 solar_absorptance=0.0,
                                                 rain_absorption=0.0, emissivity=0.0))
    boundaries.add("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5)))
    solver = Wufi2DSolver(grid, materials, boundaries,
                          initial=InitialConditions(temperature=10.0, rh=0.5),
                          options=SolverOptions(latent_heat=False))
    temperature, _ = solver.solve_steady_state()
    assert np.allclose(temperature, temperature[::-1, :], atol=1e-6)


def test_thermal_bridge_increases_heat_flow():
    """Eine Betonrippe in der Daemmebene erhoeht den Waermestrom (Psi > 0)."""
    materials = MaterialLibrary([_dry_material("Beton", lambda_dry=2.1),
                                 _dry_material("Daemmung", lambda_dry=0.035)])
    height = 0.5
    boundaries = bnd.BoundarySet()
    boundaries.add("links", bnd.exterior_surface(ConstantClimate(-5.0, 0.8),
                                                 solar_absorptance=0.0,
                                                 rain_absorption=0.0, emissivity=0.0))
    boundaries.add("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5)))
    options = SolverOptions(duration=60 * DAY, dt=6 * HOUR,
                            output_interval=60 * DAY, latent_heat=False)

    def heat_flow(regions):
        grid = build_grid(regions, materials=materials, max_cell=0.02, min_cell=0.005)
        solver = Wufi2DSolver(grid, materials, boundaries,
                              initial=InitialConditions(temperature=10.0, rh=0.5),
                              options=options)
        return solver.run().surfaces["innen"].heat_flux[-1]

    undisturbed = [Region("Daemmung", rectangle(0.0, 0.0, 0.16, height)),
                   Region("Beton", rectangle(0.16, 0.0, 0.2, height))]
    with_bridge = undisturbed + [
        Region("Beton", rectangle(0.0, 0.2, 0.16, 0.1), priority=1)]
    assert heat_flow(with_bridge) > 1.2 * heat_flow(undisturbed)


def test_inactive_cells_are_excluded():
    """Inaktive Zellen liefern NaN und beeinflussen das Ergebnis nicht."""
    materials = MaterialLibrary([_dry_material("Beton", lambda_dry=2.0)])
    regions = [Region("Beton", rectangle(0.0, 0.0, 0.3, 0.1)),
               Region("Beton", rectangle(0.0, 0.1, 0.1, 0.2))]
    grid = build_grid(regions, materials=materials, max_cell=0.05, min_cell=0.025)
    boundaries = bnd.BoundarySet()
    boundaries.add(bnd.SideSelector("bottom"),
                   bnd.exterior_surface(ConstantClimate(-5.0, 0.8),
                                        solar_absorptance=0.0, rain_absorption=0.0,
                                        emissivity=0.0))
    boundaries.add(bnd.SideSelector("top"),
                   bnd.interior_surface(ConstantClimate(20.0, 0.5)))
    solver = Wufi2DSolver(grid, materials, boundaries,
                          options=SolverOptions(duration=DAY, dt=HOUR,
                                                output_interval=DAY,
                                                latent_heat=False))
    results = solver.run()
    inactive = ~grid.active
    assert np.all(np.isnan(results.temperature[-1][inactive]))
    assert np.all(np.isfinite(results.temperature[-1][grid.active]))


# ---------------------------------------------------------------------------
# Numerik
# ---------------------------------------------------------------------------

def test_numpy_fallback_matches_scipy():
    """Der SOR-Fallback ohne SciPy liefert dasselbe Ergebnis."""
    materials = MaterialLibrary([_dry_material("Beton", lambda_dry=1.5)])
    boundaries = bnd.BoundarySet()
    boundaries.add("links", bnd.exterior_surface(ConstantClimate(-5.0, 0.8),
                                                 solar_absorptance=0.0,
                                                 rain_absorption=0.0, emissivity=0.0))
    boundaries.add("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5)))
    fields = []
    for use_scipy in (True, False):
        grid = _one_dimensional_grid([("Beton", 0.2)], materials, max_cell=0.02,
                                     min_cell=0.01)
        solver = Wufi2DSolver(
            grid, materials, boundaries,
            initial=InitialConditions(temperature=10.0, rh=0.5),
            options=SolverOptions(duration=12 * HOUR, dt=HOUR,
                                  output_interval=12 * HOUR, latent_heat=False,
                                  use_scipy=use_scipy))
        results = solver.run()
        fields.append(results.temperature[-1, 0, :])
    assert np.allclose(fields[0], fields[1], atol=1e-6)


def test_rain_load_wets_exterior_surface():
    """Schlagregen erhoeht den Wassergehalt an der bewitterten Oberflaeche."""
    materials = MaterialLibrary([default_library().get("Kalkputz"),
                                 default_library().get("Vollziegel (Altbau)")])
    grid = _one_dimensional_grid([("Kalkputz", 0.02), ("Vollziegel (Altbau)", 0.24)],
                                 materials, max_cell=0.01, min_cell=0.002)
    climate = ConstantClimate(10.0, 0.8, rain=0.5 / 3600.0)  # 0.5 mm/h
    boundaries = bnd.BoundarySet()
    boundaries.add("links", bnd.exterior_surface(climate, solar_absorptance=0.0,
                                                 rain_absorption=0.7, emissivity=0.0))
    boundaries.add("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5)))
    options = SolverOptions(duration=2 * DAY, dt=1800.0, output_interval=DAY)
    solver = Wufi2DSolver(grid, materials, boundaries,
                          initial=InitialConditions(temperature=15.0, rh=0.5),
                          options=options)
    results = solver.run()
    assert results.total_water[-1] > results.total_water[0]
    # Aussenseite ist deutlich feuchter als die Innenseite
    assert results.rh[-1, 0, 0] > results.rh[-1, 0, -1]
    assert results.rh[-1, 0, 0] > 0.9


def test_water_content_limited_by_free_saturation():
    """Der Wassergehalt uebersteigt die freie Wassersaettigung nicht."""
    material = default_library().get("Kalkputz")
    materials = MaterialLibrary([material])
    grid = _one_dimensional_grid([("Kalkputz", 0.03)], materials, max_cell=0.005,
                                 min_cell=0.002)
    climate = ConstantClimate(20.0, 1.0, rain=5.0 / 3600.0)  # Starkregen
    boundaries = bnd.BoundarySet()
    boundaries.add("links", bnd.exterior_surface(climate, solar_absorptance=0.0,
                                                 rain_absorption=1.0, emissivity=0.0))
    solver = Wufi2DSolver(grid, materials, boundaries,
                          initial=InitialConditions(temperature=20.0, rh=0.6),
                          options=SolverOptions(duration=DAY, dt=600.0,
                                                output_interval=DAY))
    results = solver.run()
    assert np.nanmax(results.water_content) <= material.w_f * 1.001
    assert np.nanmax(results.rh) <= 1.0 + 1e-9


def test_solver_requires_boundary_for_steady_state():
    materials = MaterialLibrary([_dry_material("Beton")])
    grid = _one_dimensional_grid([("Beton", 0.1)], materials, max_cell=0.05,
                                 min_cell=0.05)
    solver = Wufi2DSolver(grid, materials, boundaries=bnd.BoundarySet())
    with pytest.raises(SolverError):
        solver.solve_steady_state()
