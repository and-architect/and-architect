"""wufi2d | 06 Rechnen -- Berechnung starten.

Grasshopper-Skriptkomponente (Rhino 8/9, Python 3).

Eingaenge
---------
modell      obj    Item   Ausgang von '05 Modell'
rechnen     bool   Item   Schalter: True startet die Berechnung
stationaer  bool   Item   optional: nur stationaere Loesung (schnell, fuer
                          Waermebrueckenkennwerte und als Startzustand)
speichern   str    Item   optional: Pfad einer .npz-Datei fuer die Ergebnisse
pfad        str    Item   optional: Pfad zu 'wufi2d/src'

Ausgaenge
---------
ergebnis    Ergebnis-Objekt fuer '07 Ergebnis' und '08 Auswertung'
info        Zusammenfassung (Extremwerte, Wassergehalt, Rechenzeit)
datei       Pfad der gespeicherten Datei (falls 'speichern' gesetzt)

Hinweise
--------
* Die Berechnung laeuft im Grasshopper-Thread: Rhino ist waehrenddessen
  blockiert. Fuer Jahresrechnungen mit feinem Gitter besser zuerst mit kurzer
  Dauer testen -- oder headless rechnen::

      python -m wufi2d rechne modell.json --npz ergebnis.npz

* Das Ergebnis wird zusaetzlich in ``scriptcontext.sticky`` gehalten, damit ein
  Neuzeichnen des Baumes die Rechnung nicht wiederholt. Ein Umschalten von
  'rechnen' auf False behaelt das letzte Ergebnis.
"""

# r: numpy

import os
import sys
import time

import scriptcontext

STICKY_KEY = "wufi2d.pfad"
RESULT_KEY = "wufi2d.ergebnis"


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

modell = globals().get("modell")
starten = bool(globals().get("rechnen"))
nur_stationaer = bool(globals().get("stationaer"))
ziel = globals().get("speichern")

ergebnis = scriptcontext.sticky.get(RESULT_KEY)
datei = None

if modell is None:
    info = "Kein Modell angeschlossen."
elif not starten:
    info = ("Schalter 'rechnen' auf True setzen, um zu starten."
            + ("\nLetztes Ergebnis liegt vor." if ergebnis is not None else ""))
else:
    warnungen = modell.validate()
    beginn = time.time()
    if nur_stationaer:
        loeser = modell.build_solver()
        temperatur, feuchte = loeser.solve_steady_state()
        aktiv = loeser.grid.active
        ergebnis = None
        scriptcontext.sticky[RESULT_KEY] = None
        info = "\n".join([
            "Stationaere Loesung:",
            f"  Temperatur {np.nanmin(temperatur[aktiv]):.2f} .. "
            f"{np.nanmax(temperatur[aktiv]):.2f} degC",
            f"  Rel. Feuchte {np.nanmin(feuchte[aktiv]) * 100:.1f} .. "
            f"{np.nanmax(feuchte[aktiv]) * 100:.1f} %",
            f"  Rechenzeit {time.time() - beginn:.1f} s",
            "Fuer Felder und Auswertung die transiente Rechnung verwenden.",
        ])
    else:
        ergebnis = modell.run()
        scriptcontext.sticky[RESULT_KEY] = ergebnis
        zeilen = [ergebnis.summary(),
                  f"Rechenzeit {ergebnis.meta['runtime_s']:.1f} s "
                  f"({ergebnis.meta['steps']} Zeitschritte)"]
        if ziel:
            datei = str(ergebnis.to_npz(str(ziel)))
            zeilen.append(f"gespeichert: {datei}")
        if warnungen:
            zeilen.append("Warnungen: " + "; ".join(warnungen))
        info = "\n".join(zeilen)
