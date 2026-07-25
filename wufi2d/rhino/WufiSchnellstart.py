"""wufi2d -- interaktive 2D-Waerme-/Feuchteberechnung in Rhino 8/9.

Ablauf des Befehls:

1. Geschlossene Kurven des Bauteilschnitts waehlen (XY-Ebene).
2. Je Kurve ein Material aus der Datenbank zuordnen.
3. Aussen- und Innenoberflaeche waehlen (Kurven oder Bauteilseiten).
4. Klima, Dauer und Diskretisierung abfragen.
5. Rechnen und das Ergebnis als farbiges Mesh in die Zeichnung legen.

Start in Rhino::

    _-RunPythonScript "C:\\Pfad\\zu\\wufi2d\\rhino\\WufiSchnellstart.py"

Bequemer: im Script-Editor oeffnen und ueber "Publish as command" bzw. ueber
einen Alias verfuegbar machen (siehe rhino/README.md).

Voraussetzung: NumPy in der Rhino-Python-3-Umgebung. Der Script-Editor
installiert es ueber die Zeile ``# r: numpy`` automatisch.
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


# ---------------------------------------------------------------------------
# Paket finden
# ---------------------------------------------------------------------------

def paket_laden():
    """wufi2d importierbar machen (Sticky, Umgebungsvariable oder Dialog)."""
    kandidaten = [sc.sticky.get(STICKY_KEY), os.environ.get("WUFI2D_PATH")]
    hier = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
    if hier:
        kandidaten.append(os.path.join(os.path.dirname(hier), "src"))

    for kandidat in kandidaten:
        if not kandidat or not os.path.isdir(str(kandidat)):
            continue
        kandidat = str(kandidat)
        if os.path.isdir(os.path.join(kandidat, "wufi2d")):
            wurzel = kandidat
        elif os.path.isdir(os.path.join(kandidat, "src", "wufi2d")):
            wurzel = os.path.join(kandidat, "src")
        else:
            continue
        if wurzel not in sys.path:
            sys.path.insert(0, wurzel)
        sc.sticky[STICKY_KEY] = wurzel
        return wurzel

    ordner = rs.BrowseForFolder(message="Ordner 'wufi2d/src' waehlen")
    if not ordner:
        return None
    if os.path.isdir(os.path.join(ordner, "src", "wufi2d")):
        ordner = os.path.join(ordner, "src")
    if not os.path.isdir(os.path.join(ordner, "wufi2d")):
        rs.MessageBox("In diesem Ordner liegt kein Paket 'wufi2d'.", 0, "wufi2d")
        return None
    if ordner not in sys.path:
        sys.path.insert(0, ordner)
    sc.sticky[STICKY_KEY] = ordner
    return ordner


# ---------------------------------------------------------------------------
# Eingaben
# ---------------------------------------------------------------------------

def einheitenfaktor():
    """Faktor Dokumenteinheit -> Meter."""
    return float(Rhino.RhinoMath.UnitScale(sc.doc.ModelUnitSystem,
                                           Rhino.UnitSystem.Meters))


def regionen_abfragen(library, rhino_adapter, scale):
    """Kurven waehlen und Materialien zuordnen."""
    ids = rs.GetObjects("Geschlossene Kurven des Bauteilschnitts waehlen",
                        rs.filter.curve, preselect=True)
    if not ids:
        return None

    namen = library.names()
    regionen = []
    zuletzt = namen[0]
    for index, objekt_id in enumerate(ids):
        kurve = rs.coercecurve(objekt_id)
        if kurve is None or not kurve.IsClosed:
            rs.MessageBox(f"Kurve {index + 1} ist nicht geschlossen und wird "
                          "uebersprungen.", 0, "wufi2d")
            continue
        rs.SelectObject(objekt_id)
        auswahl = rs.ListBox(namen, f"Material fuer Kurve {index + 1} von "
                             f"{len(ids)}", "wufi2d -- Material", zuletzt)
        rs.UnselectObject(objekt_id)
        if not auswahl:
            return None
        zuletzt = auswahl
        regionen.append(rhino_adapter.region_from_curve(
            kurve, auswahl, name=f"{auswahl} #{index + 1}", unit_scale=scale))
    return regionen or None


def oberflaeche_abfragen(bezeichnung, bnd, rhino_adapter, scale, toleranz):
    """Selektor fuer eine Oberflaeche: Kurve oder Bauteilseite."""
    seiten = ["Kurve waehlen", "links", "rechts", "oben", "unten"]
    auswahl = rs.ListBox(seiten, f"{bezeichnung}: Oberflaeche festlegen",
                         "wufi2d -- Oberflaeche", seiten[0])
    if not auswahl:
        return None
    if auswahl != "Kurve waehlen":
        return bnd.make_selector(auswahl)
    ids = rs.GetObjects(f"Kurve(n) der {bezeichnung}-Oberflaeche waehlen",
                        rs.filter.curve)
    if not ids:
        return None
    punkte = []
    for objekt_id in ids:
        punkte.extend(rhino_adapter.polyline_points(rs.coercecurve(objekt_id),
                                                    unit_scale=scale))
    return bnd.PolylineSelector(punkte, tolerance=toleranz)


def zahl(frage, standard, minimum=None, maximum=None):
    wert = rs.GetReal(frage, standard, minimum, maximum)
    return standard if wert is None else float(wert)


# ---------------------------------------------------------------------------
# Hauptteil
# ---------------------------------------------------------------------------

def main():
    wurzel = paket_laden()
    if not wurzel:
        return

    import numpy as np

    import wufi2d
    from wufi2d import boundary as bnd
    from wufi2d import rhino as rhino_adapter
    from wufi2d.climate import ConstantClimate, SineClimate
    from wufi2d.model import Model
    from wufi2d.solver import InitialConditions, SolverOptions

    scale = einheitenfaktor()
    library = wufi2d.default_library()

    regionen = regionen_abfragen(library, rhino_adapter, scale)
    if not regionen:
        print("Abgebrochen: keine Region definiert.")
        return

    # Diskretisierung
    max_zelle = zahl("Groesste Zellabmessung [mm]", 20.0, 1.0, 500.0) / 1000.0
    min_zelle = zahl("Kleinste Zellabmessung an Raendern [mm]", 2.0, 0.1, 100.0) / 1000.0
    toleranz = max(0.5 * min_zelle, 0.002)

    aussen_selektor = oberflaeche_abfragen("Aussen", bnd, rhino_adapter, scale, toleranz)
    if aussen_selektor is None:
        print("Abgebrochen.")
        return
    innen_selektor = oberflaeche_abfragen("Innen", bnd, rhino_adapter, scale, toleranz)
    if innen_selektor is None:
        print("Abgebrochen.")
        return

    # Klima
    klimatypen = ["konstant", "sinus (Jahresgang)"]
    klimawahl = rs.ListBox(klimatypen, "Aussenklima", "wufi2d -- Klima", klimatypen[1])
    if not klimawahl:
        print("Abgebrochen.")
        return
    if klimawahl.startswith("konstant"):
        aussenklima = ConstantClimate(zahl("Aussentemperatur [degC]", -5.0),
                                      zahl("Aussenluftfeuchte [%]", 80.0, 1.0, 100.0) / 100.0)
    else:
        aussenklima = SineClimate(
            mean_temperature=zahl("Jahresmittel der Aussentemperatur [degC]", 9.0),
            amplitude_temperature=zahl("Amplitude der Aussentemperatur [K]", 10.0),
            mean_rh=zahl("Mittlere Aussenluftfeuchte [%]", 78.0, 1.0, 100.0) / 100.0,
            amplitude_rh=zahl("Amplitude der Aussenluftfeuchte [%]", 10.0, 0.0, 50.0) / 100.0)
    innenklima = ConstantClimate(zahl("Innentemperatur [degC]", 20.0),
                                 zahl("Innenluftfeuchte [%]", 50.0, 1.0, 100.0) / 100.0)

    dauer_tage = zahl("Simulationsdauer [d]", 365.0, 0.1, 20000.0)
    dt_stunden = zahl("Zeitschritt [h]", 1.0, 0.01, 24.0)
    start_rf = zahl("Anfangsfeuchte im Bauteil [%]", 80.0, 1.0, 100.0) / 100.0
    start_temp = zahl("Anfangstemperatur im Bauteil [degC]", 20.0)

    # Modell
    modell = Model(name="Rhino-Bauteil")
    modell.regions = regionen
    modell.grid_options.max_cell = max_zelle
    modell.grid_options.min_cell = min_zelle
    modell.add_boundary(aussen_selektor, bnd.exterior_surface(aussenklima))
    modell.add_boundary(innen_selektor, bnd.interior_surface(innenklima))
    modell.options = SolverOptions(duration=dauer_tage * 86400.0,
                                   dt=dt_stunden * 3600.0,
                                   output_interval=max(dauer_tage * 86400.0 / 100.0,
                                                       3600.0))
    modell.initial = InitialConditions(temperature=start_temp, rh=start_rf)

    for warnung in modell.validate():
        print(f"Warnung: {warnung}")

    gitter = modell.build_grid()
    print(gitter.summary())
    schritte = int(modell.options.duration / modell.options.dt)
    if not rs.MessageBox(
            f"{gitter.n_active} aktive Zellen, {schritte} Zeitschritte.\n"
            "Rhino ist waehrend der Rechnung blockiert.\n\nBerechnung starten?",
            4 | 32, "wufi2d") == 6:
        return

    # Rechnen
    def fortschritt(t, dauer):
        Rhino.RhinoApp.SetCommandPrompt(
            f"wufi2d rechnet: {100.0 * t / dauer:.0f} %  "
            f"({t / 86400.0:.1f} von {dauer / 86400.0:.0f} Tagen)")
        Rhino.RhinoApp.Wait()

    loeser = modell.build_solver(gitter)
    ergebnis = loeser.run(progress=fortschritt)
    Rhino.RhinoApp.SetCommandPrompt("")
    sc.sticky[ERGEBNIS_KEY] = ergebnis
    print(ergebnis.summary())

    # Darstellung
    groessen = ["temperature", "rh", "water_content", "moisture_mass_percent"]
    groesse = rs.ListBox(groessen, "Darzustellende Groesse",
                         "wufi2d -- Ergebnis", groessen[0]) or groessen[0]
    feld = ergebnis.field(groesse)
    palette = rhino_adapter.QUANTITY_PALETTE.get(groesse, "temperatur")
    mesh = rhino_adapter.result_mesh(gitter, feld, palette=palette,
                                     unit_scale=1.0 / scale if scale else 1.0)
    if not rs.IsLayer(LAYER):
        rs.AddLayer(LAYER)
    rs.CurrentLayer(LAYER)
    objekt_id = sc.doc.Objects.AddMesh(mesh)
    sc.doc.Views.Redraw()
    aktiv = gitter.active
    print(f"Mesh '{groesse}' erzeugt ({objekt_id}); Wertebereich "
          f"{float(np.nanmin(feld[aktiv])):.2f} .. {float(np.nanmax(feld[aktiv])):.2f}. "
          "Anzeigemodus 'Schattiert' zeigt die Farben.")

    speichern = rs.MessageBox("Ergebnisse als Datei speichern?", 4 | 32, "wufi2d")
    if speichern == 6:
        ziel = rs.SaveFileName("Ergebnisse speichern", "NumPy-Archiv (*.npz)|*.npz||")
        if ziel:
            print(f"gespeichert: {ergebnis.to_npz(ziel)}")


if __name__ == "__main__":
    main()
