"""Gekoppelter Waerme- und Feuchteloeser (2D, Finite-Volumen, implizit).

Diskretisierung
---------------
Finite-Volumen-Verfahren auf dem strukturierten Gitter aus :mod:`wufi2d.grid`.
Die Transportkoeffizienten an den Zellgrenzen werden als Reihenschaltung der
Halbzellenwiderstaende gebildet -- damit sind Materialspruenge korrekt
abgebildet. Zeitintegration: implizites Euler-Verfahren.

Nichtlineare Kopplung
---------------------
Feuchte- und Waermebilanz werden je Zeitschritt abwechselnd geloest und
ueber eine Picard-Iteration zur Konvergenz gebracht (Materialkennwerte,
Saettigungsdampfdruck und Latentwaermequelle werden dabei aktualisiert).
Konvergiert ein Zeitschritt nicht, wird der Zeitschritt halbiert.

Potentiale sind -- wie bei Kuenzel -- Temperatur ``T`` [degC] und relative
Feuchte ``phi`` [-]. ``phi`` ist an Materialgrenzen stetig, weshalb es sich
als Feuchtepotential fuer geschichtete Bauteile eignet.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import physics
from .boundary import (AdiabaticBoundary, BoundaryAssignment, BoundaryCondition,
                       BoundarySet, ExchangeBoundary, FixedBoundary)
from .grid import Face, Grid2D, Region
from .linalg import ConvergenceError, solve_five_point
from .material import Material, MaterialLibrary
from .results import Results, SurfaceSeries

SECONDS_PER_HOUR = 3600.0
SECONDS_PER_DAY = 86400.0

RAIN_RAMP = 0.05
"""Breite des geglaetteten Uebergangs der Regenaufnahme, bezogen auf w_f.

Ab ``w = (1 - RAIN_RAMP) * w_f`` wird die aufgenommene Regenmenge linear auf
null zurueckgefahren; darueber laeuft das Wasser vollstaendig ab.
"""


class SolverError(RuntimeError):
    """Die Berechnung konnte nicht durchgefuehrt werden."""


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

@dataclass
class InitialConditions:
    """Anfangsbedingungen.

    ``per_material`` erlaubt materialweise Startwerte, z.B.
    ``{"Beton C25/30": {"rh": 0.95}}`` fuer Baufeuchte.
    """

    temperature: float = 20.0
    rh: float = 0.8
    per_material: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def fields(self, grid: Grid2D, regions: Optional[Sequence[Region]] = None
               ) -> Tuple[np.ndarray, np.ndarray]:
        temperature = np.full(grid.shape, float(self.temperature))
        rh = np.full(grid.shape, float(self.rh))
        for name, values in self.per_material.items():
            if name not in grid.material_names:
                raise SolverError(
                    f"Anfangsbedingung fuer unbekanntes Material '{name}' "
                    f"(vorhanden: {grid.material_names})")
            mask = grid.material_id == grid.material_names.index(name)
            if "temperature" in values:
                temperature[mask] = float(values["temperature"])
            if "rh" in values:
                rh[mask] = float(values["rh"])
        if regions is not None and grid.region_index is not None:
            for k, region in enumerate(regions):
                mask = grid.region_index == k
                if not mask.any():
                    continue
                if region.initial_temperature is not None:
                    temperature[mask] = float(region.initial_temperature)
                if region.initial_rh is not None:
                    rh[mask] = float(region.initial_rh)
        rh = np.clip(rh, 1e-4, 1.0)
        return temperature, rh


@dataclass
class SolverOptions:
    """Steuerparameter der Berechnung."""

    duration: float = 365.0 * SECONDS_PER_DAY
    """Simulationsdauer [s]."""

    dt: float = SECONDS_PER_HOUR
    """Zeitschritt [s] (WUFI-typisch 1 h)."""

    output_interval: float = SECONDS_PER_DAY
    """Abstand der gespeicherten Feldausgaben [s]."""

    max_iterations: int = 30
    """Maximale Picard-Iterationen je Zeitschritt."""

    tol_temperature: float = 1e-3
    """Konvergenzkriterium Temperatur [K]."""

    tol_rh: float = 1e-6
    """Konvergenzkriterium relative Feuchte [-]."""

    relaxation: float = 1.0
    """Obergrenze des Relaxationsfaktors der Picard-Iteration (1.0 = keine
    Daempfung). Der Faktor wird automatisch reduziert, sobald die Iteration zu
    pendeln beginnt (siehe ``min_relaxation``)."""

    min_relaxation: float = 0.1
    """Kleinster Relaxationsfaktor der automatischen Daempfung."""

    adaptive_timestep: bool = True
    """Zeitschritt bei Konvergenzproblemen halbieren."""

    min_dt: float = 30.0
    """Kleinster zugelassener Zeitschritt [s]."""

    latent_heat: bool = True
    """Latentwaerme aus Verdunstung/Kondensation beruecksichtigen."""

    liquid_transport: bool = True
    """Kapillaren Fluessigtransport beruecksichtigen."""

    suction_at_rain: bool = True
    """An regenbelasteten Oberflaechen D_ws (Saugen) statt D_ww verwenden."""

    verbose: bool = False
    """Fortschritt auf der Konsole ausgeben."""

    use_scipy: Optional[bool] = None
    """``None`` = SciPy verwenden, wenn vorhanden."""


# ---------------------------------------------------------------------------
# interne Hilfsstrukturen
# ---------------------------------------------------------------------------

@dataclass
class _BoundaryGroup:
    """Vorberechnete Geometrie einer Randbedingungsgruppe."""

    condition: BoundaryCondition
    j: np.ndarray
    i: np.ndarray
    area: np.ndarray
    d_half: np.ndarray
    total_area: float
    surface_temperature: np.ndarray
    faces: List[Face] = field(default_factory=list)


def _cosine(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    """Richtungsaehnlichkeit zweier aufeinanderfolgender Iterationszuwaechse.

    Negative Werte bedeuten, dass der Zuwachs die Richtung umgekehrt hat --
    die Iteration pendelt.
    """
    x = a[mask]
    y = b[mask]
    norm = float(np.linalg.norm(x)) * float(np.linalg.norm(y))
    if norm < 1e-30:
        return 0.0
    return float(np.dot(x, y)) / norm


def _series_conductance(k_a, k_b, d_a, d_b):
    """Leitwert je Flaeche aus zwei Halbzellen (Reihenschaltung).

    ``k`` ist der Transportkoeffizient (lambda, delta_p oder D_phi), ``d`` der
    halbe Zellabstand. Ist einer der Koeffizienten null (dampfdichte Schicht,
    kein Fluessigtransport), sperrt die Flaeche vollstaendig.
    """
    shape = np.broadcast_shapes(np.shape(k_a), np.shape(k_b), np.shape(d_a), np.shape(d_b))
    k_a = np.broadcast_to(np.asarray(k_a, dtype=float), shape)
    k_b = np.broadcast_to(np.asarray(k_b, dtype=float), shape)
    d_a = np.broadcast_to(np.asarray(d_a, dtype=float), shape)
    d_b = np.broadcast_to(np.asarray(d_b, dtype=float), shape)
    resistance = (np.where(k_a > 0.0, d_a / np.where(k_a > 0.0, k_a, 1.0), np.inf)
                  + np.where(k_b > 0.0, d_b / np.where(k_b > 0.0, k_b, 1.0), np.inf))
    finite = np.isfinite(resistance) & (resistance > 0.0)
    return np.where(finite, 1.0 / np.where(finite, resistance, 1.0), 0.0)


# ---------------------------------------------------------------------------
# Loeser
# ---------------------------------------------------------------------------

class Wufi2DSolver:
    """Transienter 2D-Loeser fuer gekoppelten Waerme- und Feuchtetransport."""

    def __init__(self,
                 grid: Grid2D,
                 materials: MaterialLibrary,
                 boundaries: Optional[BoundarySet] = None,
                 initial: Optional[InitialConditions] = None,
                 options: Optional[SolverOptions] = None,
                 regions: Optional[Sequence[Region]] = None) -> None:
        self.grid = grid
        self.materials = materials
        self.boundaries = boundaries or BoundarySet()
        self.initial = initial or InitialConditions()
        self.options = options or SolverOptions()
        self.regions = list(regions) if regions else None

        self.active = grid.active
        self.dx = grid.dx
        self.dy = grid.dy
        self.volume = grid.cell_volume
        self.shape = grid.shape

        # Material je Zelle (als Maskenliste fuer vektorisierte Auswertung)
        self._material_masks: List[Tuple[Material, np.ndarray]] = []
        for mid, name in enumerate(grid.material_names):
            mask = grid.material_id == mid
            if mask.any():
                self._material_masks.append((materials.get(name), mask))
        if not self._material_masks:
            raise SolverError("Gitter enthaelt keine Zelle mit Material")

        self.density = self._map(lambda m, _: m.rho)
        self.w_saturation = self._map(lambda m, _: m.w_sat)

        # Kopplungen zwischen benachbarten aktiven Zellen
        self._link_x = (self.active[:, :-1] & self.active[:, 1:]
                        if self.grid.nx > 1 else np.zeros((self.grid.ny, 0), dtype=bool))
        self._link_y = (self.active[:-1, :] & self.active[1:, :]
                        if self.grid.ny > 1 else np.zeros((0, self.grid.nx), dtype=bool))
        self._area_x = (self.dy[:, None] * grid.depth) * np.ones((1, max(self.grid.nx - 1, 0)))
        self._area_y = (self.dx[None, :] * grid.depth) * np.ones((max(self.grid.ny - 1, 0), 1))
        self._dx_half_left = 0.5 * self.dx[None, :-1] if self.grid.nx > 1 else np.zeros((1, 0))
        self._dx_half_right = 0.5 * self.dx[None, 1:] if self.grid.nx > 1 else np.zeros((1, 0))
        self._dy_half_low = 0.5 * self.dy[:-1, None] if self.grid.ny > 1 else np.zeros((0, 1))
        self._dy_half_high = 0.5 * self.dy[1:, None] if self.grid.ny > 1 else np.zeros((0, 1))

        self.assignment: BoundaryAssignment = self.boundaries.assign(grid.exposed_faces())
        self._groups = self._build_groups(self.assignment)

        self.temperature, self.rh = self.initial.fields(grid, self.regions)
        self.temperature[~self.active] = np.nan
        self.rh[~self.active] = np.nan
        self._clamped_steps = 0
        self._suction_cells = np.zeros(self.shape, dtype=bool)

    # ------------------------------------------------------------------
    # Vorbereitung
    # ------------------------------------------------------------------
    def _map(self, func: Callable[[Material, np.ndarray], np.ndarray],
             *arrays: np.ndarray) -> np.ndarray:
        """Materialabhaengige Groesse als Feld auswerten."""
        out = np.zeros(self.shape, dtype=float)
        for material, mask in self._material_masks:
            args = [np.asarray(a)[mask] for a in arrays]
            out[mask] = func(material, *args) if args else func(material, None)
        return out

    def _build_groups(self, assignment: BoundaryAssignment) -> List[_BoundaryGroup]:
        groups: List[_BoundaryGroup] = []
        for name, indices in assignment.groups.items():
            condition = assignment.conditions[indices[0]]
            if isinstance(condition, AdiabaticBoundary):
                continue  # adiabat = kein Beitrag
            faces = [assignment.faces[k] for k in indices]
            j = np.array([f.j for f in faces], dtype=int)
            i = np.array([f.i for f in faces], dtype=int)
            area = np.array([f.length * self.grid.depth for f in faces], dtype=float)
            d_half = np.array([
                0.5 * (self.dx[f.i] if f.side in ("left", "right") else self.dy[f.j])
                for f in faces], dtype=float)
            groups.append(_BoundaryGroup(
                condition=condition, j=j, i=i, area=area, d_half=d_half,
                total_area=float(area.sum()),
                surface_temperature=np.full(len(faces), float(self.initial.temperature)),
                faces=faces))
        return groups

    # ------------------------------------------------------------------
    # Materialkennwerte zum aktuellen Zustand
    # ------------------------------------------------------------------
    def _properties(self, temperature: np.ndarray, rh: np.ndarray) -> Dict[str, np.ndarray]:
        """Alle feuchte- und temperaturabhaengigen Kennwerte als Felder.

        Bewusst *ein* Durchlauf ueber die Materialien: die Auswertung liegt in
        der innersten Schleife der Zeitintegration.
        """
        active = self.active
        phi = np.where(active, rh, 0.5)
        theta = np.where(active, temperature, 20.0)
        keys = ("w", "dw_dphi", "delta_p", "lambda", "capacity_heat", "d_phi")
        props = {key: np.zeros(self.shape, dtype=float) for key in keys}
        liquid = self.options.liquid_transport
        suction = (self._suction_cells
                   if liquid and self.options.suction_at_rain else None)

        for material, mask in self._material_masks:
            phi_cells = phi[mask]
            theta_cells = theta[mask]
            w = material.w(phi_cells)
            dw_dphi = material.dw_dphi(phi_cells)
            props["w"][mask] = w
            props["dw_dphi"][mask] = dw_dphi
            props["delta_p"][mask] = material.delta_p(theta_cells, phi_cells)
            props["lambda"][mask] = material.lambda_moist(w)
            props["capacity_heat"][mask] = material.heat_capacity_moist(w)
            if liquid:
                d_w = material.dw_redistribution(w)
                if suction is not None:
                    wetted = suction[mask]
                    if wetted.any():
                        d_w = np.where(wetted, material.dw_suction(w), d_w)
                props["d_phi"][mask] = d_w * dw_dphi

        props["p_sat"] = np.where(active, physics.p_sat(theta), 0.0)
        for key in keys:
            props[key][~active] = 0.0
        return props

    # ------------------------------------------------------------------
    # Klimazustaende
    # ------------------------------------------------------------------
    def _group_states(self, t: float) -> List[Dict[str, float]]:
        states = []
        for group in self._groups:
            condition = group.condition
            if isinstance(condition, FixedBoundary):
                states.append({"temperature": condition.temperature, "rh": condition.rh,
                               "solar": 0.0, "rain": 0.0, "wind": 0.0,
                               "sky_temperature": None})
                continue
            state = condition.climate.state(t)
            states.append({
                "temperature": state.temperature,
                "rh": state.rh,
                "solar": state.solar,
                "rain": state.rain,
                "wind": state.wind,
                "sky_temperature": state.sky_temperature,
            })
        return states

    def _update_suction_cells(self, states: Sequence[Dict[str, float]]) -> None:
        self._suction_cells[:] = False
        if not self.options.suction_at_rain:
            return
        for group, state in zip(self._groups, states):
            condition = group.condition
            if not isinstance(condition, ExchangeBoundary):
                continue
            load = state["rain"] * condition.transfer.rain_absorption
            if load > 0.0:
                self._suction_cells[group.j, group.i] = True

    # ------------------------------------------------------------------
    # Assemblierung
    # ------------------------------------------------------------------
    def _assemble_moisture(self, props: Dict[str, np.ndarray], phi_iterate: np.ndarray,
                           w_old: np.ndarray, dt: Optional[float],
                           states: Sequence[Dict[str, float]],
                           temperature: np.ndarray):
        shape = self.shape
        aW = np.zeros(shape); aE = np.zeros(shape)
        aS = np.zeros(shape); aN = np.zeros(shape)
        aP = np.zeros(shape); b = np.zeros(shape)

        p_sat = props["p_sat"]
        if dt is not None:
            # Modifizierte Picard-Iteration nach Celia et al. (1990): der
            # Speicherterm wird um die tatsaechliche Wassergehaltsaenderung
            # korrigiert. Dadurch ist die Massenbilanz auch bei stark
            # nichtlinearer Sorptionsisotherme geschlossen -- die reine
            # Kapazitaetsform (dw/dphi * dphi) waere es nicht.
            capacity = self.volume * props["dw_dphi"] / dt
            aP += capacity
            b += (capacity * np.nan_to_num(phi_iterate)
                  - self.volume * (props["w"] - w_old) / dt)

        # innere Flaechen in x-Richtung
        if self.grid.nx > 1:
            g_liquid = self._area_x * _series_conductance(
                props["d_phi"][:, :-1], props["d_phi"][:, 1:],
                self._dx_half_left, self._dx_half_right) * self._link_x
            g_vapour = self._area_x * _series_conductance(
                props["delta_p"][:, :-1], props["delta_p"][:, 1:],
                self._dx_half_left, self._dx_half_right) * self._link_x
            aE[:, :-1] += g_liquid + g_vapour * p_sat[:, 1:]
            aP[:, :-1] += g_liquid + g_vapour * p_sat[:, :-1]
            aW[:, 1:] += g_liquid + g_vapour * p_sat[:, :-1]
            aP[:, 1:] += g_liquid + g_vapour * p_sat[:, 1:]
            self._g_vapour_x = g_vapour
        else:
            self._g_vapour_x = np.zeros((self.grid.ny, 0))

        # innere Flaechen in y-Richtung
        if self.grid.ny > 1:
            g_liquid = self._area_y * _series_conductance(
                props["d_phi"][:-1, :], props["d_phi"][1:, :],
                self._dy_half_low, self._dy_half_high) * self._link_y
            g_vapour = self._area_y * _series_conductance(
                props["delta_p"][:-1, :], props["delta_p"][1:, :],
                self._dy_half_low, self._dy_half_high) * self._link_y
            aN[:-1, :] += g_liquid + g_vapour * p_sat[1:, :]
            aP[:-1, :] += g_liquid + g_vapour * p_sat[:-1, :]
            aS[1:, :] += g_liquid + g_vapour * p_sat[:-1, :]
            aP[1:, :] += g_liquid + g_vapour * p_sat[1:, :]
            self._g_vapour_y = g_vapour
        else:
            self._g_vapour_y = np.zeros((0, self.grid.nx))

        # Randflaechen
        self._boundary_moisture = []
        for group, state in zip(self._groups, states):
            j, i = group.j, group.i
            condition = group.condition
            delta_cell = props["delta_p"][j, i]
            p_sat_cell = p_sat[j, i]
            if isinstance(condition, FixedBoundary):
                g_vapour = group.area * np.divide(
                    delta_cell, group.d_half, out=np.zeros_like(delta_cell),
                    where=delta_cell > 0.0)
                g_liquid = group.area * np.divide(
                    props["d_phi"][j, i], group.d_half,
                    out=np.zeros_like(delta_cell), where=props["d_phi"][j, i] > 0.0)
                p_v_air = state["rh"] * physics.p_sat(state["temperature"])
                np.add.at(aP, (j, i), g_liquid + g_vapour * p_sat_cell)
                np.add.at(b, (j, i), g_liquid * state["rh"] + g_vapour * p_v_air)
                self._boundary_moisture.append((group, g_vapour, p_v_air, 0.0))
                continue

            transfer = condition.transfer
            resistance = 1.0 / np.maximum(transfer.beta_value(state["wind"]), 1e-30)
            if transfer.sd > 0.0:
                resistance = resistance + transfer.sd / physics.delta_a(state["temperature"])
            resistance = resistance + np.divide(
                group.d_half, delta_cell, out=np.full_like(group.d_half, np.inf),
                where=delta_cell > 0.0)
            beta_total = np.divide(1.0, resistance, out=np.zeros_like(resistance),
                                   where=np.isfinite(resistance) & (resistance > 0.0))
            g_vapour = group.area * beta_total
            p_v_air = state["rh"] * physics.p_sat(state["temperature"])
            np.add.at(aP, (j, i), g_vapour * p_sat_cell)
            np.add.at(b, (j, i), g_vapour * p_v_air)

            rain = state["rain"] * transfer.rain_absorption
            if rain > 0.0:
                # Wasseraufnahme nur, solange die freie Wassersaettigung nicht
                # erreicht ist -- ueberschuessiges Wasser laeuft ab. Der
                # Uebergang wird ueber die letzten Prozent der Speicherfaehigkeit
                # geglaettet; eine harte Schwelle wuerde die Picard-Iteration
                # zwischen "aufnehmend" und "gesperrt" pendeln lassen.
                w_max = np.maximum(self.w_saturation[j, i], 1e-12)
                saturation = props["w"][j, i] / w_max
                open_for_water = np.clip((1.0 - saturation) / RAIN_RAMP, 0.0, 1.0)
                source = group.area * rain * open_for_water
                # Quellterm-Linearisierung (Patankar): die Abhaengigkeit von phi
                # wandert in die Hauptdiagonale. Das stabilisiert die Iteration
                # nahe der Saettigung erheblich, wo dw/dphi sehr gross wird.
                in_transition = (open_for_water > 0.0) & (open_for_water < 1.0)
                slope = np.where(in_transition,
                                 -source / (RAIN_RAMP * w_max)
                                 * props["dw_dphi"][j, i] / np.maximum(open_for_water, 1e-12),
                                 0.0)
                np.add.at(aP, (j, i), -slope)
                np.add.at(b, (j, i), source - slope * np.nan_to_num(phi_iterate[j, i]))
            self._boundary_moisture.append((group, g_vapour, p_v_air, rain))

        return aP, aW, aE, aS, aN, b

    def _assemble_heat(self, props: Dict[str, np.ndarray], temperature_old: np.ndarray,
                       dt: Optional[float], states: Sequence[Dict[str, float]],
                       phi_new: np.ndarray, temperature_iterate: np.ndarray):
        shape = self.shape
        aW = np.zeros(shape); aE = np.zeros(shape)
        aS = np.zeros(shape); aN = np.zeros(shape)
        aP = np.zeros(shape); b = np.zeros(shape)

        if dt is not None:
            capacity = self.volume * props["capacity_heat"] / dt
            aP += capacity
            b += capacity * np.nan_to_num(temperature_old)

        lam = props["lambda"]
        if self.grid.nx > 1:
            g = self._area_x * _series_conductance(
                lam[:, :-1], lam[:, 1:], self._dx_half_left, self._dx_half_right) * self._link_x
            aE[:, :-1] += g
            aW[:, 1:] += g
            aP[:, :-1] += g
            aP[:, 1:] += g
        if self.grid.ny > 1:
            g = self._area_y * _series_conductance(
                lam[:-1, :], lam[1:, :], self._dy_half_low, self._dy_half_high) * self._link_y
            aN[:-1, :] += g
            aS[1:, :] += g
            aP[:-1, :] += g
            aP[1:, :] += g

        # Randflaechen
        self._boundary_heat = []
        for group, state in zip(self._groups, states):
            j, i = group.j, group.i
            condition = group.condition
            lam_cell = np.maximum(lam[j, i], 1e-12)
            if isinstance(condition, FixedBoundary):
                g = group.area * lam_cell / group.d_half
                np.add.at(aP, (j, i), g)
                np.add.at(b, (j, i), g * state["temperature"])
                self._boundary_heat.append((group, g / group.area, state["temperature"]))
                continue

            transfer = condition.transfer
            alpha = np.asarray(transfer.alpha_value(state["wind"]), dtype=float)
            alpha = np.broadcast_to(alpha, group.area.shape)
            alpha_total = 1.0 / (1.0 / np.maximum(alpha, 1e-12) + group.d_half / lam_cell)

            # Sol-Air-Temperatur: kurzwellige Einstrahlung und langwelliger
            # Austausch wirken an der Oberflaeche, nicht im Zellmittelpunkt.
            radiation = transfer.solar_absorptance * state["solar"] * np.ones_like(group.area)
            sky = state.get("sky_temperature")
            if sky is not None and transfer.emissivity > 0.0:
                t_surface = group.surface_temperature
                radiation = radiation + transfer.emissivity * physics.STEFAN_BOLTZMANN * (
                    (sky + physics.KELVIN) ** 4 - (t_surface + physics.KELVIN) ** 4)
            t_air_effective = state["temperature"] + radiation / np.maximum(alpha, 1e-12)

            g = group.area * alpha_total
            np.add.at(aP, (j, i), g)
            np.add.at(b, (j, i), g * t_air_effective)
            self._boundary_heat.append((group, alpha_total, t_air_effective))

        # Latentwaerme aus dem Dampfstrom (Verdunstung/Kondensation)
        if self.options.latent_heat:
            b += physics.H_EVAPORATION * self._vapour_divergence(props, phi_new, states)

        return aP, aW, aE, aS, aN, b

    def _vapour_divergence(self, props: Dict[str, np.ndarray], phi: np.ndarray,
                           states: Sequence[Dict[str, float]]) -> np.ndarray:
        """Netto-Dampfeintrag je Zelle [kg/s] (positiv = Kondensation in der Zelle)."""
        p_v = np.where(self.active, phi * props["p_sat"], 0.0)
        net = np.zeros(self.shape)
        if self.grid.nx > 1:
            flux = self._g_vapour_x * (p_v[:, 1:] - p_v[:, :-1])
            net[:, :-1] += flux
            net[:, 1:] -= flux
        if self.grid.ny > 1:
            flux = self._g_vapour_y * (p_v[1:, :] - p_v[:-1, :])
            net[:-1, :] += flux
            net[1:, :] -= flux
        for group, g_vapour, p_v_air, _rain in self._boundary_moisture:
            j, i = group.j, group.i
            np.add.at(net, (j, i), g_vapour * (p_v_air - p_v[j, i]))
        return net

    # ------------------------------------------------------------------
    # Zeitschritt
    # ------------------------------------------------------------------
    def _step(self, t_new: float, dt: Optional[float],
              temperature_old: np.ndarray, phi_old: np.ndarray
              ) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray], List[Dict[str, float]], bool]:
        """Einen Zeitschritt (oder den stationaeren Fall) loesen."""
        options = self.options
        states = self._group_states(t_new)
        self._update_suction_cells(states)

        temperature = np.array(temperature_old, copy=True)
        phi = np.array(phi_old, copy=True)
        converged = False
        props: Dict[str, np.ndarray] = {}
        w_old = self._map(lambda m, p: m.w(p),
                          np.where(self.active, np.nan_to_num(phi_old), 0.5))

        clamped_mask = np.zeros(self.shape, dtype=bool)
        omega = options.relaxation
        previous_increment = None
        at_limit = np.zeros(self.shape, dtype=bool)
        for _iteration in range(options.max_iterations):
            props = self._properties(temperature, phi)

            aP, aW, aE, aS, aN, b = self._assemble_moisture(
                props, phi, w_old, dt, states, temperature)
            phi_star, _ = solve_five_point(aP, aW, aE, aS, aN, b, self.active,
                                           x0=np.nan_to_num(phi),
                                           use_scipy=options.use_scipy)
            # Zellen oberhalb der freien Wassersaettigung werden auf phi = 1
            # begrenzt (ueberschuessiges Wasser laeuft ab). Sie liegen damit auf
            # einer aktiven Nebenbedingung und werden aus dem Konvergenzmass
            # herausgenommen -- andernfalls koennte der Zeitschritt nie
            # konvergieren, solange eine Zelle gesaettigt ist.
            at_limit = np.zeros(self.shape, dtype=bool)
            at_limit[self.active] = phi_star[self.active] > 1.0
            clamped_mask |= at_limit
            phi_star = np.clip(phi_star, 1e-4, 1.0)

            aP, aW, aE, aS, aN, b = self._assemble_heat(
                props, temperature_old, dt, states, phi_star, temperature)
            temperature_star, _ = solve_five_point(aP, aW, aE, aS, aN, b, self.active,
                                                   x0=np.nan_to_num(temperature),
                                                   use_scipy=options.use_scipy)

            increment_phi = phi_star - phi
            increment_t = temperature_star - temperature

            # Konvergenzmass: der *ungedaempfte* Zuwachs. Damit taeuscht eine
            # starke Daempfung keine Konvergenz vor.
            free = self.active & ~at_limit
            delta_phi = (float(np.max(np.abs(increment_phi[free])))
                         if free.any() else 0.0)
            delta_t = float(np.max(np.abs(increment_t[self.active])))
            if delta_phi <= options.tol_rh and delta_t <= options.tol_temperature:
                phi, temperature = phi_star, temperature_star
                converged = True
                break

            # Automatische Daempfung: kehrt der Zuwachs die Richtung um, pendelt
            # die Iteration (typisch an Oberflaechen, wo Verdunstungskuehlung und
            # Dampfstrom sich gegenseitig aufschaukeln). Dann wird der
            # Relaxationsfaktor verkleinert, sonst wieder vergroessert.
            if previous_increment is not None:
                similarity = _cosine(increment_phi, previous_increment[0], self.active) \
                    + _cosine(increment_t, previous_increment[1], self.active)
                if similarity < 0.0:
                    omega = max(0.5 * omega, options.min_relaxation)
                else:
                    omega = min(1.2 * omega, options.relaxation)
            previous_increment = (increment_phi, increment_t)

            phi = np.clip(phi + omega * increment_phi, 1e-4, 1.0)
            temperature = temperature + omega * increment_t

        if clamped_mask.any():
            self._clamped_steps += 1
        props = self._properties(temperature, phi)
        self._update_surface_temperatures(props, temperature, states)
        temperature = np.where(self.active, temperature, np.nan)
        phi = np.where(self.active, phi, np.nan)
        return temperature, phi, props, states, converged

    def _update_surface_temperatures(self, props, temperature, states) -> None:
        """Oberflaechentemperaturen fuer den Strahlungsterm nachfuehren."""
        for (group, alpha_total, t_air_effective) in getattr(self, "_boundary_heat", []):
            j, i = group.j, group.i
            lam_cell = np.maximum(props["lambda"][j, i], 1e-12)
            q = alpha_total * (t_air_effective - temperature[j, i])
            group.surface_temperature = temperature[j, i] + q * group.d_half / lam_cell

    # ------------------------------------------------------------------
    # Oeffentliche Schnittstelle
    # ------------------------------------------------------------------
    def solve_steady_state(self, max_iterations: int = 200,
                           tolerance: float = 1e-6, t: float = 0.0
                           ) -> Tuple[np.ndarray, np.ndarray]:
        """Stationaeren Zustand berechnen (Speicherterme = 0).

        Nuetzlich fuer Waermebrueckenkennwerte (L2D, Psi, f_Rsi) und als
        Startzustand einer transienten Rechnung. Rueckgabe ``(T, phi)``.
        """
        if not self._groups:
            raise SolverError(
                "Stationaere Rechnung ohne wirksame Randbedingung ist nicht "
                "eindeutig loesbar -- mindestens eine Uebergangs- oder "
                "Festwert-Randbedingung zuweisen")
        original = self.options.max_iterations
        self.options.max_iterations = max_iterations
        try:
            temperature, phi, props, states, converged = self._step(
                t, None, self.temperature, self.rh)
        finally:
            self.options.max_iterations = original
        if not converged:
            raise SolverError(
                "Stationaere Loesung nicht konvergiert -- Gitter, Randbedingungen "
                "oder Materialkennwerte pruefen")
        self.temperature, self.rh = temperature, phi
        self._last_props = props
        self._last_states = states
        return temperature, phi

    def run(self, progress: Optional[Callable[[float, float], None]] = None) -> Results:
        """Transiente Berechnung durchfuehren."""
        options = self.options
        if options.duration <= 0:
            raise SolverError("duration muss > 0 sein")
        if options.dt <= 0:
            raise SolverError("dt muss > 0 sein")

        temperature = np.array(self.temperature, copy=True)
        phi = np.array(self.rh, copy=True)

        times: List[float] = []
        temperature_out: List[np.ndarray] = []
        rh_out: List[np.ndarray] = []
        water_out: List[np.ndarray] = []
        surface_records: Dict[str, Dict[str, List[float]]] = {
            group.condition.name: {"temperature": [], "rh": [], "heat_flux": [],
                                   "moisture_flux": [], "min_temperature": [],
                                   "max_rh": []}
            for group in self._groups
        }
        water_by_material: Dict[str, List[float]] = {
            name: [] for name in self.grid.material_names}

        props = self._properties(temperature, phi)
        states = self._group_states(0.0)
        self._assemble_moisture(props, phi, props["w"], options.dt, states, temperature)
        self._assemble_heat(props, temperature, options.dt, states, phi, temperature)
        self._record(0.0, temperature, phi, props, states, times, temperature_out,
                     rh_out, water_out, surface_records, water_by_material)

        t = 0.0
        dt = options.dt
        next_output = options.output_interval
        step_count = 0
        started = _time.time()
        while t < options.duration - 1e-9:
            dt = min(dt, options.duration - t, max(next_output - t, options.min_dt))
            try:
                new_temperature, new_phi, props, states, converged = self._step(
                    t + dt, dt, temperature, phi)
            except ConvergenceError as error:
                if not options.adaptive_timestep or dt <= options.min_dt:
                    raise SolverError(f"Zeitschritt bei t = {t / SECONDS_PER_HOUR:.2f} h "
                                      f"nicht loesbar: {error}") from error
                dt = max(dt / 2.0, options.min_dt)
                continue
            if not converged:
                if options.adaptive_timestep and dt > options.min_dt:
                    dt = max(dt / 2.0, options.min_dt)
                    continue
                if options.verbose:
                    print(f"  Warnung: Picard-Iteration bei t = "
                          f"{(t + dt) / SECONDS_PER_HOUR:.2f} h nicht konvergiert")

            temperature, phi = new_temperature, new_phi
            t += dt
            step_count += 1
            if t >= next_output - 1e-9 or t >= options.duration - 1e-9:
                self._record(t, temperature, phi, props, states, times, temperature_out,
                             rh_out, water_out, surface_records, water_by_material)
                while next_output <= t + 1e-9:
                    next_output += options.output_interval
                if options.verbose:
                    print(f"  t = {t / SECONDS_PER_DAY:7.2f} d  "
                          f"T {np.nanmin(temperature):6.2f}..{np.nanmax(temperature):6.2f} degC  "
                          f"rF {np.nanmin(phi) * 100:5.1f}..{np.nanmax(phi) * 100:5.1f} %")
            if converged and options.adaptive_timestep and dt < options.dt:
                dt = min(dt * 2.0, options.dt)
            if progress is not None:
                progress(t, options.duration)

        self.temperature, self.rh = temperature, phi
        surfaces = {
            name: SurfaceSeries(
                name=name,
                area=next(g.total_area for g in self._groups if g.condition.name == name),
                temperature=np.asarray(record["temperature"]),
                rh=np.asarray(record["rh"]),
                heat_flux=np.asarray(record["heat_flux"]),
                moisture_flux=np.asarray(record["moisture_flux"]),
                min_temperature=np.asarray(record["min_temperature"]),
                max_rh=np.asarray(record["max_rh"]),
            )
            for name, record in surface_records.items()
        }
        return Results(
            times=np.asarray(times, dtype=float),
            temperature=np.asarray(temperature_out),
            rh=np.asarray(rh_out),
            water_content=np.asarray(water_out),
            grid=self.grid,
            surfaces=surfaces,
            water_by_material={k: np.asarray(v) for k, v in water_by_material.items()},
            meta={
                "duration": options.duration,
                "dt": options.dt,
                "steps": step_count,
                "runtime_s": _time.time() - started,
                "clamped_steps": self._clamped_steps,
                "density_field": self.density,
                "materials": {name: self.materials.get(name).describe()
                              for name in self.grid.material_names},
                "boundaries": self.boundaries.describe(),
                "latent_heat": options.latent_heat,
                "liquid_transport": options.liquid_transport,
            },
        )

    # ------------------------------------------------------------------
    def _record(self, t, temperature, phi, props, states, times, temperature_out,
                rh_out, water_out, surface_records, water_by_material) -> None:
        times.append(float(t))
        temperature_out.append(np.where(self.active, temperature, np.nan))
        rh_out.append(np.where(self.active, phi, np.nan))
        water = np.where(self.active, props["w"], np.nan)
        water_out.append(water)

        volume = self.volume
        for mid, name in enumerate(self.grid.material_names):
            mask = self.grid.material_id == mid
            water_by_material[name].append(
                float(np.nansum(water[mask] * volume[mask])) if mask.any() else 0.0)

        heat_lookup = {id(group): (alpha, t_air)
                       for group, alpha, t_air in getattr(self, "_boundary_heat", [])}
        moisture_lookup = {id(group): (g_vapour, p_v_air, rain)
                           for group, g_vapour, p_v_air, rain
                           in getattr(self, "_boundary_moisture", [])}
        for group in self._groups:
            j, i = group.j, group.i
            record = surface_records[group.condition.name]
            lam_cell = np.maximum(props["lambda"][j, i], 1e-12)
            alpha_total, t_air_effective = heat_lookup.get(
                id(group), (np.zeros_like(group.area), np.zeros_like(group.area)))
            q = alpha_total * (t_air_effective - np.nan_to_num(temperature[j, i]))
            t_surface = np.nan_to_num(temperature[j, i]) + q * group.d_half / lam_cell

            g_vapour, p_v_air, rain = moisture_lookup.get(
                id(group), (np.zeros_like(group.area), 0.0, 0.0))
            p_v_cell = np.nan_to_num(phi[j, i]) * props["p_sat"][j, i]
            g_flux = g_vapour * (p_v_air - p_v_cell)
            delta_cell = np.maximum(props["delta_p"][j, i], 1e-30)
            p_v_surface = p_v_cell + g_flux / np.maximum(group.area, 1e-30) * group.d_half / delta_cell
            phi_surface = np.clip(p_v_surface / physics.p_sat(t_surface), 0.0, 1.0)

            weights = group.area / max(group.total_area, 1e-30)
            record["temperature"].append(float(np.sum(t_surface * weights)))
            record["rh"].append(float(np.sum(phi_surface * weights)))
            record["heat_flux"].append(float(np.sum(q * group.area)))
            record["moisture_flux"].append(
                float(np.sum(g_flux) + np.sum(group.area * rain)))
            record["min_temperature"].append(float(np.min(t_surface)))
            record["max_rh"].append(float(np.max(phi_surface)))

    # ------------------------------------------------------------------
    def describe(self) -> str:
        lines = [self.grid.summary(), "", self.assignment.summary(), "",
                 self.boundaries.describe(), "",
                 f"Zeitschritt {self.options.dt / SECONDS_PER_HOUR:.2f} h, Dauer "
                 f"{self.options.duration / SECONDS_PER_DAY:.1f} d"]
        return "\n".join(lines)
