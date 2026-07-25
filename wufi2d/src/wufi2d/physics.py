"""Physikalische Basisfunktionen fuer die hygrothermische Simulation.

Grundlage ist das Modell nach Kuenzel (Fraunhofer-Institut fuer Bauphysik, IBP),
das auch WUFI zugrunde liegt:

    Kuenzel, H.M. (1995): Simultaneous Heat and Moisture Transport in Building
    Components. One- and two-dimensional calculation using simple parameters.
    Fraunhofer IRB Verlag, Stuttgart.

Gekoppelte Bilanzgleichungen (2D, Feuchtepotential = relative Luftfeuchte phi):

    Feuchtebilanz
        dw/dphi * dphi/dt = div( D_phi * grad(phi) + delta_p * grad(phi * p_sat) )

    Waermebilanz
        dH/dT * dT/dt = div( lambda * grad(T) ) + h_v * div( delta_p * grad(phi * p_sat) )

mit

    w           Wassergehalt                            [kg/m3]
    dw/dphi     Feuchtespeicherfaehigkeit               [kg/m3]
    D_phi       Fluessigtransportkoeffizient bzgl. phi  [kg/(m s)]
    delta_p     Wasserdampfpermeabilitaet               [kg/(m s Pa)]
    p_sat       Wasserdampfsaettigungsdruck             [Pa]
    dH/dT       Waermespeicherfaehigkeit (feucht)       [J/(m3 K)]
    lambda      Waermeleitfaehigkeit (feucht)           [W/(m K)]
    h_v         Verdunstungsenthalpie von Wasser        [J/kg]

Alle Funktionen arbeiten sowohl mit Skalaren als auch mit NumPy-Arrays.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

RHO_WATER = 1000.0
"""Dichte von fluessigem Wasser [kg/m3]."""

C_WATER = 4187.0
"""Spezifische Waermekapazitaet von fluessigem Wasser [J/(kg K)]."""

C_ICE = 2100.0
"""Spezifische Waermekapazitaet von Eis [J/(kg K)]."""

H_EVAPORATION = 2_500_000.0
"""Verdunstungsenthalpie von Wasser [J/kg] (Kuenzel rechnet mit 2500 kJ/kg)."""

H_FUSION = 333_500.0
"""Schmelzenthalpie von Eis [J/kg] (nur fuer optionale Auswertungen)."""

R_VAPOUR = 461.5
"""Spezifische Gaskonstante von Wasserdampf [J/(kg K)]."""

P_ATM = 101_325.0
"""Normluftdruck [Pa]."""

KELVIN = 273.15
"""Nullpunktverschiebung Celsius -> Kelvin."""

STEFAN_BOLTZMANN = 5.67e-8
"""Stefan-Boltzmann-Konstante [W/(m2 K4)]."""

BETA_PER_ALPHA = 7.0e-9
"""Lewis-Beziehung: beta_p / alpha_c ~ 7e-9 [kg/(m2 s Pa)] / [W/(m2 K)].

Naeherung nach Kuenzel zur Abschaetzung des Wasserdampfuebergangs-
koeffizienten aus dem Waermeuebergangskoeffizienten.
"""

SECONDS_PER_HOUR = 3600.0


# ---------------------------------------------------------------------------
# Wasserdampf
# ---------------------------------------------------------------------------

def p_sat(theta):
    """Wasserdampfsaettigungsdruck [Pa] fuer die Temperatur ``theta`` [degC].

    Magnus-Formulierung nach Kuenzel (1995), Gl. (14) mit getrennten
    Koeffizientensaetzen ueber und unter dem Gefrierpunkt::

        p_sat = 611 * exp( a * theta / (theta_0 + theta) )

        theta >= 0 degC :  a = 17.08,  theta_0 = 234.18 degC
        theta <  0 degC :  a = 22.44,  theta_0 = 272.44 degC
    """
    theta = np.asarray(theta, dtype=float)
    a = np.where(theta >= 0.0, 17.08, 22.44)
    theta0 = np.where(theta >= 0.0, 234.18, 272.44)
    # Schutz gegen den Pol bei theta = -theta0 (physikalisch irrelevant,
    # verhindert aber Overflow bei divergierenden Iterationen).
    denom = np.maximum(theta0 + theta, 1.0)
    value = 611.0 * np.exp(a * theta / denom)
    return value if value.ndim else float(value)


def dp_sat_dtheta(theta):
    """Ableitung des Saettigungsdampfdrucks nach der Temperatur [Pa/K]."""
    theta = np.asarray(theta, dtype=float)
    a = np.where(theta >= 0.0, 17.08, 22.44)
    theta0 = np.where(theta >= 0.0, 234.18, 272.44)
    denom = np.maximum(theta0 + theta, 1.0)
    value = p_sat(theta) * a * theta0 / denom**2
    return value if np.ndim(value) else float(value)


def delta_a(theta, p_ambient=P_ATM):
    """Wasserdampfleitfaehigkeit ruhender Luft [kg/(m s Pa)].

    Nach Schirmer, in der von Kuenzel (1995) verwendeten Form::

        delta_a = 2.0e-7 * T^0.81 / p_ambient        (T in K)
    """
    t_kelvin = np.asarray(theta, dtype=float) + KELVIN
    value = 2.0e-7 * np.power(t_kelvin, 0.81) / p_ambient
    return value if np.ndim(value) else float(value)


def vapour_pressure(theta, phi):
    """Wasserdampfpartialdruck [Pa] aus Temperatur [degC] und rel. Feuchte [-]."""
    return np.asarray(phi, dtype=float) * p_sat(theta)


def relative_humidity(theta, p_v):
    """Relative Feuchte [-] aus Temperatur [degC] und Dampfdruck [Pa]."""
    return np.asarray(p_v, dtype=float) / p_sat(theta)


def humidity_ratio(theta, phi, p_ambient=P_ATM):
    """Absolute Feuchte (Wasserdampfgehalt der Luft) [kg/kg trockene Luft]."""
    p_v = vapour_pressure(theta, phi)
    return 0.622 * p_v / np.maximum(p_ambient - p_v, 1.0)


def vapour_concentration(theta, phi):
    """Wasserdampfkonzentration [kg/m3] (ideales Gas)."""
    return vapour_pressure(theta, phi) / (R_VAPOUR * (np.asarray(theta, dtype=float) + KELVIN))


def dew_point(theta, phi):
    """Taupunkttemperatur [degC] fuer Temperatur [degC] und rel. Feuchte [-].

    Invertierung der Magnus-Formel mit dem Koeffizientensatz fuer ``theta >= 0``
    bzw. ``theta < 0``, ausgewaehlt anhand des resultierenden Taupunkts.
    """
    phi = np.clip(np.asarray(phi, dtype=float), 1e-6, 1.0)
    p_v = vapour_pressure(theta, phi)
    ln = np.log(np.maximum(p_v, 1e-6) / 611.0)

    def invert(a, theta0):
        return theta0 * ln / (a - ln)

    td_pos = invert(17.08, 234.18)
    td_neg = invert(22.44, 272.44)
    value = np.where(td_pos >= 0.0, td_pos, td_neg)
    return value if np.ndim(value) else float(value)


def suction_pressure(theta, phi):
    """Kapillardruck / Saugspannung [Pa] nach Kelvin-Gleichung.

    Negative Werte bedeuten Unterdruck in der Fluessigphase::

        p_c = rho_w * R_v * T * ln(phi)
    """
    phi = np.clip(np.asarray(phi, dtype=float), 1e-12, 1.0)
    t_kelvin = np.asarray(theta, dtype=float) + KELVIN
    return RHO_WATER * R_VAPOUR * t_kelvin * np.log(phi)


def phi_from_suction(theta, p_c):
    """Umkehrung von :func:`suction_pressure`: rel. Feuchte aus Kapillardruck."""
    t_kelvin = np.asarray(theta, dtype=float) + KELVIN
    return np.exp(np.asarray(p_c, dtype=float) / (RHO_WATER * R_VAPOUR * t_kelvin))


# ---------------------------------------------------------------------------
# Mittelung von Transportkoeffizienten an Zellgrenzen
# ---------------------------------------------------------------------------

def harmonic_face_value(k_a, k_b, d_a, d_b):
    """Reihenschaltung zweier Halbzellen-Widerstaende.

    Liefert den aequivalenten Leitwert ``k_f`` bezogen auf den Abstand
    ``d_a + d_b`` der beiden Zellmittelpunkte::

        (d_a + d_b) / k_f = d_a / k_a + d_b / k_b

    Das ist die fuer sprunghafte Materialwechsel korrekte Mittelung im
    Finite-Volumen-Verfahren. Ist einer der Leitwerte null (z.B. voellig
    trockener Fluessigtransport oder dampfdichte Schicht), ist auch ``k_f``
    null, d.h. die Grenzflaeche sperrt.
    """
    k_a = np.asarray(k_a, dtype=float)
    k_b = np.asarray(k_b, dtype=float)
    resistance = np.where(k_a > 0.0, d_a / np.where(k_a > 0.0, k_a, 1.0), np.inf)
    resistance = resistance + np.where(k_b > 0.0, d_b / np.where(k_b > 0.0, k_b, 1.0), np.inf)
    return np.where(np.isfinite(resistance) & (resistance > 0.0),
                    (d_a + d_b) / np.where(resistance > 0.0, resistance, 1.0),
                    0.0)
