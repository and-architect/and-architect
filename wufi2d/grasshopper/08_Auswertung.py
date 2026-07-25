"""wufi2d | 08 Auswertung -- bauphysikalische Bewertung.

Grasshopper-Skriptkomponente (Rhino 8/9, Python 3).

Eingaenge
---------
ergebnis      obj    Item   Ausgang von '06 Rechnen' (oder Pfad einer .npz-Datei)
oberflaeche   str    Item   Name der Randbedingung fuer Schimmel/f_Rsi
                            (z.B. "innen")
punkt         Point  List   optional: Punkte fuer eine punktweise Auswertung
                            (z.B. Grenzflaeche Innendaemmung / Mauerwerk)
holzmaterial  str    List   optional: Materialnamen fuer die Holzfeuchtepruefung
t_innen       float  Item   Innenlufttemperatur [degC] fuer L2D und f_Rsi
t_aussen      float  Item   Aussenlufttemperatur [degC] fuer L2D und f_Rsi
u_werte       float  List   optional: U-Werte der ungestoerten Bauteile [W/m2K]
laengen       float  List   optional: zugehoerige Laengen [m] (fuer den Psi-Wert)
pfad          str    Item   optional: Pfad zu 'wufi2d/src'

Ausgaenge
---------
bericht     Gesamtbericht als Text
schimmel    Stunden ueber der kritischen Feuchte je Auswertungsort
feuchte     Wassergehalt: Start, Ende, Maximum, Trend [kg/a]
kennwerte   L2D [W/mK], f_Rsi [-], Psi [W/mK] (falls U-Werte angegeben)
zeitreihe   Gesamtwassergehalt je Ausgabezeitpunkt [kg]
zeiten      zugehoerige Zeitpunkte [d]

Die Grenzwerte (kritische Feuchtekurve, 20 M.-% fuer Holz) sind Naeherungen --
fuer Nachweise sind die geltenden Normen und Richtlinien maßgeblich.
"""

# r: numpy

import os
import sys

import scriptcontext

STICKY_KEY = "wufi2d.pfad"


def _bootstrap(explicit_path=None):
    for candidate in (explicit_path, scriptcontext.sticky.get(STICKY_KEY),
                      os.environ.get("WUFI2D_PATH")):
        if not candidate or not os.path.isdir(str(candidate)):
            continue
        candidate = str(candidate)
        if os.path.isdir(os.path.join(candidate, "wufi2d")):
            root = candidate
        elif os.path.isdir(os.path.join(candidate, "src", "wufi2d")):
            root = os.path.join(candidate, "src")
        else:
            continue
        if root not in sys.path:
            sys.path.insert(0, root)
        scriptcontext.sticky[STICKY_KEY] = root
        return root
    raise RuntimeError("wufi2d nicht gefunden -- zuerst '01 Setup' ausfuehren.")


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v is not None]
    return [value]


_bootstrap(globals().get("pfad"))

from wufi2d import analysis  # noqa: E402
from wufi2d.results import Results  # noqa: E402
from wufi2d.rhino import document_unit_scale  # noqa: E402

quelle = globals().get("ergebnis")
if isinstance(quelle, str):
    quelle = Results.from_npz(quelle)

if quelle is None:
    bericht = "Kein Ergebnis angeschlossen."
    schimmel = []
    feuchte = []
    kennwerte = []
    zeitreihe = []
    zeiten = []
else:
    oberflaeche = globals().get("oberflaeche")
    holzmaterialien = [str(m) for m in _as_list(globals().get("holzmaterial"))]

    bericht = analysis.report(
        quelle,
        surfaces=[str(oberflaeche)] if oberflaeche else None,
        wood_materials=holzmaterialien)

    # Schimmelrisiko an Oberflaechen und optional an Punkten
    schimmel = []
    namen = [str(oberflaeche)] if oberflaeche else list(quelle.surfaces)
    for name in namen:
        if name in quelle.surfaces:
            risiko = analysis.mould_risk_at_surface(quelle, name)
            schimmel.append(risiko.summary())
    scale = document_unit_scale()
    for punkt in _as_list(globals().get("punkt")):
        x = float(punkt.X) * scale
        y = float(punkt.Y) * scale
        try:
            schimmel.append(analysis.mould_risk_at_point(quelle, x, y).summary())
        except ValueError as fehler:
            schimmel.append(f"Punkt ({x:.3f}, {y:.3f}): {fehler}")

    bilanz = analysis.moisture_balance(quelle)
    feuchte = [bilanz.water_start, bilanz.water_end, bilanz.water_max,
               bilanz.trend_per_year]

    kennwerte = []
    t_innen = globals().get("t_innen")
    t_aussen = globals().get("t_aussen")
    if oberflaeche and t_innen is not None and t_aussen is not None:
        delta = float(t_innen) - float(t_aussen)
        l2d = analysis.thermal_coupling_coefficient(quelle, str(oberflaeche), delta)
        f_rsi = analysis.temperature_factor(quelle, str(oberflaeche),
                                           float(t_innen), float(t_aussen))
        kennwerte = [l2d, f_rsi]
        u_werte = [float(u) for u in _as_list(globals().get("u_werte"))]
        laengen = [float(l) for l in _as_list(globals().get("laengen"))]
        if u_werte and len(u_werte) == len(laengen):
            kennwerte.append(analysis.psi_value(l2d, list(zip(u_werte, laengen))))
        bericht += (f"\n\nWaermebrueckenkennwerte (stationaer auswerten!):"
                    f"\n  L2D = {l2d:.4f} W/(m K), f_Rsi = {f_rsi:.3f}")
        if len(kennwerte) > 2:
            bericht += f", Psi = {kennwerte[2]:.4f} W/(m K)"

    zeitreihe = [float(v) for v in quelle.total_water]
    zeiten = [float(t) / 86400.0 for t in quelle.times]
