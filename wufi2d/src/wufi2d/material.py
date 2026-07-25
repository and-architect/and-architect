"""Materialmodell nach Kuenzel / WUFI-Prinzip.

Ein Material wird ueber wenige, praxisnahe Kennwerte beschrieben
(Kuenzel 1995, "calculation using simple parameters"):

* Trockenkennwerte: Dichte, Waermekapazitaet, Waermeleitfaehigkeit,
  Dampfdiffusionswiderstandszahl mu
* Feuchtespeicherung: freie Wassersaettigung w_f und Wassergehalt w_80
  bei 80 % rel. Feuchte -- daraus wird die Sorptionsisotherme als
  Approximation gebildet. Alternativ kann eine tabellierte Isotherme
  hinterlegt werden.
* Fluessigtransport: Wasseraufnahmekoeffizient A_w, daraus wird der
  Fluessigtransportkoeffizient D_w approximiert. Alternativ Tabelle.
* Feuchtezuschlag der Waermeleitfaehigkeit b [%/M.-%]

WICHTIGER HINWEIS ZU DEN KENNWERTEN
-----------------------------------
Die mitgelieferte Datenbank (``materials_db.json``) enthaelt *Richtwerte aus
der Literatur*, keine geprueften Messdaten und keine Daten aus der
(lizenzpflichtigen) WUFI-/IBP-Materialdatenbank. Fuer Nachweise sind
gemessene Kennwerte des jeweiligen Produkts einzusetzen.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import physics

_DB_FILE = Path(__file__).with_name("materials_db.json")


class MaterialError(ValueError):
    """Fehlerhafte oder inkonsistente Materialdefinition."""


@dataclass
class Material:
    """Hygrothermische Materialdefinition.

    Attribute
    ---------
    name:
        Bezeichnung.
    rho:
        Rohdichte des trockenen Materials [kg/m3].
    cp:
        Spezifische Waermekapazitaet trocken [J/(kg K)].
    lambda_dry:
        Waermeleitfaehigkeit trocken [W/(m K)].
    mu:
        Wasserdampfdiffusionswiderstandszahl (trocken) [-].
    w_f:
        Freie Wassersaettigung [kg/m3].
    w_80:
        Wassergehalt bei 80 % rel. Feuchte [kg/m3]. Muss kleiner als
        ``0.8 * w_f`` sein, damit die Approximation der Isotherme monoton ist.
    a_w:
        Wasseraufnahmekoeffizient [kg/(m2 s^0.5)]. 0 = kein Kapillartransport.
    lambda_moisture_supplement:
        Feuchtebedingter Zuschlag der Waermeleitfaehigkeit b [%/M.-%]::

            lambda(w) = lambda_dry * (1 + b/100 * u)   mit u = 100 * w/rho [M.-%]

    redistribution_factor:
        Verhaeltnis D_ww / D_ws (Weiterverteilung zu Saugen). Kuenzel gibt
        etwa eine Zehnerpotenz Unterschied an -> Standardwert 0.1.
    sorption_table:
        Optionale tabellierte Isotherme als Liste von ``[phi, w]``.
    dw_table:
        Optionale Tabelle des Fluessigtransportkoeffizienten (Saugen) als
        Liste von ``[w, D_ws]`` mit D_ws in [m2/s].
    mu_table:
        Optionale feuchteabhaengige mu-Werte als Liste von ``[phi, mu]``.
    porosity:
        Offene Porositaet [m3/m3], optional (nur informativ / Clamping).
    category, note:
        Freitext.
    """

    name: str
    rho: float
    cp: float
    lambda_dry: float
    mu: float
    w_f: float
    w_80: float
    a_w: float = 0.0
    lambda_moisture_supplement: float = 0.0
    redistribution_factor: float = 0.1
    sorption_table: Optional[List[List[float]]] = None
    dw_table: Optional[List[List[float]]] = None
    mu_table: Optional[List[List[float]]] = None
    porosity: Optional[float] = None
    category: str = ""
    note: str = ""

    # -- interne, aus den Kennwerten abgeleitete Groessen -------------------
    _b_iso: float = field(init=False, repr=False, default=0.0)
    _phi_tab: Optional[np.ndarray] = field(init=False, repr=False, default=None)
    _w_tab: Optional[np.ndarray] = field(init=False, repr=False, default=None)

    def __post_init__(self) -> None:
        self.validate()
        if self.sorption_table:
            table = np.asarray(sorted(self.sorption_table, key=lambda p: p[0]), dtype=float)
            self._phi_tab = table[:, 0]
            self._w_tab = table[:, 1]
        else:
            # Approximation der Sorptionsisotherme nach Kuenzel (1995):
            #     w(phi) = w_f * (b - 1) * phi / (b - phi)
            # b folgt aus der Bedingung w(0.8) = w_80.
            self._b_iso = 0.8 * (self.w_80 - self.w_f) / (self.w_80 - 0.8 * self.w_f)

    # ------------------------------------------------------------------
    # Validierung / Serialisierung
    # ------------------------------------------------------------------
    def validate(self) -> None:
        if self.rho <= 0:
            raise MaterialError(f"{self.name}: Dichte muss > 0 sein")
        if self.cp <= 0:
            raise MaterialError(f"{self.name}: Waermekapazitaet muss > 0 sein")
        if self.lambda_dry <= 0:
            raise MaterialError(f"{self.name}: Waermeleitfaehigkeit muss > 0 sein")
        if self.mu <= 0:
            raise MaterialError(f"{self.name}: mu muss > 0 sein")
        if self.sorption_table:
            table = sorted(self.sorption_table, key=lambda p: p[0])
            phis = [p[0] for p in table]
            ws = [p[1] for p in table]
            if phis[0] > 1e-9:
                raise MaterialError(f"{self.name}: Isotherme muss bei phi = 0 beginnen")
            if not math.isclose(phis[-1], 1.0, abs_tol=1e-6):
                raise MaterialError(f"{self.name}: Isotherme muss bei phi = 1 enden")
            if any(b <= a for a, b in zip(ws, ws[1:])):
                raise MaterialError(f"{self.name}: Isotherme muss streng monoton steigen")
            return
        if self.w_f <= 0:
            raise MaterialError(f"{self.name}: w_f muss > 0 sein (oder Isothermen-Tabelle angeben)")
        if not 0 < self.w_80 < 0.8 * self.w_f:
            raise MaterialError(
                f"{self.name}: w_80 = {self.w_80} muss zwischen 0 und 0.8*w_f = "
                f"{0.8 * self.w_f:.3f} liegen, sonst ist die Approximation der "
                "Sorptionsisotherme nicht monoton"
            )

    def to_dict(self) -> Dict:
        data = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        return {k: v for k, v in data.items() if v is not None and v != ""}

    @classmethod
    def from_dict(cls, data: Dict) -> "Material":
        known = {f for f in cls.__dataclass_fields__ if not f.startswith("_")}
        unknown = set(data) - known
        if unknown:
            raise MaterialError(f"Unbekannte Materialfelder: {sorted(unknown)}")
        return cls(**data)

    # ------------------------------------------------------------------
    # Feuchtespeicherung
    # ------------------------------------------------------------------
    @property
    def w_sat(self) -> float:
        """Wassergehalt bei phi = 1 [kg/m3]."""
        if self._w_tab is not None:
            return float(self._w_tab[-1])
        return float(self.w_f)

    def w(self, phi):
        """Wassergehalt [kg/m3] als Funktion der rel. Feuchte."""
        phi = np.clip(np.asarray(phi, dtype=float), 0.0, 1.0)
        if self._phi_tab is not None:
            return np.interp(phi, self._phi_tab, self._w_tab)
        b = self._b_iso
        return self.w_f * (b - 1.0) * phi / (b - phi)

    def dw_dphi(self, phi):
        """Feuchtespeicherfaehigkeit dw/dphi [kg/m3]."""
        phi = np.clip(np.asarray(phi, dtype=float), 0.0, 1.0)
        if self._phi_tab is not None:
            # Zentraler Differenzenquotient des stueckweise linearen
            # Interpolanten: glaettet die Sprungstellen an den Tabellen-
            # stuetzstellen und stabilisiert damit die Picard-Iteration.
            h = 5e-3
            lo = np.clip(phi - h, 0.0, 1.0)
            hi = np.clip(phi + h, 0.0, 1.0)
            slope = (self.w(hi) - self.w(lo)) / np.maximum(hi - lo, 1e-12)
            return np.maximum(slope, 1e-9)
        b = self._b_iso
        return self.w_f * (b - 1.0) * b / (b - phi) ** 2

    def phi_from_w(self, w):
        """Umkehrung der Sorptionsisotherme: rel. Feuchte aus Wassergehalt."""
        w = np.asarray(w, dtype=float)
        if self._phi_tab is not None:
            return np.interp(np.clip(w, self._w_tab[0], self._w_tab[-1]),
                             self._w_tab, self._phi_tab)
        b = self._b_iso
        w = np.clip(w, 0.0, self.w_f)
        return w * b / (self.w_f * (b - 1.0) + w)

    def moisture_mass_percent(self, w):
        """Massebezogener Feuchtegehalt [M.-%]."""
        return 100.0 * np.asarray(w, dtype=float) / self.rho

    # ------------------------------------------------------------------
    # Transportkoeffizienten
    # ------------------------------------------------------------------
    def delta_p(self, theta, phi=None):
        """Wasserdampfpermeabilitaet [kg/(m s Pa)]: ``delta_a(T) / mu``."""
        mu = self.mu_value(phi)
        return physics.delta_a(theta) / mu

    def mu_value(self, phi=None):
        """mu-Wert, optional feuchteabhaengig interpoliert."""
        if self.mu_table and phi is not None:
            table = np.asarray(sorted(self.mu_table, key=lambda p: p[0]), dtype=float)
            return np.interp(np.clip(np.asarray(phi, dtype=float), 0.0, 1.0),
                             table[:, 0], table[:, 1])
        return self.mu

    def dw_suction(self, w):
        """Fluessigtransportkoeffizient fuer Saugen D_ws [m2/s].

        Approximation nach Kuenzel (1995) aus dem Wasseraufnahmekoeffizienten::

            D_ws(w) = 3.8 * (A_w / w_f)^2 * 1000^(w/w_f - 1)

        Ohne ``a_w`` (nicht kapillaraktives Material) wird 0 geliefert.
        """
        w = np.asarray(w, dtype=float)
        if self.dw_table:
            table = np.asarray(sorted(self.dw_table, key=lambda p: p[0]), dtype=float)
            return np.interp(np.clip(w, table[0, 0], table[-1, 0]), table[:, 0], table[:, 1])
        if self.a_w <= 0.0:
            return np.zeros_like(w)
        w_f = self.w_sat
        saturation = np.clip(w / w_f, 0.0, 1.0)
        return 3.8 * (self.a_w / w_f) ** 2 * np.power(1000.0, saturation - 1.0)

    def dw_redistribution(self, w):
        """Fluessigtransportkoeffizient fuer Weiterverteilung D_ww [m2/s]."""
        return self.redistribution_factor * self.dw_suction(w)

    def d_phi(self, phi, suction=False):
        """Fluessigleitkoeffizient bezogen auf phi: ``D_w * dw/dphi`` [kg/(m s)]."""
        w = self.w(phi)
        d_w = self.dw_suction(w) if suction else self.dw_redistribution(w)
        return d_w * self.dw_dphi(phi)

    def lambda_moist(self, w):
        """Feuchteabhaengige Waermeleitfaehigkeit [W/(m K)]."""
        u = self.moisture_mass_percent(w)
        return self.lambda_dry * (1.0 + self.lambda_moisture_supplement / 100.0 * u)

    def heat_capacity_moist(self, w):
        """Volumenbezogene Waermespeicherfaehigkeit dH/dT [J/(m3 K)]."""
        return self.rho * self.cp + np.asarray(w, dtype=float) * physics.C_WATER

    # ------------------------------------------------------------------
    def sd_value(self, thickness: float, theta: float = 20.0) -> float:
        """Aequivalente Luftschichtdicke s_d [m] fuer eine Schichtdicke [m]."""
        return float(self.mu_value(None) * thickness)

    def describe(self) -> str:
        return (
            f"{self.name}: rho={self.rho:.0f} kg/m3, cp={self.cp:.0f} J/kgK, "
            f"lambda={self.lambda_dry:.3f} W/mK, mu={self.mu:g}, "
            f"w_80={self.w_80:g} kg/m3, w_f={self.w_sat:g} kg/m3, A_w={self.a_w:g}"
        )


# ---------------------------------------------------------------------------
# Materialbibliothek
# ---------------------------------------------------------------------------

class MaterialLibrary:
    """Sammlung von Materialien mit Zugriff ueber den Namen."""

    def __init__(self, materials: Optional[Sequence[Material]] = None) -> None:
        self._materials: Dict[str, Material] = {}
        for material in materials or []:
            self.add(material)

    # -- Zugriff --------------------------------------------------------
    def add(self, material: Material) -> Material:
        self._materials[material.name] = material
        return material

    def __contains__(self, name: object) -> bool:
        return name in self._materials

    def __len__(self) -> int:
        return len(self._materials)

    def __iter__(self):
        return iter(self._materials.values())

    def get(self, name: str) -> Material:
        try:
            return self._materials[name]
        except KeyError:
            raise MaterialError(
                f"Material '{name}' nicht in der Bibliothek. Verfuegbar: "
                f"{', '.join(sorted(self._materials))}"
            ) from None

    def names(self) -> List[str]:
        return sorted(self._materials)

    def by_category(self) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        for material in self._materials.values():
            groups.setdefault(material.category or "sonstige", []).append(material.name)
        return {k: sorted(v) for k, v in sorted(groups.items())}

    # -- I/O ------------------------------------------------------------
    @classmethod
    def from_json(cls, path) -> "MaterialLibrary":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = data["materials"] if isinstance(data, dict) else data
        return cls([Material.from_dict(entry) for entry in entries])

    def to_json(self, path) -> None:
        payload = {"materials": [m.to_dict() for m in self]}
        Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def default(cls) -> "MaterialLibrary":
        """Mitgelieferte Richtwert-Datenbank laden."""
        return cls.from_json(_DB_FILE)


_default_library: Optional[MaterialLibrary] = None


def default_library() -> MaterialLibrary:
    """Zwischengespeicherte Standardbibliothek."""
    global _default_library
    if _default_library is None:
        _default_library = MaterialLibrary.default()
    return _default_library


def get_material(name: str) -> Material:
    """Material aus der Standardbibliothek holen."""
    return default_library().get(name)


def air_layer(thickness: float, thermal_resistance: Optional[float] = None,
              name: Optional[str] = None) -> Material:
    """Ruhende Luftschicht als aequivalentes Material.

    ``thermal_resistance`` [m2K/W] nach DIN EN ISO 6946 fuer die jeweilige
    Schichtdicke und Waermestromrichtung. Ohne Angabe wird der Waermedurchlass-
    widerstand fuer eine vertikale Luftschicht grob interpoliert.
    """
    if thermal_resistance is None:
        # Stuetzwerte DIN EN ISO 6946, horizontaler Waermestrom
        d = [0.005, 0.007, 0.010, 0.015, 0.025, 0.050, 0.100, 0.300]
        r = [0.11, 0.13, 0.15, 0.17, 0.18, 0.18, 0.18, 0.18]
        thermal_resistance = float(np.interp(thickness, d, r))
    lambda_eq = thickness / thermal_resistance
    # Feuchtespeicherung nur ueber die Luftfeuchte selbst (sehr klein).
    w_sat_air = physics.vapour_concentration(20.0, 1.0)
    return Material(
        name=name or f"Luftschicht {thickness * 1000:.0f} mm",
        rho=1.3,
        cp=1000.0,
        lambda_dry=lambda_eq,
        mu=1.0,
        w_f=float(w_sat_air),
        w_80=float(0.75 * w_sat_air),
        a_w=0.0,
        category="Luftschicht",
        note=(f"Ersatzmaterial fuer {thickness * 1000:.0f} mm Luftschicht, "
              f"R = {thermal_resistance:.3f} m2K/W"),
    )


def membrane(sd_value: float, thickness: float = 0.001,
             name: Optional[str] = None) -> Material:
    """Folie / Dampfbremse als duenne Materialschicht.

    ``mu`` wird aus ``s_d`` und der modellierten Dicke berechnet. Die Schicht
    muss im Gitter aufgeloest werden -- alternativ kann ein s_d-Wert direkt an
    einer Randbedingung angegeben werden (``BoundaryCondition.sd``).
    """
    return Material(
        name=name or f"Dampfbremse sd={sd_value:g} m",
        rho=130.0,
        cp=2300.0,
        lambda_dry=0.17,
        mu=sd_value / thickness,
        w_f=1.0,
        w_80=0.1,
        a_w=0.0,
        category="Folie",
        note=(f"s_d = {sd_value:g} m bei modellierter Dicke "
              f"{thickness * 1000:.1f} mm"),
    )


def variable_membrane(sd_dry: float, sd_wet: float, thickness: float = 0.001,
                      name: Optional[str] = None) -> Material:
    """Feuchtevariable Dampfbremse ueber eine mu-Tabelle.

    ``sd_dry`` gilt bei niedriger, ``sd_wet`` bei hoher mittlerer Feuchte.
    Die Interpolation ist eine einfache Naeherung des tatsaechlichen
    Produktverhaltens.
    """
    mu_dry = sd_dry / thickness
    mu_wet = sd_wet / thickness
    return Material(
        name=name or f"Feuchtevariable Dampfbremse sd={sd_dry:g}-{sd_wet:g} m",
        rho=130.0,
        cp=2300.0,
        lambda_dry=0.17,
        mu=mu_dry,
        mu_table=[[0.0, mu_dry], [0.3, mu_dry], [0.5, 0.5 * (mu_dry + mu_wet)],
                  [0.7, mu_wet], [1.0, mu_wet]],
        w_f=1.0,
        w_80=0.1,
        a_w=0.0,
        category="Folie",
        note=(f"s_d {sd_dry:g} m (trocken) bis {sd_wet:g} m (feucht), "
              f"modellierte Dicke {thickness * 1000:.1f} mm"),
    )
