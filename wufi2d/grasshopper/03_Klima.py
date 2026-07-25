"""wufi2d | 03 Klima -- Aussen- und Innenklima definieren.

Grasshopper-Skriptkomponente (Rhino 8/9, Python 3).

Eingaenge
---------
typ         str    Item   "konstant" | "sinus" | "csv" | "innen"
temperatur  float  Item   konstant: Lufttemperatur [degC]
                          sinus:    Jahresmittel [degC]
rf          float  Item   konstant: rel. Feuchte 0..1
                          sinus:    Jahresmittel 0..1
amplitude_t float  Item   sinus: Amplitude der Temperatur [K] (Standard 10)
amplitude_rf float Item   sinus: Amplitude der Feuchte (Standard 0.1)
tagesgang_t float  Item   sinus: Amplitude des Tagesgangs [K]
strahlung   float  Item   sinus: Spitzenwert der Einstrahlung [W/m2]
regen       float  Item   konstant/sinus: Schlagregen [mm/h] auf die Flaeche
datei       str    Item   csv: Pfad zur Klimadatei (Spalten Zeit/Temperatur/rF/...)
aussenklima obj    Item   innen: Aussenklima, aus dem das Innenklima folgt
feuchtelast str    Item   innen: "normal" oder "hoch"
pfad        str    Item   optional: Pfad zu 'wufi2d/src'

Ausgaenge
---------
klima   Klima-Objekt fuer die Rand-Komponente
info    Beschreibung und Extremwerte
werte   Stundenwerte des ersten Jahres (Temperatur) zur Kontrolle

"innen" bildet das in EN 15026 / DIN 4108-3 gebraeuchliche Innenklima ab:
Innentemperatur und Innenfeuchte folgen dem Tagesmittel der Aussentemperatur.
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

from wufi2d.climate import (ConstantClimate, InteriorClimateFromExterior,  # noqa: E402
                           SineClimate, read_climate_csv)

typ = str(globals().get("typ") or "konstant").strip().lower()
temperatur = globals().get("temperatur")
rf = globals().get("rf")
regen_mm_h = globals().get("regen") or 0.0
regen = float(regen_mm_h) / 3600.0  # mm/h -> kg/(m2 s)

if typ in ("konstant", "constant"):
    klima = ConstantClimate(
        temperature=float(temperatur if temperatur is not None else 20.0),
        rh=float(rf if rf is not None else 0.5),
        solar=float(globals().get("strahlung") or 0.0),
        rain=regen)
elif typ in ("sinus", "sine"):
    klima = SineClimate(
        mean_temperature=float(temperatur if temperatur is not None else 10.0),
        amplitude_temperature=float(globals().get("amplitude_t") or 10.0),
        mean_rh=float(rf if rf is not None else 0.75),
        amplitude_rh=float(globals().get("amplitude_rf") or 0.1),
        daily_temperature_amplitude=float(globals().get("tagesgang_t") or 0.0),
        solar_peak=float(globals().get("strahlung") or 0.0),
        rain=regen)
elif typ in ("csv", "datei", "file"):
    datei = globals().get("datei")
    if not datei:
        raise ValueError("Fuer typ='csv' muss 'datei' angegeben werden")
    klima = read_climate_csv(str(datei), rain_unit="mm/h")
elif typ in ("innen", "interior", "en15026"):
    aussen = globals().get("aussenklima")
    if aussen is None:
        raise ValueError("Fuer typ='innen' muss 'aussenklima' angeschlossen werden")
    klima = InteriorClimateFromExterior(
        aussen, moisture_load=str(globals().get("feuchtelast") or "normal"))
else:
    raise ValueError(f"Unbekannter Klimatyp '{typ}'. Erlaubt: konstant, sinus, "
                     "csv, innen")

# Kontrollreihe: Stundenwerte eines Jahres
stunden = np.arange(0.0, 8760.0) * 3600.0
reihe = klima.series(stunden)
werte = [float(v) for v in reihe["temperature"]]
info = "\n".join([
    klima.describe(),
    f"Temperatur {reihe['temperature'].min():.1f} .. {reihe['temperature'].max():.1f} degC",
    f"Rel. Feuchte {reihe['rh'].min() * 100:.0f} .. {reihe['rh'].max() * 100:.0f} %",
    f"Einstrahlung max {reihe['solar'].max():.0f} W/m2, "
    f"Regen max {reihe['rain'].max() * 3600.0:.2f} mm/h",
])
