"""wufi2d | 05 Modell -- Gitter erzeugen und Modell zusammenstellen.

Grasshopper-Skriptkomponente (Rhino 8/9, Python 3).

Eingaenge
---------
regionen    obj    List   Ausgang von '02 Region'
raender     obj    List   Ausgaenge von '04 Rand'
zellgroesse float  Item   groesste Zellabmessung [m] (Standard 0.02)
min_zelle   float  Item   kleinste Zellabmessung an Raendern/Grenzen [m]
                          (Standard 0.002)
wachstum    float  Item   Wachstumsfaktor des Gitters (Standard 1.3)
dauer_tage  float  Item   Simulationsdauer [d] (Standard 365)
dt_stunden  float  Item   Zeitschritt [h] (Standard 1)
ausgabe_h   float  Item   Abstand der gespeicherten Ergebnisse [h] (Standard 24)
start_temp  float  Item   Anfangstemperatur [degC] (Standard 20)
start_rf    float  Item   Anfangsfeuchte 0..1 (Standard 0.8)
name        str    Item   Bezeichnung des Bauteils
pfad        str    Item   optional: Pfad zu 'wufi2d/src'

Ausgaenge
---------
modell      Modell-Objekt fuer '06 Rechnen'
gitter      Vorschau-Mesh der Materialverteilung
linien      Gitterlinien zur Kontrolle der Diskretisierung
info        Gitterkennzahlen, Randzuordnung, Rechenzeitabschaetzung
warnungen   Plausibilitaetspruefung (leer = in Ordnung)

Faustregel zur Diskretisierung
------------------------------
An Oberflaechen und Materialgrenzen sind feine Zellen (1-5 mm) wichtig, in der
Bauteilmitte darf das Gitter grob sein. Genau das macht das expandierende
Gitter automatisch. Die Rechenzeit steigt etwa linear mit der Zellzahl und mit
der Anzahl der Zeitschritte.
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

import Rhino.Geometry as rg  # noqa: E402

from wufi2d.model import Model  # noqa: E402
from wufi2d.rhino import document_unit_scale, grid_lines, material_mesh  # noqa: E402
from wufi2d.solver import InitialConditions, SolverOptions  # noqa: E402

regionen = _as_list(globals().get("regionen"))
raender = _as_list(globals().get("raender"))

if not regionen:
    modell = None
    gitter = None
    linien = []
    info = "Keine Region angeschlossen."
    warnungen = ["Keine Region angeschlossen."]
else:
    modell = Model(name=str(globals().get("name") or "Bauteil"))
    modell.regions = list(regionen)
    modell.grid_options.max_cell = float(globals().get("zellgroesse") or 0.02)
    modell.grid_options.min_cell = float(globals().get("min_zelle") or 0.002)
    modell.grid_options.growth = float(globals().get("wachstum") or 1.3)
    for regel in raender:
        selektor, bedingung = regel
        modell.add_boundary(selektor, bedingung)

    dauer_tage = float(globals().get("dauer_tage") or 365.0)
    dt_stunden = float(globals().get("dt_stunden") or 1.0)
    ausgabe_h = float(globals().get("ausgabe_h") or 24.0)
    modell.options = SolverOptions(duration=dauer_tage * 86400.0,
                                   dt=dt_stunden * 3600.0,
                                   output_interval=ausgabe_h * 3600.0)
    start_temp = globals().get("start_temp")
    start_rf = globals().get("start_rf")
    modell.initial = InitialConditions(
        temperature=float(start_temp if start_temp is not None else 20.0),
        rh=float(start_rf if start_rf is not None else 0.8))

    grid = modell.build_grid()
    warnungen = modell.validate()

    scale = document_unit_scale()
    zurueck = 1.0 / scale if scale else 1.0  # Meter -> Dokumenteinheiten
    gitter = material_mesh(grid, unit_scale=zurueck)
    linien = [rg.Line(rg.Point3d(*a), rg.Point3d(*b))
              for a, b in grid_lines(grid, unit_scale=zurueck)]

    zuordnung = modell.boundary_set().assign(grid.exposed_faces())
    schritte = int(modell.options.duration / modell.options.dt)
    info = "\n".join([
        grid.summary(),
        "",
        zuordnung.summary(),
        "",
        f"Zeitschritte: {schritte} ({dauer_tage:.0f} d, dt = {dt_stunden:.2f} h)",
        f"Groessenordnung Rechenaufwand: {grid.n_active * schritte / 1e6:.1f} "
        "Mio. Zell-Zeitschritte",
    ])
