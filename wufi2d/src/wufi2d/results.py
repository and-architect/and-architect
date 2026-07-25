"""Ergebnisverwaltung: Felder, Oberflaechenwerte, Bilanzen, Export."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .grid import Grid2D

SECONDS_PER_HOUR = 3600.0
SECONDS_PER_DAY = 86400.0


@dataclass
class SurfaceSeries:
    """Zeitreihen an einer Randbedingungsgruppe (flaechengewichtete Mittel).

    ``temperature`` und ``rh`` sind die *Oberflaechen*werte (nicht die
    Klimawerte), rekonstruiert aus dem Waerme- bzw. Dampfstrom durch den
    Uebergangswiderstand. ``heat_flux`` ist positiv, wenn Waerme in das
    Bauteil hineinstroemt, ``moisture_flux`` analog fuer Feuchte.
    """

    name: str
    area: float = 0.0
    temperature: np.ndarray = field(default_factory=lambda: np.zeros(0))
    rh: np.ndarray = field(default_factory=lambda: np.zeros(0))
    heat_flux: np.ndarray = field(default_factory=lambda: np.zeros(0))
    moisture_flux: np.ndarray = field(default_factory=lambda: np.zeros(0))
    min_temperature: np.ndarray = field(default_factory=lambda: np.zeros(0))
    max_rh: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def cumulative_heat(self, times: np.ndarray) -> np.ndarray:
        """Kumulierte Waermemenge [J] (positiv = Eintrag in das Bauteil)."""
        return _cumulative_trapezoid(times, self.heat_flux)

    def cumulative_moisture(self, times: np.ndarray) -> np.ndarray:
        """Kumulierte Feuchtemenge [kg] (positiv = Eintrag in das Bauteil)."""
        return _cumulative_trapezoid(times, self.moisture_flux)


def _cumulative_trapezoid(times: np.ndarray, values: np.ndarray) -> np.ndarray:
    times = np.asarray(times, dtype=float)
    values = np.asarray(values, dtype=float)
    if len(times) < 2:
        return np.zeros_like(values)
    increments = 0.5 * (values[1:] + values[:-1]) * np.diff(times)
    return np.concatenate([[0.0], np.cumsum(increments)])


@dataclass
class Results:
    """Ergebnisse einer transienten Berechnung.

    Felder haben die Form ``(n_zeitschritte, ny, nx)``; inaktive Zellen sind
    ``NaN``. Zeiten in Sekunden ab Simulationsbeginn.
    """

    times: np.ndarray
    temperature: np.ndarray
    rh: np.ndarray
    water_content: np.ndarray
    grid: Grid2D
    surfaces: Dict[str, SurfaceSeries] = field(default_factory=dict)
    water_by_material: Dict[str, np.ndarray] = field(default_factory=dict)
    meta: Dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Basis
    # ------------------------------------------------------------------
    @property
    def n_steps(self) -> int:
        return len(self.times)

    @property
    def hours(self) -> np.ndarray:
        return self.times / SECONDS_PER_HOUR

    @property
    def days(self) -> np.ndarray:
        return self.times / SECONDS_PER_DAY

    @property
    def total_water(self) -> np.ndarray:
        """Gesamtwassergehalt des Bauteils [kg] je Ausgabezeitpunkt."""
        volume = self.grid.cell_volume
        mask = self.grid.active
        return np.array([np.nansum(w[mask] * volume[mask]) for w in self.water_content])

    def index_at(self, time: float) -> int:
        """Index des Ausgabezeitpunkts, der ``time`` [s] am naechsten liegt."""
        return int(np.argmin(np.abs(self.times - float(time))))

    def field(self, quantity: str, time: Optional[float] = None,
              step: Optional[int] = None) -> np.ndarray:
        """Feld einer Groesse zu einem Zeitpunkt.

        ``quantity``: ``"temperature"``, ``"rh"``, ``"water_content"``,
        ``"moisture_mass_percent"`` oder ``"vapour_pressure"``.
        """
        if step is None:
            step = self.n_steps - 1 if time is None else self.index_at(time)
        if quantity in ("temperature", "T", "temperatur"):
            return self.temperature[step]
        if quantity in ("rh", "phi", "feuchte"):
            return self.rh[step]
        if quantity in ("water_content", "w", "wassergehalt"):
            return self.water_content[step]
        if quantity in ("moisture_mass_percent", "u"):
            return self.moisture_mass_percent(step)
        if quantity in ("vapour_pressure", "pv"):
            from . import physics
            return physics.vapour_pressure(self.temperature[step], self.rh[step])
        raise KeyError(f"Unbekannte Groesse: {quantity}")

    def moisture_mass_percent(self, step: int = -1) -> np.ndarray:
        """Massebezogener Feuchtegehalt [M.-%] je Zelle."""
        rho = np.asarray(self.meta.get("density_field"), dtype=float)
        if rho.shape != self.grid.shape:
            raise KeyError("Dichtefeld nicht in den Ergebnissen gespeichert")
        with np.errstate(invalid="ignore", divide="ignore"):
            return 100.0 * self.water_content[step] / np.where(rho > 0, rho, np.nan)

    # ------------------------------------------------------------------
    # Punkt- und Profilauswertung
    # ------------------------------------------------------------------
    def cell_series(self, x: float, y: float) -> Dict[str, np.ndarray]:
        """Zeitreihen in der Zelle am Punkt ``(x, y)``."""
        cell = self.grid.cell_at(x, y)
        if cell is None:
            raise ValueError(f"Punkt ({x}, {y}) liegt nicht im aktiven Gebiet")
        j, i = cell
        return {
            "times": self.times,
            "temperature": self.temperature[:, j, i],
            "rh": self.rh[:, j, i],
            "water_content": self.water_content[:, j, i],
        }

    def profile(self, quantity: str = "temperature", y: Optional[float] = None,
                time: Optional[float] = None) -> Tuple[np.ndarray, np.ndarray]:
        """Horizontales Schnittprofil ``(x, Werte)`` in der Hoehe ``y``."""
        step = self.n_steps - 1 if time is None else self.index_at(time)
        values = self.field(quantity, step=step)
        yc = self.grid.yc
        j = int(np.argmin(np.abs(yc - (yc.mean() if y is None else y))))
        return self.grid.xc, values[j]

    def extremes(self) -> Dict[str, float]:
        """Wichtigste Extremwerte der Rechnung."""
        return {
            "temperature_min": float(np.nanmin(self.temperature)),
            "temperature_max": float(np.nanmax(self.temperature)),
            "rh_min": float(np.nanmin(self.rh)),
            "rh_max": float(np.nanmax(self.rh)),
            "water_content_max": float(np.nanmax(self.water_content)),
            "water_total_start": float(self.total_water[0]),
            "water_total_end": float(self.total_water[-1]),
        }

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def cell_values(self, quantity: str = "temperature", time: Optional[float] = None
                    ) -> List[float]:
        """Werte je aktiver Zelle in der Reihenfolge von :meth:`Grid2D.mesh_data`."""
        values = self.field(quantity, time=time)
        _, _, cells = self.grid.mesh_data()
        return [float(values[j, i]) for j, i in cells]

    def to_npz(self, path) -> Path:
        """Ergebnisse kompakt als ``.npz`` speichern."""
        path = Path(path)
        np.savez_compressed(
            path,
            times=self.times,
            temperature=self.temperature,
            rh=self.rh,
            water_content=self.water_content,
            x_edges=self.grid.x_edges,
            y_edges=self.grid.y_edges,
            material_id=self.grid.material_id,
            material_names=np.array(self.grid.material_names, dtype=object),
            depth=self.grid.depth,
            meta=json.dumps(_jsonify(self.meta)),
            surfaces=json.dumps({
                name: {
                    "area": s.area,
                    "temperature": s.temperature.tolist(),
                    "rh": s.rh.tolist(),
                    "heat_flux": s.heat_flux.tolist(),
                    "moisture_flux": s.moisture_flux.tolist(),
                    "min_temperature": s.min_temperature.tolist(),
                    "max_rh": s.max_rh.tolist(),
                }
                for name, s in self.surfaces.items()
            }),
            water_by_material=json.dumps({k: v.tolist() for k, v in
                                          self.water_by_material.items()}),
        )
        return path

    @classmethod
    def from_npz(cls, path) -> "Results":
        data = np.load(Path(path), allow_pickle=True)
        grid = Grid2D(
            x_edges=data["x_edges"],
            y_edges=data["y_edges"],
            material_id=data["material_id"],
            material_names=[str(n) for n in data["material_names"]],
            depth=float(data["depth"]),
        )
        surfaces = {}
        for name, payload in json.loads(str(data["surfaces"])).items():
            surfaces[name] = SurfaceSeries(
                name=name,
                area=payload["area"],
                temperature=np.asarray(payload["temperature"], dtype=float),
                rh=np.asarray(payload["rh"], dtype=float),
                heat_flux=np.asarray(payload["heat_flux"], dtype=float),
                moisture_flux=np.asarray(payload["moisture_flux"], dtype=float),
                min_temperature=np.asarray(payload["min_temperature"], dtype=float),
                max_rh=np.asarray(payload["max_rh"], dtype=float),
            )
        return cls(
            times=data["times"],
            temperature=data["temperature"],
            rh=data["rh"],
            water_content=data["water_content"],
            grid=grid,
            surfaces=surfaces,
            water_by_material={k: np.asarray(v, dtype=float) for k, v in
                               json.loads(str(data["water_by_material"])).items()},
            meta=json.loads(str(data["meta"])),
        )

    def to_csv(self, path, quantity: str = "summary") -> Path:
        """Zeitreihen als CSV exportieren.

        ``quantity="summary"`` schreibt Gesamtwassergehalt, Extremwerte und
        Oberflaechenwerte je Ausgabezeitpunkt. Andernfalls wird das Zeit-
        verhalten der angegebenen Feldgroesse in allen aktiven Zellen
        geschrieben (breite Tabelle).
        """
        path = Path(path)
        if quantity == "summary":
            header = ["zeit_h", "zeit_d", "wasser_total_kg",
                      "T_min_C", "T_max_C", "rF_min", "rF_max"]
            for name in self.water_by_material:
                header.append(f"wasser_{name}_kg")
            for name in self.surfaces:
                header += [f"{name}_T_C", f"{name}_rF",
                           f"{name}_q_W", f"{name}_g_kgs"]
            rows = []
            total = self.total_water
            for k, t in enumerate(self.times):
                row = [t / SECONDS_PER_HOUR, t / SECONDS_PER_DAY, total[k],
                       np.nanmin(self.temperature[k]), np.nanmax(self.temperature[k]),
                       np.nanmin(self.rh[k]), np.nanmax(self.rh[k])]
                row += [values[k] for values in self.water_by_material.values()]
                for surface in self.surfaces.values():
                    row += [surface.temperature[k], surface.rh[k],
                            surface.heat_flux[k], surface.moisture_flux[k]]
                rows.append(row)
        else:
            values = np.asarray([self.field(quantity, step=k) for k in range(self.n_steps)])
            _, _, cells = self.grid.mesh_data()
            header = ["zeit_h"] + [f"x{self.grid.xc[i]:.4f}_y{self.grid.yc[j]:.4f}"
                                   for j, i in cells]
            rows = [[t / SECONDS_PER_HOUR] + [values[k][j, i] for j, i in cells]
                    for k, t in enumerate(self.times)]
        lines = [";".join(header)]
        for row in rows:
            lines.append(";".join(f"{v:.6g}" for v in row))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def summary(self) -> str:
        extremes = self.extremes()
        lines = [
            f"Simulationsdauer: {self.times[-1] / SECONDS_PER_DAY:.1f} d "
            f"({self.n_steps} Ausgabezeitpunkte)",
            f"Temperatur: {extremes['temperature_min']:.2f} .. "
            f"{extremes['temperature_max']:.2f} degC",
            f"Rel. Feuchte: {extremes['rh_min'] * 100:.1f} .. "
            f"{extremes['rh_max'] * 100:.1f} %",
            f"Wassergehalt gesamt: {extremes['water_total_start']:.3f} kg -> "
            f"{extremes['water_total_end']:.3f} kg",
        ]
        for name, values in self.water_by_material.items():
            lines.append(f"  {name}: {values[0]:.3f} -> {values[-1]:.3f} kg")
        for name, surface in self.surfaces.items():
            lines.append(
                f"Oberflaeche '{name}': T {surface.temperature.min():.2f} .. "
                f"{surface.temperature.max():.2f} degC, rF max "
                f"{surface.max_rh.max() * 100:.1f} %, "
                f"q mittel {surface.heat_flux.mean():.2f} W")
        if self.meta.get("clamped_steps"):
            lines.append(
                f"Hinweis: in {self.meta['clamped_steps']} Zeitschritten wurde die "
                "freie Wassersaettigung erreicht (Begrenzung auf phi = 1).")
        return "\n".join(lines)


def _jsonify(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    return obj
