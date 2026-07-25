"""Tests der Gittererzeugung und der Geometriezuweisung."""

from __future__ import annotations

import numpy as np
import pytest

from wufi2d.grid import (Grid2D, GridError, Region, build_grid, build_layered_grid,
                         graded_spacing, points_in_polygon, polygon_area, rectangle)
from wufi2d.material import default_library


def test_graded_spacing_sums_to_length():
    for length in (0.001, 0.01, 0.1, 0.365, 1.0):
        sizes = graded_spacing(length, d_min=0.002, d_max=0.02, growth=1.3)
        assert sum(sizes) == pytest.approx(length, rel=1e-12)
        assert min(sizes) > 0.0
        assert max(sizes) <= 0.02 + 1e-12


def test_graded_spacing_refines_at_edges():
    sizes = graded_spacing(0.4, d_min=0.002, d_max=0.02, growth=1.3)
    assert sizes[0] == pytest.approx(0.002, rel=0.2)
    assert sizes[-1] == pytest.approx(0.002, rel=0.2)
    assert max(sizes) > sizes[0]  # Gitter waechst zur Mitte


def test_graded_spacing_single_cell_for_thin_layer():
    assert graded_spacing(0.001, d_min=0.002, d_max=0.02) == [0.001]


def test_graded_spacing_merges_tiny_middle_cell():
    """Intervalle knapp ueber zwei Zellbreiten (Restzelle wird eingerechnet)."""
    for length in (0.0081, 0.009, 0.010, 0.0119):
        sizes = graded_spacing(length, d_min=0.004, d_max=0.02, growth=1.3)
        assert sum(sizes) == pytest.approx(length, rel=1e-12)
        assert all(size > 0.0 for size in sizes)
        # keine Zelle kleiner als die Haelfte der kleinsten Vorgabe
        assert min(sizes) >= 0.5 * 0.004 - 1e-12


def test_graded_spacing_stays_symmetric():
    for length in (0.01, 0.05, 0.2, 0.365, 1.0):
        sizes = graded_spacing(length, d_min=0.002, d_max=0.02, growth=1.3)
        assert sizes == pytest.approx(sizes[::-1], rel=1e-12)


def test_polygon_helpers():
    square = rectangle(0.0, 0.0, 2.0, 3.0)
    assert polygon_area(square) == pytest.approx(6.0)
    inside = points_in_polygon(np.array([1.0, 3.0]), np.array([1.5, 1.5]), square)
    assert inside.tolist() == [True, False]


def test_build_grid_places_material_boundaries_on_grid_lines():
    regions = [
        Region("Vollziegel (Altbau)", rectangle(0.0, 0.0, 0.365, 0.1)),
        Region("Kalkputz", rectangle(0.365, 0.0, 0.015, 0.1)),
    ]
    grid = build_grid(regions, materials=default_library(), max_cell=0.02,
                      min_cell=0.002, max_cell_y=0.1, min_cell_y=0.1)
    assert np.any(np.isclose(grid.x_edges, 0.365))
    assert grid.x_edges[0] == pytest.approx(0.0)
    assert grid.x_edges[-1] == pytest.approx(0.38)
    assert grid.ny == 1
    assert grid.n_active == grid.nx
    # Materialzuordnung stimmt mit der Geometrie ueberein
    assert grid.material_of(0, 0) == "Vollziegel (Altbau)"
    assert grid.material_of(0, grid.nx - 1) == "Kalkputz"


def test_build_layered_grid_rows_and_thicknesses():
    grid = build_layered_grid([("Kalkzementputz", 0.02), ("Mineralwolle", 0.16),
                               ("Stahlbeton", 0.2)], height=0.1, n_rows=2,
                              materials=default_library())
    assert grid.ny == 2
    assert grid.x_edges[-1] == pytest.approx(0.38)
    volumes = grid.cell_volume
    for name, thickness in (("Kalkzementputz", 0.02), ("Mineralwolle", 0.16),
                            ("Stahlbeton", 0.2)):
        mask = grid.material_id == grid.material_names.index(name)
        assert volumes[mask].sum() == pytest.approx(thickness * 0.1, rel=1e-9)


def test_inactive_cells_for_l_shaped_component():
    # L-Form: aufgehende Wand plus Bodenplatte
    regions = [
        Region("Stahlbeton", rectangle(0.0, 0.0, 0.6, 0.2), name="Bodenplatte"),
        Region("Stahlbeton", rectangle(0.0, 0.2, 0.2, 0.6), name="Wand"),
    ]
    grid = build_grid(regions, materials=default_library(), max_cell=0.05, min_cell=0.02)
    assert grid.n_active < grid.nx * grid.ny  # es gibt inaktive Zellen
    # Punkt im ausgeschnittenen Bereich ist inaktiv
    assert grid.cell_at(0.5, 0.5) is None
    assert grid.cell_at(0.1, 0.5) is not None
    assert grid.cell_at(0.5, 0.1) is not None


def test_region_with_hole():
    region = Region("Stahlbeton", rectangle(0.0, 0.0, 0.4, 0.4),
                    holes=[rectangle(0.15, 0.15, 0.1, 0.1)])
    assert region.area() == pytest.approx(0.16 - 0.01)
    grid = build_grid([region], materials=default_library(), max_cell=0.02, min_cell=0.01)
    assert grid.cell_at(0.2, 0.2) is None  # Aussparung
    assert grid.cell_at(0.05, 0.05) is not None


def test_exposed_faces_for_rectangle():
    grid = build_grid([Region("Stahlbeton", rectangle(0.0, 0.0, 0.1, 0.1))],
                      materials=default_library(), max_cell=0.05, min_cell=0.05)
    faces = grid.exposed_faces()
    # 2x2-Gitter -> 8 Randflaechen, Gesamtlaenge = Umfang
    assert len(faces) == 8
    assert sum(f.length for f in faces) == pytest.approx(0.4)
    assert {f.side for f in faces} == {"left", "right", "bottom", "top"}


def test_exposed_faces_include_hole_boundary():
    region = Region("Stahlbeton", rectangle(0.0, 0.0, 0.3, 0.3),
                    holes=[rectangle(0.1, 0.1, 0.1, 0.1)])
    grid = build_grid([region], materials=default_library(), max_cell=0.1, min_cell=0.1)
    faces = grid.exposed_faces()
    total = sum(f.length for f in faces)
    assert total == pytest.approx(0.3 * 4 + 0.1 * 4)  # Aussenrand + Aussparung


def test_priority_resolves_overlap():
    regions = [
        Region("Stahlbeton", rectangle(0.0, 0.0, 0.2, 0.2), priority=0),
        Region("Mineralwolle", rectangle(0.05, 0.05, 0.1, 0.1), priority=1),
    ]
    grid = build_grid(regions, materials=default_library(), max_cell=0.05, min_cell=0.05)
    assert grid.material_of(*grid.cell_at(0.1, 0.1)) == "Mineralwolle"
    assert grid.material_of(*grid.cell_at(0.01, 0.01)) == "Stahlbeton"


def test_mesh_data_matches_active_cells():
    grid = build_grid([Region("Stahlbeton", rectangle(0.0, 0.0, 0.1, 0.1))],
                      materials=default_library(), max_cell=0.05, min_cell=0.05)
    vertices, quads, cells = grid.mesh_data()
    assert len(quads) == grid.n_active == len(cells)
    assert len(vertices) == (grid.nx + 1) * (grid.ny + 1)
    for quad in quads:
        assert all(0 <= index < len(vertices) for index in quad)


def test_grid_rejects_unknown_material():
    from wufi2d.material import MaterialError
    with pytest.raises(MaterialError):
        build_grid([Region("Unbekannt", rectangle(0, 0, 0.1, 0.1))],
                   materials=default_library())


def test_grid_rejects_non_monotone_edges():
    with pytest.raises(GridError):
        Grid2D(x_edges=[0.0, 0.2, 0.1], y_edges=[0.0, 0.1],
               material_id=np.zeros((1, 2), dtype=int), material_names=["a"])
