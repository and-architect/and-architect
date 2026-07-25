"""wufi2d -- gekoppelte 2D-Waerme- und Feuchtesimulation nach dem
WUFI-/Kuenzel-Prinzip (Fraunhofer IBP) fuer Rhino 8/9 und Grasshopper.

Der Rechenkern ist reines Python + NumPy und laeuft unabhaengig von Rhino
(headless, Tests, CI). Die Rhino-/Grasshopper-Anbindung liegt in den
Verzeichnissen ``rhino/`` und ``grasshopper/`` und wandelt lediglich
Geometrie in Regionen um.

Schnellstart::

    from wufi2d import (ConstantClimate, InitialConditions, Model,
                        SolverOptions, rectangle)
    from wufi2d import boundary as bnd

    model = Model(name="Aussenwand")
    model.add_region("Vollziegel (Altbau)", rectangle(0.0, 0.0, 0.365, 0.5))
    model.add_boundary("links", bnd.exterior_surface(ConstantClimate(-5.0, 0.8)))
    model.add_boundary("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5)))
    model.options = SolverOptions(duration=30 * 86400.0)
    ergebnis = model.run()
    print(ergebnis.summary())

Hinweis: Dies ist eine eigenstaendige Implementierung der veroeffentlichten
Modellgleichungen (Kuenzel 1995). Es ist kein WUFI, keine Portierung von
WUFI-Code und enthaelt keine WUFI-Materialdatenbank. "WUFI" ist eine Marke
des Fraunhofer-Instituts fuer Bauphysik.
"""

from __future__ import annotations

__version__ = "0.1.0"

from . import analysis, boundary, climate, grid, material, physics
from .analysis import (moisture_balance, mould_risk_at_point, mould_risk_at_surface,
                       psi_value, report, temperature_factor,
                       thermal_coupling_coefficient, wood_moisture_check)
from .boundary import (AdiabaticBoundary, BoundarySet, ExchangeBoundary, FixedBoundary,
                       PolylineSelector, SideSelector, SurfaceTransfer,
                       exterior_surface, interior_surface)
from .climate import (ClimateState, ConstantClimate, InteriorClimateFromExterior,
                      SineClimate, TabularClimate, driving_rain, read_climate_csv)
from .grid import Grid2D, Region, build_grid, build_layered_grid, rectangle
from .material import (Material, MaterialLibrary, air_layer, default_library,
                       get_material, membrane, variable_membrane)
from .model import GridOptions, Model
from .results import Results
from .solver import InitialConditions, SolverOptions, Wufi2DSolver

__all__ = [
    "__version__",
    # Module
    "analysis", "boundary", "climate", "grid", "material", "physics",
    # Material
    "Material", "MaterialLibrary", "default_library", "get_material",
    "air_layer", "membrane", "variable_membrane",
    # Geometrie
    "Grid2D", "Region", "build_grid", "build_layered_grid", "rectangle",
    # Klima
    "ClimateState", "ConstantClimate", "SineClimate", "TabularClimate",
    "InteriorClimateFromExterior", "read_climate_csv", "driving_rain",
    # Rand
    "AdiabaticBoundary", "BoundarySet", "ExchangeBoundary", "FixedBoundary",
    "PolylineSelector", "SideSelector", "SurfaceTransfer",
    "exterior_surface", "interior_surface",
    # Rechnen
    "InitialConditions", "SolverOptions", "Wufi2DSolver", "Model", "GridOptions",
    "Results",
    # Auswertung
    "moisture_balance", "mould_risk_at_point", "mould_risk_at_surface",
    "psi_value", "report", "temperature_factor", "thermal_coupling_coefficient",
    "wood_moisture_check",
]
