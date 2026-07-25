"""Randbedingungen und ihre Zuordnung zu Gitter-Randflaechen.

Es gibt drei Typen:

``ExchangeBoundary``
    Uebergangsrandbedingung an eine Luftschicht (Aussen-/Innenklima) mit
    Waermeuebergangskoeffizient alpha, Wasserdampfuebergangskoeffizient beta,
    optionaler Oberflaechenbeschichtung (s_d-Wert), kurzwelliger Einstrahlung,
    langwelliger Abstrahlung und Schlagregenlast.

``FixedBoundary``
    Vorgegebene Oberflaechentemperatur und -feuchte (Dirichlet), z.B. fuer
    Normtestfaelle und Verifikationen.

``AdiabaticBoundary``
    Waerme- und dampfdichter Rand (Symmetrieebene, Schnittkante des
    Ausschnitts). Standard fuer alle nicht zugeordneten Flaechen.

Die Zuordnung erfolgt ueber "Selektoren", die eine Randflaeche geometrisch
identifizieren -- im Grasshopper-Adapter kommen die Selektoren aus
Rhino-Kurven, headless z.B. ueber die Seite (``links``, ``rechts`` ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import physics
from .climate import Climate, ConstantClimate
from .grid import Face

Point = Tuple[float, float]

_SIDE_ALIASES = {
    "links": "left", "left": "left", "west": "left",
    "rechts": "right", "right": "right", "ost": "right", "east": "right",
    "unten": "bottom", "bottom": "bottom", "sued": "bottom", "south": "bottom",
    "oben": "top", "top": "top", "nord": "top", "north": "top",
}


def normalise_side(side: str) -> str:
    key = str(side).strip().lower()
    if key not in _SIDE_ALIASES:
        raise ValueError(f"Unbekannte Seite '{side}'. Erlaubt: "
                         f"{sorted(set(_SIDE_ALIASES))}")
    return _SIDE_ALIASES[key]


# ---------------------------------------------------------------------------
# Uebergangskoeffizienten
# ---------------------------------------------------------------------------

@dataclass
class SurfaceTransfer:
    """Uebergangsparameter einer Bauteiloberflaeche.

    Attribute
    ---------
    alpha:
        Waermeuebergangskoeffizient [W/(m2 K)], einschliesslich des
        langwelligen Anteils, wenn ``emissivity`` nicht separat gerechnet
        wird. Richtwerte: innen 8 (R_si = 0.125 m2K/W), aussen 17
        (R_se = 0.0588 m2K/W).
    wind_factor:
        Windabhaengigkeit ``alpha = alpha + wind_factor * v`` [W s/(m3 K)].
        Mit ``alpha=4`` und ``wind_factor=4`` ergibt sich der in WUFI
        gebraeuchliche Ansatz fuer Aussenoberflaechen.
    beta:
        Wasserdampfuebergangskoeffizient [kg/(m2 s Pa)]. Ohne Angabe wird
        die Lewis-Beziehung ``beta = 7e-9 * alpha`` verwendet.
    sd:
        Aequivalente Luftschichtdicke einer Oberflaechenbeschichtung
        (Anstrich, Folie) [m]. Wirkt als zusaetzlicher Dampfwiderstand.
    solar_absorptance:
        Kurzwelliger Absorptionsgrad [-] fuer die Einstrahlung des Klimas.
    emissivity:
        Langwelliger Emissionsgrad [-]. Wird nur ausgewertet, wenn das Klima
        eine Himmelstemperatur liefert.
    rain_absorption:
        Anteil der Schlagregenlast, der als Fluessigwasser aufgenommen wird
        (Abspritzen/Abfliessen beruecksichtigt). 0 = kein Regeneintrag,
        typisch 0.7 fuer Fassaden.
    """

    alpha: float = 8.0
    wind_factor: float = 0.0
    beta: Optional[float] = None
    sd: float = 0.0
    solar_absorptance: float = 0.0
    emissivity: float = 0.9
    rain_absorption: float = 0.0

    def alpha_value(self, wind=0.0):
        return self.alpha + self.wind_factor * np.asarray(wind, dtype=float)

    def beta_value(self, wind=0.0):
        """Wasserdampfuebergangskoeffizient [kg/(m2 s Pa)]."""
        if self.beta is not None:
            return np.full(np.shape(wind), float(self.beta)) if np.ndim(wind) else float(self.beta)
        return physics.BETA_PER_ALPHA * self.alpha_value(wind)

    def vapour_resistance(self, theta=10.0, wind=0.0):
        """Gesamter Dampfuebergangswiderstand inkl. Beschichtung [(m2 s Pa)/kg]."""
        beta = self.beta_value(wind)
        resistance = 1.0 / np.maximum(beta, 1e-30)
        if self.sd > 0.0:
            resistance = resistance + self.sd / physics.delta_a(theta)
        return resistance


def interior_transfer(sd: float = 0.0, alpha: float = 8.0) -> SurfaceTransfer:
    """Innenoberflaeche: alpha = 8 W/m2K (R_si = 0.125 m2K/W)."""
    return SurfaceTransfer(alpha=alpha, sd=sd, solar_absorptance=0.0,
                           rain_absorption=0.0)


def exterior_transfer(sd: float = 0.0, alpha: float = 17.0,
                      wind_factor: float = 0.0,
                      solar_absorptance: float = 0.6,
                      rain_absorption: float = 0.7,
                      emissivity: float = 0.9) -> SurfaceTransfer:
    """Aussenoberflaeche: alpha = 17 W/m2K (R_se = 0.0588 m2K/W).

    Fuer windabhaengige Uebergaenge ``alpha=4`` und ``wind_factor=4`` setzen.
    """
    return SurfaceTransfer(alpha=alpha, wind_factor=wind_factor, sd=sd,
                           solar_absorptance=solar_absorptance,
                           emissivity=emissivity,
                           rain_absorption=rain_absorption)


# ---------------------------------------------------------------------------
# Randbedingungen
# ---------------------------------------------------------------------------

class BoundaryCondition:
    """Basisklasse."""

    kind = "adiabatic"

    def __init__(self, name: str = "") -> None:
        self.name = name or self.__class__.__name__

    def describe(self) -> str:
        return f"{self.name} ({self.kind})"


class AdiabaticBoundary(BoundaryCondition):
    """Waerme- und dampfdichter Rand (Symmetrie / Schnittkante)."""

    kind = "adiabatic"

    def __init__(self, name: str = "adiabat") -> None:
        super().__init__(name)


class ExchangeBoundary(BoundaryCondition):
    """Uebergangsrandbedingung zu einem Klima."""

    kind = "exchange"

    def __init__(self, climate: Climate, transfer: Optional[SurfaceTransfer] = None,
                 name: str = "Uebergang") -> None:
        super().__init__(name)
        self.climate = climate
        self.transfer = transfer or SurfaceTransfer()

    def describe(self) -> str:
        t = self.transfer
        text = (f"{self.name}: {self.climate.describe()}, alpha={t.alpha:g}")
        if t.wind_factor:
            text += f"+{t.wind_factor:g}*v"
        if t.sd:
            text += f", s_d={t.sd:g} m"
        if t.rain_absorption:
            text += f", Regenaufnahme {t.rain_absorption * 100:.0f} %"
        if t.solar_absorptance:
            text += f", a_s={t.solar_absorptance:g}"
        return text


class FixedBoundary(BoundaryCondition):
    """Vorgegebene Oberflaechentemperatur und -feuchte (Dirichlet)."""

    kind = "fixed"

    def __init__(self, temperature: float, rh: float, name: str = "fest") -> None:
        super().__init__(name)
        self.climate = ConstantClimate(temperature, rh)
        self.temperature = float(temperature)
        self.rh = float(rh)

    def describe(self) -> str:
        return f"{self.name}: fest {self.temperature:.1f} degC / {self.rh * 100:.0f} % rF"


def exterior_surface(climate: Climate, sd: float = 0.0, alpha: float = 17.0,
                     wind_factor: float = 0.0, solar_absorptance: float = 0.6,
                     rain_absorption: float = 0.7, emissivity: float = 0.9,
                     name: str = "aussen") -> ExchangeBoundary:
    """Aussenoberflaeche mit Standard-Uebergangswerten."""
    return ExchangeBoundary(climate, exterior_transfer(
        sd=sd, alpha=alpha, wind_factor=wind_factor,
        solar_absorptance=solar_absorptance, rain_absorption=rain_absorption,
        emissivity=emissivity), name=name)


def interior_surface(climate: Climate, sd: float = 0.0, alpha: float = 8.0,
                     name: str = "innen") -> ExchangeBoundary:
    """Innenoberflaeche mit Standard-Uebergangswerten."""
    return ExchangeBoundary(climate, interior_transfer(sd=sd, alpha=alpha), name=name)


# ---------------------------------------------------------------------------
# Selektoren
# ---------------------------------------------------------------------------

class Selector:
    """Basisklasse: waehlt Randflaechen aus."""

    def matches(self, face: Face) -> bool:
        raise NotImplementedError

    def describe(self) -> str:
        return self.__class__.__name__


class AllFaces(Selector):
    """Alle Randflaechen."""

    def matches(self, face: Face) -> bool:
        return True


class SideSelector(Selector):
    """Alle Flaechen einer Bauteilseite, optional auf einen Bereich begrenzt."""

    def __init__(self, side: str, x_range: Optional[Tuple[float, float]] = None,
                 y_range: Optional[Tuple[float, float]] = None) -> None:
        self.side = normalise_side(side)
        self.x_range = x_range
        self.y_range = y_range

    def matches(self, face: Face) -> bool:
        if face.side != self.side:
            return False
        if self.x_range and not (self.x_range[0] - 1e-9 <= face.x <= self.x_range[1] + 1e-9):
            return False
        if self.y_range and not (self.y_range[0] - 1e-9 <= face.y <= self.y_range[1] + 1e-9):
            return False
        return True

    def describe(self) -> str:
        return f"Seite '{self.side}'"


class BoxSelector(Selector):
    """Alle Flaechen, deren Mittelpunkt in einem Rechteck liegt."""

    def __init__(self, x_min: float, y_min: float, x_max: float, y_max: float,
                 sides: Optional[Sequence[str]] = None) -> None:
        self.x_min, self.y_min = float(x_min), float(y_min)
        self.x_max, self.y_max = float(x_max), float(y_max)
        self.sides = None if sides is None else {normalise_side(s) for s in sides}

    def matches(self, face: Face) -> bool:
        if self.sides is not None and face.side not in self.sides:
            return False
        return (self.x_min - 1e-9 <= face.x <= self.x_max + 1e-9
                and self.y_min - 1e-9 <= face.y <= self.y_max + 1e-9)

    def describe(self) -> str:
        return (f"Bereich x {self.x_min:.3f}..{self.x_max:.3f}, "
                f"y {self.y_min:.3f}..{self.y_max:.3f}")


class PolylineSelector(Selector):
    """Alle Flaechen, deren Mittelpunkt nahe an einem Polygonzug liegt.

    Das ist der Anschluss an Rhino/Grasshopper: der Anwender zeichnet die
    Aussen- bzw. Innenoberflaeche als Kurve, der Adapter wandelt sie in einen
    Polygonzug um. ``tolerance`` ist der maximale Abstand [m].
    """

    def __init__(self, points: Sequence[Point], tolerance: float = 0.005,
                 sides: Optional[Sequence[str]] = None) -> None:
        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) < 2:
            raise ValueError("PolylineSelector braucht mindestens zwei (x, y)-Punkte")
        self.points = pts
        self.tolerance = float(tolerance)
        self.sides = None if sides is None else {normalise_side(s) for s in sides}

    def distance(self, x: float, y: float) -> float:
        a = self.points[:-1]
        b = self.points[1:]
        ab = b - a
        length_sq = np.sum(ab * ab, axis=1)
        length_sq = np.where(length_sq > 0.0, length_sq, 1.0)
        ap = np.array([x, y]) - a
        t = np.clip(np.sum(ap * ab, axis=1) / length_sq, 0.0, 1.0)
        closest = a + t[:, None] * ab
        return float(np.min(np.hypot(*(np.array([x, y]) - closest).T)))

    def matches(self, face: Face) -> bool:
        if self.sides is not None and face.side not in self.sides:
            return False
        return self.distance(face.x, face.y) <= self.tolerance

    def describe(self) -> str:
        return f"Kurve mit {len(self.points)} Punkten (Toleranz {self.tolerance * 1000:.1f} mm)"


class PredicateSelector(Selector):
    """Selektor aus einer beliebigen Funktion ``face -> bool``."""

    def __init__(self, predicate: Callable[[Face], bool], label: str = "Praedikat") -> None:
        self.predicate = predicate
        self.label = label

    def matches(self, face: Face) -> bool:
        return bool(self.predicate(face))

    def describe(self) -> str:
        return self.label


def make_selector(spec) -> Selector:
    """Selektor aus einer kompakten Angabe erzeugen.

    Erlaubt sind: ein ``Selector``, ein Seitenname (``"links"``, ``"top"`` ...),
    eine Punktliste (-> :class:`PolylineSelector`), ein Dictionary mit den
    Schluesseln ``side``/``polyline``/``box``, oder ``"alle"``.
    """
    if isinstance(spec, Selector):
        return spec
    if isinstance(spec, str):
        if spec.strip().lower() in ("alle", "all", "*"):
            return AllFaces()
        return SideSelector(spec)
    if isinstance(spec, dict):
        if "side" in spec:
            return SideSelector(spec["side"], spec.get("x_range"), spec.get("y_range"))
        if "polyline" in spec:
            return PolylineSelector(spec["polyline"], spec.get("tolerance", 0.005),
                                    spec.get("sides"))
        if "box" in spec:
            return BoxSelector(*spec["box"], sides=spec.get("sides"))
        raise ValueError(f"Selektor-Definition nicht erkannt: {spec}")
    if isinstance(spec, (list, tuple)):
        return PolylineSelector(spec)
    raise TypeError(f"Selektor-Definition nicht erkannt: {spec!r}")


# ---------------------------------------------------------------------------
# Zuordnung
# ---------------------------------------------------------------------------

@dataclass
class BoundaryAssignment:
    """Ergebnis der Zuordnung: Randbedingung je Randflaeche."""

    faces: List[Face]
    conditions: List[BoundaryCondition]
    groups: Dict[str, List[int]] = field(default_factory=dict)

    def unassigned_length(self, default_name: str = "adiabat") -> float:
        return sum(f.length for f, c in zip(self.faces, self.conditions)
                   if c.name == default_name)

    def summary(self) -> str:
        lines = [f"Randflaechen: {len(self.faces)}"]
        for name, indices in self.groups.items():
            length = sum(self.faces[k].length for k in indices)
            lines.append(f"  {name}: {len(indices)} Flaechen, {length:.3f} m")
        return "\n".join(lines)


class BoundarySet:
    """Regelwerk aus (Selektor, Randbedingung).

    Die Regeln werden in der angegebenen Reihenfolge ausgewertet; spaetere
    Regeln ueberschreiben frueher zugeordnete Flaechen. Nicht zugeordnete
    Flaechen erhalten die Standard-Randbedingung (adiabat).
    """

    def __init__(self, default: Optional[BoundaryCondition] = None) -> None:
        self.rules: List[Tuple[Selector, BoundaryCondition]] = []
        self.default = default or AdiabaticBoundary()

    def add(self, selector, condition: BoundaryCondition) -> "BoundarySet":
        self.rules.append((make_selector(selector), condition))
        return self

    def __len__(self) -> int:
        return len(self.rules)

    def conditions(self) -> List[BoundaryCondition]:
        seen: List[BoundaryCondition] = [self.default]
        for _, condition in self.rules:
            if condition not in seen:
                seen.append(condition)
        return seen

    def assign(self, faces: Sequence[Face]) -> BoundaryAssignment:
        assigned: List[BoundaryCondition] = [self.default] * len(faces)
        for selector, condition in self.rules:
            for k, face in enumerate(faces):
                if selector.matches(face):
                    assigned[k] = condition
        groups: Dict[str, List[int]] = {}
        for k, condition in enumerate(assigned):
            groups.setdefault(condition.name, []).append(k)
        return BoundaryAssignment(faces=list(faces), conditions=assigned, groups=groups)

    def describe(self) -> str:
        lines = [f"Standard: {self.default.describe()}"]
        for selector, condition in self.rules:
            lines.append(f"  {selector.describe()} -> {condition.describe()}")
        return "\n".join(lines)
