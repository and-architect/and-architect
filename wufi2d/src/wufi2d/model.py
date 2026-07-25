"""Vollstaendiges Modell als serialisierbares Objekt (JSON).

Das Modell buendelt Geometrie, Materialien, Randbedingungen, Anfangs-
bedingungen und Rechenoptionen. Damit laesst sich ein Bauteil in
Grasshopper zusammenstellen, als JSON ablegen und headless (CLI, CI,
Parameterstudie) rechnen -- oder umgekehrt.

Beispiel::

    from wufi2d import Model
    model = Model.load("beispiele/waermebruecke.json")
    ergebnis = model.run()
    print(ergebnis.summary())
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import boundary as bnd
from .climate import Climate, ConstantClimate, climate_from_dict
from .grid import Grid2D, Region, build_grid
from .material import Material, MaterialLibrary, default_library
from .results import Results
from .solver import InitialConditions, SolverOptions, Wufi2DSolver

SECONDS_PER_HOUR = 3600.0
SECONDS_PER_DAY = 86400.0

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Randbedingungen (De-)Serialisierung
# ---------------------------------------------------------------------------

def transfer_from_dict(data: Optional[Dict]) -> bnd.SurfaceTransfer:
    return bnd.SurfaceTransfer(**(data or {}))


def boundary_from_dict(data: Dict) -> bnd.BoundaryCondition:
    """Randbedingung aus einem Dictionary erzeugen."""
    kind = str(data.get("type", "exchange")).lower()
    name = data.get("name", "")
    if kind in ("adiabatic", "adiabat", "symmetrie"):
        return bnd.AdiabaticBoundary(name or "adiabat")
    if kind in ("fixed", "fest", "dirichlet"):
        return bnd.FixedBoundary(data["temperature"], data["rh"], name or "fest")
    if kind in ("exchange", "uebergang", "surface"):
        climate = climate_from_dict(data["climate"])
        preset = str(data.get("preset", "")).lower()
        if preset in ("exterior", "aussen"):
            transfer = bnd.exterior_transfer(**(data.get("transfer") or {}))
        elif preset in ("interior", "innen"):
            transfer = bnd.interior_transfer(**(data.get("transfer") or {}))
        else:
            transfer = transfer_from_dict(data.get("transfer"))
        return bnd.ExchangeBoundary(climate, transfer, name or "Uebergang")
    raise ValueError(f"Unbekannter Randbedingungstyp: {kind}")


def _climate_to_dict(climate: Climate) -> Dict:
    """Klima serialisieren (unterstuetzt die eingebauten Klimatypen)."""
    from .climate import InteriorClimateFromExterior, SineClimate, TabularClimate

    if isinstance(climate, ConstantClimate):
        return {"type": "constant", "temperature": climate.temperature, "rh": climate.rh,
                "solar": climate.solar, "rain": climate.rain, "wind": climate.wind}
    if isinstance(climate, SineClimate):
        return {"type": "sine",
                "mean_temperature": climate.mean_temperature,
                "amplitude_temperature": climate.amplitude_temperature,
                "mean_rh": climate.mean_rh,
                "amplitude_rh": climate.amplitude_rh,
                "daily_temperature_amplitude": climate.daily_temperature_amplitude,
                "daily_rh_amplitude": climate.daily_rh_amplitude,
                "phase_days": climate.phase_days,
                "solar_peak": climate.solar_peak,
                "rain": climate.rain,
                "wind": climate.wind}
    if isinstance(climate, InteriorClimateFromExterior):
        return {"type": "interior",
                "exterior": _climate_to_dict(climate.exterior),
                "moisture_load": climate.moisture_load,
                "temperature_range": list(climate.temperature_range),
                "interior_temperature_range": list(climate.interior_temperature_range),
                "rh_reference_range": list(climate.rh_reference_range),
                "rh_range": list(climate.rh_range),
                "averaging_days": climate.averaging_days}
    if isinstance(climate, TabularClimate):
        return {"type": "table",
                "hours": climate.hours.tolist(),
                "temperature": climate.temperature.tolist(),
                "rh": climate.rh.tolist(),
                "solar": climate.solar.tolist(),
                "rain": climate.rain.tolist(),
                "wind": climate.wind.tolist(),
                "name": climate.name}
    raise TypeError(f"Klima vom Typ {type(climate).__name__} kann nicht "
                    "serialisiert werden")


def _selector_to_dict(selector: bnd.Selector) -> Dict:
    if isinstance(selector, bnd.SideSelector):
        data = {"side": selector.side}
        if selector.x_range:
            data["x_range"] = list(selector.x_range)
        if selector.y_range:
            data["y_range"] = list(selector.y_range)
        return data
    if isinstance(selector, bnd.PolylineSelector):
        data = {"polyline": selector.points.tolist(), "tolerance": selector.tolerance}
        if selector.sides:
            data["sides"] = sorted(selector.sides)
        return data
    if isinstance(selector, bnd.BoxSelector):
        data = {"box": [selector.x_min, selector.y_min, selector.x_max, selector.y_max]}
        if selector.sides:
            data["sides"] = sorted(selector.sides)
        return data
    if isinstance(selector, bnd.AllFaces):
        return {"side": "alle"}
    raise TypeError(f"Selektor vom Typ {type(selector).__name__} kann nicht "
                    "serialisiert werden")


def _boundary_to_dict(condition: bnd.BoundaryCondition) -> Dict:
    if isinstance(condition, bnd.AdiabaticBoundary):
        return {"type": "adiabatic", "name": condition.name}
    if isinstance(condition, bnd.FixedBoundary):
        return {"type": "fixed", "name": condition.name,
                "temperature": condition.temperature, "rh": condition.rh}
    if isinstance(condition, bnd.ExchangeBoundary):
        transfer = condition.transfer
        return {"type": "exchange", "name": condition.name,
                "climate": _climate_to_dict(condition.climate),
                "transfer": {"alpha": transfer.alpha,
                             "wind_factor": transfer.wind_factor,
                             "beta": transfer.beta,
                             "sd": transfer.sd,
                             "solar_absorptance": transfer.solar_absorptance,
                             "emissivity": transfer.emissivity,
                             "rain_absorption": transfer.rain_absorption}}
    raise TypeError(f"Randbedingung vom Typ {type(condition).__name__} kann nicht "
                    "serialisiert werden")


# ---------------------------------------------------------------------------
# Modell
# ---------------------------------------------------------------------------

@dataclass
class GridOptions:
    """Parameter der Gittererzeugung."""

    max_cell: float = 0.02
    min_cell: float = 0.002
    growth: float = 1.3
    extra_x: List[float] = field(default_factory=list)
    extra_y: List[float] = field(default_factory=list)
    depth: float = 1.0
    max_cell_y: Optional[float] = None
    min_cell_y: Optional[float] = None

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [])}


@dataclass
class Model:
    """Komplettes Berechnungsmodell.

    Attribute
    ---------
    name:
        Bezeichnung des Bauteils.
    regions:
        Materialbereiche in der Schnittebene.
    boundaries:
        Liste ``[(Selektor, Randbedingung), ...]``.
    materials:
        Materialbibliothek. Ohne Angabe wird die Richtwert-Datenbank verwendet;
        eigene Materialien werden ergaenzt.
    grid_options / initial / options:
        Gitter-, Anfangs- und Loeserparameter.
    """

    name: str = "Bauteil"
    regions: List[Region] = field(default_factory=list)
    boundaries: List = field(default_factory=list)
    materials: Optional[MaterialLibrary] = None
    grid_options: GridOptions = field(default_factory=GridOptions)
    initial: InitialConditions = field(default_factory=InitialConditions)
    options: SolverOptions = field(default_factory=SolverOptions)
    description: str = ""

    # ------------------------------------------------------------------
    def library(self) -> MaterialLibrary:
        """Materialbibliothek des Modells (Standard + eigene Materialien)."""
        if self.materials is None:
            return default_library()
        library = MaterialLibrary(list(default_library()))
        for material in self.materials:
            library.add(material)
        return library

    def add_region(self, material: str, polygon, **kwargs) -> Region:
        region = Region(material=material, polygon=list(polygon), **kwargs)
        self.regions.append(region)
        return region

    def add_boundary(self, selector, condition: bnd.BoundaryCondition) -> "Model":
        self.boundaries.append((bnd.make_selector(selector), condition))
        return self

    def build_grid(self) -> Grid2D:
        options = self.grid_options
        return build_grid(self.regions, materials=self.library(),
                          max_cell=options.max_cell, min_cell=options.min_cell,
                          growth=options.growth, extra_x=options.extra_x,
                          extra_y=options.extra_y, depth=options.depth,
                          max_cell_y=options.max_cell_y, min_cell_y=options.min_cell_y)

    def boundary_set(self) -> bnd.BoundarySet:
        boundary_set = bnd.BoundarySet()
        for selector, condition in self.boundaries:
            boundary_set.add(selector, condition)
        return boundary_set

    def build_solver(self, grid: Optional[Grid2D] = None) -> Wufi2DSolver:
        return Wufi2DSolver(
            grid=grid or self.build_grid(),
            materials=self.library(),
            boundaries=self.boundary_set(),
            initial=self.initial,
            options=self.options,
            regions=self.regions,
        )

    def run(self, progress=None) -> Results:
        """Modell rechnen."""
        return self.build_solver().run(progress=progress)

    def run_steady_state(self):
        """Stationaere Loesung ``(T, phi)`` berechnen."""
        return self.build_solver().solve_steady_state()

    # ------------------------------------------------------------------
    # Serialisierung
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict:
        data = {
            "schema": SCHEMA_VERSION,
            "name": self.name,
            "description": self.description,
            "grid": self.grid_options.to_dict(),
            "regions": [region.to_dict() for region in self.regions],
            "boundaries": [
                {"selector": _selector_to_dict(selector),
                 "condition": _boundary_to_dict(condition)}
                for selector, condition in self.boundaries
            ],
            "initial": {"temperature": self.initial.temperature,
                        "rh": self.initial.rh,
                        "per_material": self.initial.per_material},
            "options": {k: v for k, v in self.options.__dict__.items()},
        }
        if self.materials is not None:
            data["materials"] = [m.to_dict() for m in self.materials]
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "Model":
        schema = int(data.get("schema", SCHEMA_VERSION))
        if schema > SCHEMA_VERSION:
            raise ValueError(f"Modell-Schema {schema} ist neuer als diese Version "
                             f"({SCHEMA_VERSION}) -- wufi2d aktualisieren")
        materials = None
        if data.get("materials"):
            materials = MaterialLibrary([Material.from_dict(m) for m in data["materials"]])
        model = cls(
            name=data.get("name", "Bauteil"),
            description=data.get("description", ""),
            regions=[Region.from_dict(r) for r in data.get("regions", [])],
            materials=materials,
            grid_options=GridOptions(**data.get("grid", {})),
            initial=InitialConditions(**data.get("initial", {})),
            options=SolverOptions(**data.get("options", {})),
        )
        for entry in data.get("boundaries", []):
            model.add_boundary(bnd.make_selector(entry["selector"]),
                               boundary_from_dict(entry["condition"]))
        return model

    def save(self, path) -> Path:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return path

    @classmethod
    def load(cls, path) -> "Model":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # ------------------------------------------------------------------
    def validate(self) -> List[str]:
        """Modell pruefen und Warnungen zurueckgeben (leere Liste = in Ordnung)."""
        warnings: List[str] = []
        if not self.regions:
            warnings.append("Keine Region definiert")
        library = self.library()
        for region in self.regions:
            library.get(region.material)  # loest MaterialError aus
            if region.area() <= 0:
                warnings.append(f"Region '{region.name or region.material}' hat "
                                "keine Flaeche")
        grid = self.build_grid()
        assignment = self.boundary_set().assign(grid.exposed_faces())
        exchange = [name for name, indices in assignment.groups.items()
                    if name != "adiabat"]
        if not exchange:
            warnings.append("Keine Uebergangs- oder Festwert-Randbedingung zugeordnet "
                            "-- das Bauteil ist vollstaendig abgedichtet")
        elif len(exchange) == 1:
            warnings.append(f"Nur eine wirksame Randbedingung ('{exchange[0]}') -- "
                            "ohne zweite Randbedingung stellt sich kein Gefaelle ein")
        # Schnittkanten eines Ausschnitts sind zu Recht adiabat (Symmetrie).
        # Verdaechtig ist erst, wenn kaum eine Flaeche getroffen wurde -- dann
        # passt in der Regel die Toleranz eines Kurven-Selektors nicht.
        total = sum(face.length for face in assignment.faces)
        assigned = sum(assignment.faces[k].length
                       for name, indices in assignment.groups.items()
                       if name != "adiabat" for k in indices)
        if total > 0 and 0 < assigned / total < 0.1:
            warnings.append(
                f"Nur {assigned / total * 100:.1f} % des Randes haben eine "
                "Randbedingung -- Selektoren bzw. deren Toleranz pruefen")
        smallest = min(grid.dx.min(), grid.dy.min())
        if self.options.dt > 0 and smallest < 1e-4:
            warnings.append(f"Sehr kleine Zellen ({smallest * 1000:.2f} mm) -- "
                            "Rechenzeit und Stabilitaet pruefen")
        if grid.n_active > 20000:
            warnings.append(f"{grid.n_active} aktive Zellen -- Rechenzeit beachten "
                            "(max_cell/min_cell vergroessern)")
        return warnings

    def describe(self) -> str:
        lines = [f"Modell: {self.name}"]
        if self.description:
            lines.append(self.description)
        for region in self.regions:
            lines.append(f"  Region '{region.name or region.material}': "
                         f"{region.material}, {region.area() * 1e4:.0f} cm2")
        for selector, condition in self.boundaries:
            lines.append(f"  {selector.describe()} -> {condition.describe()}")
        lines.append(f"  Dauer {self.options.duration / SECONDS_PER_DAY:.1f} d, "
                     f"dt {self.options.dt / SECONDS_PER_HOUR:.2f} h")
        return "\n".join(lines)
