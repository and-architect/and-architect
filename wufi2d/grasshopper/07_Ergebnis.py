"""wufi2d | 07 Ergebnis -- Felder als farbiges Mesh darstellen.

Grasshopper-Skriptkomponente (Rhino 8/9, Python 3).

Eingaenge
---------
ergebnis    obj    Item   Ausgang von '06 Rechnen' (oder Pfad einer .npz-Datei)
groesse     str    Item   "temperature" | "rh" | "water_content" |
                          "moisture_mass_percent" | "vapour_pressure"
zeit_tage   float  Item   Auswertungszeitpunkt [d]; leer = letzter Zeitpunkt
min_wert    float  Item   optional: unteres Ende der Farbskala
max_wert    float  Item   optional: oberes Ende der Farbskala
palette     str    Item   "temperatur" | "feuchte" | "wasser" | "graustufen"
isolinie    float  Item   optional: Wert, dessen Isolinie als Punkte ausgegeben wird
pfad        str    Item   optional: Pfad zu 'wufi2d/src'

Ausgaenge
---------
mesh        farbiges Mesh (eine Zelle = eine Fläche, flache Faerbung)
werte       Zellwerte in der Reihenfolge der Mesh-Flaechen
legende     Stuetzwerte der Farbskala (6 Stufen)
grenzen     [Minimum, Maximum] der dargestellten Groesse
punkte      Punkte der Isolinie (wenn 'isolinie' gesetzt)
info        Zeitpunkt, Groesse und Extremwerte

Einheiten: Temperatur in degC, rel. Feuchte 0..1, Wassergehalt in kg/m3,
Feuchtegehalt in M.-%, Dampfdruck in Pa.
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


_bootstrap(globals().get("pfad"))

import numpy as np  # noqa: E402
import Rhino.Geometry as rg  # noqa: E402

from wufi2d.results import Results  # noqa: E402
from wufi2d.rhino import (QUANTITY_PALETTE, document_unit_scale,  # noqa: E402
                         isotherm_points, legend_steps, result_mesh)

quelle = globals().get("ergebnis")
if isinstance(quelle, str):
    quelle = Results.from_npz(quelle)

if quelle is None:
    mesh = None
    werte = []
    legende = []
    grenzen = []
    punkte = []
    info = "Kein Ergebnis angeschlossen."
else:
    groesse = str(globals().get("groesse") or "temperature").strip()
    zeit_tage = globals().get("zeit_tage")
    zeit = None if zeit_tage is None else float(zeit_tage) * 86400.0
    feld = quelle.field(groesse, time=zeit)
    schritt = quelle.n_steps - 1 if zeit is None else quelle.index_at(zeit)

    aktiv = quelle.grid.active
    min_wert = globals().get("min_wert")
    max_wert = globals().get("max_wert")
    unten = float(min_wert) if min_wert is not None else float(np.nanmin(feld[aktiv]))
    oben = float(max_wert) if max_wert is not None else float(np.nanmax(feld[aktiv]))

    palette = str(globals().get("palette")
                  or QUANTITY_PALETTE.get(groesse, "temperatur"))
    scale = document_unit_scale()
    zurueck = 1.0 / scale if scale else 1.0

    mesh = result_mesh(quelle.grid, feld, v_min=unten, v_max=oben, palette=palette,
                       unit_scale=zurueck)
    werte = quelle.cell_values(groesse, time=zeit)
    legende = legend_steps(unten, oben)
    grenzen = [unten, oben]

    punkte = []
    isolinie = globals().get("isolinie")
    if isolinie is not None:
        punkte = [rg.Point3d(x * zurueck, y * zurueck, 0.0)
                  for x, y in isotherm_points(quelle.grid, feld, float(isolinie))]

    info = "\n".join([
        f"Groesse: {groesse}, Palette: {palette}",
        f"Zeitpunkt: {quelle.times[schritt] / 86400.0:.2f} d "
        f"(Schritt {schritt + 1}/{quelle.n_steps})",
        f"Wertebereich im Feld: {float(np.nanmin(feld[aktiv])):.3f} .. "
        f"{float(np.nanmax(feld[aktiv])):.3f}",
        f"Farbskala: {unten:.3f} .. {oben:.3f}",
    ])
