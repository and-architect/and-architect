"""Tests der rhinounabhaengigen Teile des Rhino-/Grasshopper-Adapters.

Die Funktionen, die echte Rhino-Objekte erzeugen, koennen hier nicht geprueft
werden; getestet werden die Datenaufbereitung (Mesh-Struktur, Farbverlaeufe,
Isolinien) und die Fehlermeldung ohne Rhino.
"""

from __future__ import annotations

import numpy as np
import pytest

from wufi2d.grid import Region, build_grid, rectangle
from wufi2d.material import default_library
from wufi2d.rhino import (PALETTES, QUANTITY_PALETTE, colour_ramp, flat_mesh_data,
                          grid_lines, has_rhino, isotherm_points, legend_steps)


@pytest.fixture
def grid():
    regions = [Region("Stahlbeton", rectangle(0.0, 0.0, 0.2, 0.1)),
               Region("Mineralwolle", rectangle(0.2, 0.0, 0.1, 0.1))]
    return build_grid(regions, materials=default_library(), max_cell=0.05,
                      min_cell=0.05, max_cell_y=0.05, min_cell_y=0.05)


def test_flat_mesh_data_structure(grid):
    values = np.arange(grid.ny * grid.nx, dtype=float).reshape(grid.shape)
    vertices, quads, cell_values = flat_mesh_data(grid, values)
    assert len(quads) == grid.n_active
    assert len(vertices) == 4 * grid.n_active  # eigene Eckpunkte je Zelle
    assert len(cell_values) == grid.n_active
    # Erste Zelle liegt am Ursprung und hat die Groesse der ersten Zelle
    x0, y0, _ = vertices[0]
    x1, y1, _ = vertices[2]
    assert x0 == pytest.approx(0.0)
    assert y0 == pytest.approx(0.0)
    assert x1 == pytest.approx(grid.dx[0])
    assert y1 == pytest.approx(grid.dy[0])


def test_flat_mesh_data_unit_scale(grid):
    values = np.zeros(grid.shape)
    vertices, _, _ = flat_mesh_data(grid, values, unit_scale=1000.0)
    assert max(v[0] for v in vertices) == pytest.approx(300.0)  # 0.3 m -> 300 mm


def test_flat_mesh_data_accepts_cell_value_list(grid):
    values = list(range(grid.n_active))
    _, quads, cell_values = flat_mesh_data(grid, values)
    assert len(quads) == grid.n_active
    assert cell_values == [float(v) for v in values]


def test_flat_mesh_data_rejects_wrong_length(grid):
    with pytest.raises(ValueError):
        flat_mesh_data(grid, [1.0, 2.0])


def test_flat_mesh_data_skips_inactive_cells():
    regions = [Region("Stahlbeton", rectangle(0.0, 0.0, 0.2, 0.1)),
               Region("Stahlbeton", rectangle(0.0, 0.1, 0.1, 0.1))]
    grid = build_grid(regions, materials=default_library(), max_cell=0.05,
                      min_cell=0.05)
    values = np.zeros(grid.shape)
    _, quads, _ = flat_mesh_data(grid, values)
    assert len(quads) == grid.n_active < grid.nx * grid.ny


def test_colour_ramp_endpoints_and_length():
    colours = colour_ramp([0.0, 0.5, 1.0], 0.0, 1.0, palette="temperatur")
    assert len(colours) == 3
    assert colours[0] == PALETTES["temperatur"][0]
    assert colours[-1] == PALETTES["temperatur"][-1]
    for colour in colours:
        assert all(0 <= channel <= 255 for channel in colour)


def test_colour_ramp_handles_nan_and_constant_field():
    colours = colour_ramp([1.0, float("nan"), 1.0])
    assert colours[1] == (190, 190, 190)  # inaktive Zelle -> neutral
    assert colours[0] == colours[2]


def test_colour_ramp_clamps_outside_range():
    low, high = colour_ramp([-5.0, 5.0], 0.0, 1.0)
    assert low == PALETTES["temperatur"][0]
    assert high == PALETTES["temperatur"][-1]


def test_colour_ramp_unknown_palette():
    with pytest.raises(KeyError):
        colour_ramp([0.0, 1.0], palette="gibt es nicht")


def test_quantity_palette_covers_result_quantities():
    for quantity in ("temperature", "rh", "water_content", "moisture_mass_percent"):
        assert QUANTITY_PALETTE[quantity] in PALETTES


def test_legend_steps():
    assert legend_steps(0.0, 10.0, 6) == pytest.approx([0.0, 2.0, 4.0, 6.0, 8.0, 10.0])
    with pytest.raises(ValueError):
        legend_steps(0.0, 1.0, 1)


def test_grid_lines_count_and_extent(grid):
    lines = grid_lines(grid)
    assert len(lines) == len(grid.x_edges) + len(grid.y_edges)
    x_values = [a[0] for a, _ in lines] + [b[0] for _, b in lines]
    assert max(x_values) == pytest.approx(0.3)


def test_isotherm_points_interpolates_crossing(grid):
    # linearer Verlauf 0..10 ueber x -> Isolinie 5.0 liegt in der Mitte
    field = np.zeros(grid.shape)
    field[:, :] = np.linspace(0.0, 10.0, grid.nx)[None, :]
    points = isotherm_points(grid, field, 5.0)
    assert len(points) == grid.ny  # je Zeile ein Durchgang
    for x, y in points:
        assert x == pytest.approx(0.5 * (grid.xc[0] + grid.xc[-1]), abs=1e-9)
        assert 0.0 <= y <= 0.1


def test_isotherm_points_empty_outside_range(grid):
    field = np.full(grid.shape, 3.0)
    assert isotherm_points(grid, field, 50.0) == []


def test_isotherm_points_rejects_wrong_shape(grid):
    with pytest.raises(ValueError):
        isotherm_points(grid, np.zeros(5), 1.0)


def test_has_rhino_is_false_headless():
    assert has_rhino() is False
