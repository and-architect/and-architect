"""Bauphysikalische Auswertung der Rechenergebnisse.

Enthalten sind die in der Praxis ueblichen Bewertungsgroessen:

* Waermebrueckenkennwerte: thermischer Leitwert L2D, Psi-Wert,
  Temperaturfaktor f_Rsi (Anlehnung an EN ISO 10211 / EN ISO 13788)
* Feuchtebilanz: Wassergehaltsverlauf, Trocknungstrend, Beurteilung nach dem
  Prinzip von WTA 6-2 (keine fortschreitende Akkumulation)
* Schimmelrisiko: Stundensummen oberhalb einer kritischen Feuchtekurve
  (Isoplethen-Naeherung)
* Holzschutz: maximaler massebezogener Feuchtegehalt (Grenzwert 20 M.-%)

Die Grenzwerte sind Naeherungen und als Parameter zugaenglich; fuer Nachweise
sind die jeweils gueltigen Normen bzw. Richtlinien heranzuziehen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .results import Results

SECONDS_PER_HOUR = 3600.0
SECONDS_PER_DAY = 86400.0
SECONDS_PER_YEAR = 365.0 * SECONDS_PER_DAY


# ---------------------------------------------------------------------------
# Waermebrueckenkennwerte
# ---------------------------------------------------------------------------

def thermal_coupling_coefficient(results: Results, surface: str,
                                 delta_temperature: float) -> float:
    """Thermischer Leitwert L2D [W/(m K)] aus einem stationaeren Ergebnis.

    ``surface`` ist der Name der Randbedingung, ueber die der Waermestrom
    bilanziert wird (ueblicherweise die Innenoberflaeche), ``delta_temperature``
    die Temperaturdifferenz zwischen Innen- und Aussenluft [K].

    Voraussetzung: stationaerer Zustand (z.B. ``solve_steady_state`` oder
    ausreichend lange transiente Rechnung mit konstantem Klima) und
    Bauteiltiefe 1 m.
    """
    if surface not in results.surfaces:
        raise KeyError(f"Randbedingung '{surface}' nicht in den Ergebnissen "
                       f"(vorhanden: {sorted(results.surfaces)})")
    if abs(delta_temperature) < 1e-9:
        raise ValueError("delta_temperature darf nicht 0 sein")
    flux = float(results.surfaces[surface].heat_flux[-1])
    return abs(flux / delta_temperature) / results.grid.depth


def psi_value(l2d: float, layers: Sequence[Tuple[float, float]]) -> float:
    """Psi-Wert [W/(m K)] aus L2D und den ungestoerten Bauteilanteilen.

    ``layers`` ist eine Liste ``[(U-Wert [W/(m2 K)], Laenge [m]), ...]`` der
    an das Modell angrenzenden ungestoerten Bauteile::

        Psi = L2D - sum(U_i * l_i)
    """
    return float(l2d - sum(u * length for u, length in layers))


def temperature_factor(results: Results, surface: str,
                       interior_temperature: float,
                       exterior_temperature: float) -> float:
    """Temperaturfaktor f_Rsi [-] aus der minimalen Oberflaechentemperatur.

    ``f_Rsi = (T_si,min - T_e) / (T_i - T_e)``. Der in Deutschland ueblich
    geforderte Mindestwert liegt bei 0.7 (entspricht 12.6 degC bei 20/-5 degC).
    """
    span = interior_temperature - exterior_temperature
    if abs(span) < 1e-9:
        raise ValueError("Innen- und Aussentemperatur sind identisch")
    t_min = float(np.min(results.surfaces[surface].min_temperature))
    return (t_min - exterior_temperature) / span


# ---------------------------------------------------------------------------
# Feuchtebilanz
# ---------------------------------------------------------------------------

@dataclass
class MoistureBalance:
    """Bewertung des Wassergehaltsverlaufs."""

    water_start: float
    water_end: float
    water_max: float
    trend_per_year: float
    accumulating: bool

    def summary(self) -> str:
        verdict = ("Feuchteakkumulation -- Aufbau kritisch pruefen"
                   if self.accumulating else "keine fortschreitende Akkumulation")
        return (f"Wassergehalt {self.water_start:.3f} -> {self.water_end:.3f} kg "
                f"(max {self.water_max:.3f} kg), Trend "
                f"{self.trend_per_year:+.3f} kg/a: {verdict}")


def moisture_balance(results: Results, tolerance_per_year: float = 0.0,
                     material: Optional[str] = None,
                     from_time: Optional[float] = None) -> MoistureBalance:
    """Wassergehaltsbilanz und Trocknungstrend.

    Der Trend ist die Steigung einer linearen Regression des Gesamt-
    wassergehalts ueber die Zeit, umgerechnet auf ein Jahr. Ein positiver
    Trend ueber ``tolerance_per_year`` gilt als Akkumulation.

    Wird ``material`` angegeben, bezieht sich die Auswertung nur auf dieses
    Material (z.B. die Holzkonstruktion oder die Daemmschicht).

    ``from_time`` [s] blendet den Anfang der Rechnung aus. Das ist fuer die
    Beurteilung wichtig: das erste Jahr ist von den Anfangsbedingungen
    (Baufeuchte, Startfeuchte) gepraegt. Beurteilt wird das *eingeschwungene*
    Verhalten -- siehe :func:`annual_balance`.
    """
    if material is not None:
        if material not in results.water_by_material:
            raise KeyError(f"Material '{material}' nicht in den Ergebnissen "
                           f"(vorhanden: {sorted(results.water_by_material)})")
        water = np.asarray(results.water_by_material[material], dtype=float)
    else:
        water = results.total_water
    times = results.times
    if from_time is not None:
        selection = times >= float(from_time)
        if selection.sum() >= 2:
            times = times[selection]
            water = water[selection]
    if len(times) > 2:
        slope = float(np.polyfit(times, water, 1)[0]) * SECONDS_PER_YEAR
    else:
        span = max(times[-1] - times[0], 1e-9)
        slope = float((water[-1] - water[0]) / span * SECONDS_PER_YEAR)
    return MoistureBalance(
        water_start=float(water[0]),
        water_end=float(water[-1]),
        water_max=float(np.max(water)),
        trend_per_year=slope,
        accumulating=slope > tolerance_per_year,
    )


def annual_balance(results: Results, material: Optional[str] = None
                   ) -> MoistureBalance:
    """Feuchtebilanz des *letzten* Simulationsjahres.

    Nach dem Prinzip von WTA 6-2 / EN 15026 wird ein Aufbau als unkritisch
    angesehen, wenn sich der Wassergehalt nach einigen Jahren auf einen
    jahreszyklischen Verlauf einstellt und nicht weiter ansteigt. Bewertet wird
    daher das letzte Jahr; bei Rechnungen unter zwei Jahren wird der gesamte
    Zeitraum ausgewertet (dann ist die Aussage vom Startzustand gepraegt).
    """
    duration = float(results.times[-1])
    from_time = duration - SECONDS_PER_YEAR if duration > 2.0 * SECONDS_PER_YEAR else None
    return moisture_balance(results, material=material, from_time=from_time)


def yearly_water_content(results: Results, material: Optional[str] = None
                         ) -> List[Tuple[float, float]]:
    """Wassergehalt zu jedem Jahreswechsel als ``[(Jahr, kg), ...]``."""
    water = (np.asarray(results.water_by_material[material], dtype=float)
             if material else results.total_water)
    years = int(results.times[-1] // SECONDS_PER_YEAR)
    values = [(0.0, float(water[0]))]
    for year in range(1, years + 1):
        index = results.index_at(year * SECONDS_PER_YEAR)
        values.append((float(year), float(water[index])))
    return values


# ---------------------------------------------------------------------------
# Schimmelrisiko
# ---------------------------------------------------------------------------

# Naeherung der niedrigsten Isoplethe fuer Schimmelwachstum (Substratgruppe mit
# guten Naehrstoffbedingungen). Stuetzstellen (Temperatur [degC], kritische
# rel. Feuchte [-]). Unterhalb von 0 degC wird kein Wachstum angesetzt.
DEFAULT_CRITICAL_RH = (
    (0.0, 0.98),
    (5.0, 0.93),
    (10.0, 0.88),
    (15.0, 0.83),
    (20.0, 0.80),
    (25.0, 0.78),
    (30.0, 0.77),
    (40.0, 0.77),
)


def critical_rh(temperature, curve: Sequence[Tuple[float, float]] = DEFAULT_CRITICAL_RH):
    """Kritische relative Feuchte [-] fuer Schimmelwachstum bei ``temperature``.

    Naeherung der untersten Isoplethe (LIM); unterhalb 0 degC wird 1.0
    geliefert (kein Wachstum). Die Kurve ist ersetzbar -- maßgeblich sind die
    Isoplethen nach Sedlbauer bzw. WTA 6-3.
    """
    temperature = np.asarray(temperature, dtype=float)
    points = np.asarray(curve, dtype=float)
    values = np.interp(temperature, points[:, 0], points[:, 1])
    return np.where(temperature < points[0, 0], 1.0, values)


@dataclass
class MouldRisk:
    """Ergebnis der Isoplethen-Auswertung."""

    location: str
    hours_critical: float
    fraction_critical: float
    max_rh: float
    max_exceedance: float

    def summary(self) -> str:
        return (f"{self.location}: {self.hours_critical:.0f} h ueber der kritischen "
                f"Feuchte ({self.fraction_critical * 100:.1f} % der Zeit), "
                f"max rF {self.max_rh * 100:.1f} %, "
                f"max Ueberschreitung {self.max_exceedance * 100:.1f} Prozentpunkte")


def mould_risk_series(times: Sequence[float], temperature: Sequence[float],
                      rh: Sequence[float], location: str = "Oberflaeche",
                      curve: Sequence[Tuple[float, float]] = DEFAULT_CRITICAL_RH
                      ) -> MouldRisk:
    """Schimmelrisiko einer Zeitreihe (Isoplethen-Vergleich)."""
    times = np.asarray(times, dtype=float)
    temperature = np.asarray(temperature, dtype=float)
    rh = np.asarray(rh, dtype=float)
    limit = critical_rh(temperature, curve)
    exceeds = rh > limit
    if len(times) > 1:
        weights = np.gradient(times)
    else:
        weights = np.zeros(1)
    hours = float(np.sum(weights[exceeds]) / SECONDS_PER_HOUR)
    total_hours = float(np.sum(weights) / SECONDS_PER_HOUR) or 1.0
    return MouldRisk(
        location=location,
        hours_critical=hours,
        fraction_critical=hours / total_hours,
        max_rh=float(np.max(rh)),
        max_exceedance=float(np.max(rh - limit)),
    )


def mould_risk_at_surface(results: Results, surface: str,
                          curve: Sequence[Tuple[float, float]] = DEFAULT_CRITICAL_RH
                          ) -> MouldRisk:
    """Schimmelrisiko an einer Bauteiloberflaeche (Randbedingungsgruppe).

    Bewertet werden die *ungunstigsten* Werte der Gruppe: die minimale
    Oberflaechentemperatur und die maximale Oberflaechenfeuchte -- also z.B.
    die Ecke einer Waermebruecke.
    """
    series = results.surfaces[surface]
    return mould_risk_series(results.times, series.min_temperature, series.max_rh,
                             location=f"Oberflaeche '{surface}'", curve=curve)


def mould_risk_at_point(results: Results, x: float, y: float,
                        curve: Sequence[Tuple[float, float]] = DEFAULT_CRITICAL_RH
                        ) -> MouldRisk:
    """Schimmelrisiko in einer Zelle (z.B. Grenzflaeche Innendaemmung/Mauerwerk)."""
    series = results.cell_series(x, y)
    return mould_risk_series(series["times"], series["temperature"], series["rh"],
                             location=f"Punkt ({x:.3f}, {y:.3f})", curve=curve)


# ---------------------------------------------------------------------------
# Holzschutz und Kondensat
# ---------------------------------------------------------------------------

@dataclass
class WoodMoistureCheck:
    """Auswertung des Holzfeuchtegehalts."""

    material: str
    max_mass_percent: float
    hours_above_limit: float
    limit: float

    def summary(self) -> str:
        verdict = "eingehalten" if self.max_mass_percent <= self.limit else "UEBERSCHRITTEN"
        return (f"{self.material}: max {self.max_mass_percent:.1f} M.-% "
                f"(Grenzwert {self.limit:.0f} M.-%, {verdict}), "
                f"{self.hours_above_limit:.0f} h darueber")


def wood_moisture_check(results: Results, material: str, limit: float = 20.0
                        ) -> WoodMoistureCheck:
    """Massebezogener Feuchtegehalt eines Materials gegen einen Grenzwert.

    Grenzwert 20 M.-% entsprechend DIN 68800-2 fuer Holzbauteile.
    """
    if material not in results.grid.material_names:
        raise KeyError(f"Material '{material}' nicht im Modell "
                       f"(vorhanden: {results.grid.material_names})")
    mask = results.grid.material_id == results.grid.material_names.index(material)
    rho = np.asarray(results.meta.get("density_field"), dtype=float)
    if rho.shape != results.grid.shape:
        raise KeyError("Dichtefeld nicht in den Ergebnissen gespeichert")
    density = float(np.max(rho[mask]))
    series = np.array([100.0 * np.nanmax(w[mask]) / density for w in results.water_content])
    weights = np.gradient(results.times) if len(results.times) > 1 else np.zeros(1)
    return WoodMoistureCheck(
        material=material,
        max_mass_percent=float(np.max(series)),
        hours_above_limit=float(np.sum(weights[series > limit]) / SECONDS_PER_HOUR),
        limit=float(limit),
    )


def worst_cell(results: Results, material: Optional[str] = None,
               quantity: str = "rh") -> Dict[str, float]:
    """Ort und Zeitpunkt des hoechsten Werts einer Groesse.

    Damit findet man die kritische Stelle eines 2D-Details, ohne sie vorher zu
    kennen -- z.B. die feuchteste Zelle des Holzbalkens oder die Ecke mit der
    hoechsten Oberflaechenfeuchte. Mit ``material`` wird die Suche auf ein
    Material eingegrenzt.

    Rueckgabe: ``{"x", "y", "wert", "zeit_d", "temperatur", "rh"}``.
    """
    mask = results.grid.active
    if material is not None:
        if material not in results.grid.material_names:
            raise KeyError(f"Material '{material}' nicht im Modell "
                           f"(vorhanden: {results.grid.material_names})")
        mask = mask & (results.grid.material_id
                       == results.grid.material_names.index(material))
    if not mask.any():
        raise KeyError("Kein Bereich zur Auswertung gefunden")

    fields = np.stack([results.field(quantity, step=k) for k in range(results.n_steps)])
    masked = np.where(mask[None, :, :], fields, -np.inf)
    step, j, i = np.unravel_index(int(np.nanargmax(masked)), masked.shape)
    return {
        "x": float(results.grid.xc[i]),
        "y": float(results.grid.yc[j]),
        "wert": float(fields[step, j, i]),
        "zeit_d": float(results.times[step] / SECONDS_PER_DAY),
        "temperatur": float(results.temperature[step, j, i]),
        "rh": float(results.rh[step, j, i]),
    }


def saturation_cells(results: Results, threshold: float = 0.995) -> Dict[str, float]:
    """Auswertung der Zellen, die die freie Wassersaettigung erreichen.

    Rueckgabe: Anteil der Zellen und Stunden mit ``phi >= threshold``
    (Hinweis auf Kondensat bzw. kapillare Saettigung).
    """
    mask = results.grid.active
    reached = np.array([np.nansum(field[mask] >= threshold) for field in results.rh])
    weights = np.gradient(results.times) if len(results.times) > 1 else np.zeros(1)
    n_active = max(results.grid.n_active, 1)
    return {
        "max_cells": float(reached.max()),
        "max_fraction": float(reached.max() / n_active),
        "hours_with_saturation": float(np.sum(weights[reached > 0]) / SECONDS_PER_HOUR),
    }


# ---------------------------------------------------------------------------
# Gesamtbericht
# ---------------------------------------------------------------------------

def report(results: Results, surfaces: Optional[Sequence[str]] = None,
           wood_materials: Optional[Sequence[str]] = None) -> str:
    """Kompakter Auswertungsbericht als Text."""
    lines = [results.summary(), "", "Bewertung:"]
    lines.append("  gesamter Zeitraum: " + moisture_balance(results).summary())
    if float(results.times[-1]) > 2.0 * SECONDS_PER_YEAR:
        lines.append("  letztes Jahr:      " + annual_balance(results).summary())
    for name in (surfaces if surfaces is not None else results.surfaces):
        if name in results.surfaces:
            lines.append("  " + mould_risk_at_surface(results, name).summary())
    for name in (wood_materials or []):
        if name in results.grid.material_names:
            lines.append("  " + wood_moisture_check(results, name).summary())
    saturation = saturation_cells(results)
    if saturation["max_cells"] > 0:
        lines.append(f"  Saettigung: bis {saturation['max_cells']:.0f} Zellen "
                     f"({saturation['max_fraction'] * 100:.1f} %), "
                     f"{saturation['hours_with_saturation']:.0f} h")
    else:
        lines.append("  Saettigung: keine Zelle erreicht die freie Wassersaettigung")
    return "\n".join(lines)
