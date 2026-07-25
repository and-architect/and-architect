"""wufi2d -- gespeicherte Ergebnisse in Rhino darstellen.

Laedt eine ``.npz``-Ergebnisdatei (oder das letzte Ergebnis dieser
Rhino-Sitzung) und legt das gewaehlte Feld als farbiges Mesh in die Zeichnung.
Mehrere Zeitpunkte koennen gestapelt werden -- dann entsteht eine "Zeitleiter"
in z-Richtung, die den Verlauf zeigt.

Start in Rhino::

    _-RunPythonScript "C:\\Pfad\\zu\\wufi2d\\rhino\\WufiErgebnisAnzeigen.py"
"""

# r: numpy

import os
import sys

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

STICKY_KEY = "wufi2d.pfad"
ERGEBNIS_KEY = "wufi2d.ergebnis"
LAYER = "WUFI Ergebnis"


def paket_laden():
    kandidaten = [sc.sticky.get(STICKY_KEY), os.environ.get("WUFI2D_PATH")]
    hier = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
    if hier:
        kandidaten.append(os.path.join(os.path.dirname(hier), "src"))
    for kandidat in kandidaten:
        if not kandidat or not os.path.isdir(str(kandidat)):
            continue
        kandidat = str(kandidat)
        wurzel = (kandidat if os.path.isdir(os.path.join(kandidat, "wufi2d"))
                  else os.path.join(kandidat, "src"))
        if not os.path.isdir(os.path.join(wurzel, "wufi2d")):
            continue
        if wurzel not in sys.path:
            sys.path.insert(0, wurzel)
        sc.sticky[STICKY_KEY] = wurzel
        return wurzel
    ordner = rs.BrowseForFolder(message="Ordner 'wufi2d/src' waehlen")
    if ordner and os.path.isdir(os.path.join(ordner, "wufi2d")):
        sys.path.insert(0, ordner)
        sc.sticky[STICKY_KEY] = ordner
        return ordner
    return None


def main():
    if not paket_laden():
        return

    import numpy as np

    from wufi2d import analysis
    from wufi2d import rhino as rhino_adapter
    from wufi2d.results import Results

    ergebnis = sc.sticky.get(ERGEBNIS_KEY)
    if ergebnis is None or rs.MessageBox(
            "Ergebnis aus einer Datei laden?\n(Nein = letztes Ergebnis dieser "
            "Sitzung verwenden)", 4 | 32, "wufi2d") == 6:
        pfad = rs.OpenFileName("Ergebnisdatei waehlen",
                               "NumPy-Archiv (*.npz)|*.npz||")
        if not pfad:
            return
        ergebnis = Results.from_npz(pfad)
    print(ergebnis.summary())

    groessen = ["temperature", "rh", "water_content", "moisture_mass_percent",
                "vapour_pressure"]
    groesse = rs.ListBox(groessen, "Darzustellende Groesse", "wufi2d", groessen[0])
    if not groesse:
        return

    anzahl = rs.GetInteger("Anzahl darzustellender Zeitpunkte", 1, 1,
                           ergebnis.n_steps)
    if anzahl is None:
        return
    abstand = 0.0
    if anzahl > 1:
        abstand = rs.GetReal("Versatz je Zeitpunkt in z-Richtung "
                             "[Dokumenteinheiten]", 0.5) or 0.0

    scale = float(Rhino.RhinoMath.UnitScale(sc.doc.ModelUnitSystem,
                                            Rhino.UnitSystem.Meters))
    zurueck = 1.0 / scale if scale else 1.0

    # gemeinsame Farbskala ueber alle dargestellten Zeitpunkte
    schritte = np.linspace(0, ergebnis.n_steps - 1, anzahl).round().astype(int)
    felder = [ergebnis.field(groesse, step=int(k)) for k in schritte]
    aktiv = ergebnis.grid.active
    unten = min(float(np.nanmin(f[aktiv])) for f in felder)
    oben = max(float(np.nanmax(f[aktiv])) for f in felder)
    palette = rhino_adapter.QUANTITY_PALETTE.get(groesse, "temperatur")

    if not rs.IsLayer(LAYER):
        rs.AddLayer(LAYER)
    rs.CurrentLayer(LAYER)
    for index, (schritt, feld) in enumerate(zip(schritte, felder)):
        mesh = rhino_adapter.result_mesh(ergebnis.grid, feld, v_min=unten, v_max=oben,
                                         palette=palette, z=index * abstand,
                                         unit_scale=zurueck)
        sc.doc.Objects.AddMesh(mesh)
        print(f"  t = {ergebnis.times[schritt] / 86400.0:8.2f} d  "
              f"{float(np.nanmin(feld[aktiv])):8.2f} .. "
              f"{float(np.nanmax(feld[aktiv])):8.2f}")
    sc.doc.Views.Redraw()

    print(f"Farbskala {groesse}: {unten:.3f} .. {oben:.3f} ({palette})")
    print()
    print(analysis.report(ergebnis))


if __name__ == "__main__":
    main()
