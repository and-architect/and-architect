"""wufi2d | 04 Rand -- Randbedingung einer Oberflaeche.

Grasshopper-Skriptkomponente (Rhino 8/9, Python 3).

Eingaenge
---------
kurve       Curve  List   Oberflaechenkurve(n); alternativ 'seite' verwenden
seite       str    Item   "links" | "rechts" | "oben" | "unten" | "alle"
klima       obj    Item   Klima-Objekt aus '03 Klima' (nicht bei typ='fest')
typ         str    Item   "aussen" | "innen" | "fest" | "adiabat"
alpha       float  Item   Waermeuebergangskoeffizient [W/m2K]
                          (Standard: aussen 17, innen 8)
wind_faktor float  Item   optional: alpha = alpha + wind_faktor * v
sd          float  Item   aequivalente Luftschichtdicke der Beschichtung [m]
absorption  float  Item   kurzwelliger Absorptionsgrad (Standard aussen 0.6)
regenanteil float  Item   Anteil des Schlagregens, der aufgenommen wird
                          (Standard aussen 0.7, innen 0)
temperatur  float  Item   typ='fest': Oberflaechentemperatur [degC]
rf          float  Item   typ='fest': Oberflaechenfeuchte 0..1
toleranz    float  Item   Fangabstand der Kurve [m] (Standard 0.005)
name        str    Item   Bezeichnung, erscheint in den Ergebnissen
pfad        str    Item   optional: Pfad zu 'wufi2d/src'

Ausgaenge
---------
rand    Regel (Selektor + Randbedingung) fuer die Modell-Komponente
info    Beschreibung der Randbedingung

Hinweise
--------
* 'toleranz' sollte etwa der halben kleinsten Zellgroesse entsprechen. Wird die
  Oberflaeche nicht gefunden, meldet die Modell-Komponente eine Warnung.
* Nicht zugeordnete Raender sind adiabat (Symmetrie-/Schnittkante) -- das ist
  fuer Ausschnitte aus einem groesseren Bauteil richtig.
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

from wufi2d import boundary as bnd  # noqa: E402
from wufi2d.rhino import document_unit_scale, polyline_points  # noqa: E402

typ = str(globals().get("typ") or "aussen").strip().lower()
kurven = _as_list(globals().get("kurve"))
seite = globals().get("seite")
toleranz = float(globals().get("toleranz") or 0.005)
bezeichnung = globals().get("name")

# --- Selektor ---------------------------------------------------------------
if kurven:
    scale = document_unit_scale()
    punkte = []
    for kurve in kurven:
        punkte.extend(polyline_points(kurve, unit_scale=scale))
    selektor = bnd.PolylineSelector(punkte, tolerance=toleranz)
elif seite:
    selektor = bnd.make_selector(str(seite))
else:
    raise ValueError("Bitte 'kurve' anschliessen oder 'seite' angeben "
                     "(links/rechts/oben/unten/alle)")

# --- Randbedingung ----------------------------------------------------------
klima = globals().get("klima")
alpha = globals().get("alpha")
sd = float(globals().get("sd") or 0.0)

if typ in ("adiabat", "adiabatic", "symmetrie"):
    bedingung = bnd.AdiabaticBoundary(bezeichnung or "adiabat")
elif typ in ("fest", "fixed", "dirichlet"):
    temperatur = globals().get("temperatur")
    rf = globals().get("rf")
    if temperatur is None or rf is None:
        raise ValueError("Fuer typ='fest' sind 'temperatur' und 'rf' erforderlich")
    bedingung = bnd.FixedBoundary(float(temperatur), float(rf),
                                  name=bezeichnung or "fest")
elif typ in ("aussen", "exterior", "extern"):
    if klima is None:
        raise ValueError("Fuer typ='aussen' muss 'klima' angeschlossen werden")
    bedingung = bnd.exterior_surface(
        klima, sd=sd,
        alpha=float(alpha) if alpha is not None else 17.0,
        wind_factor=float(globals().get("wind_faktor") or 0.0),
        solar_absorptance=float(globals().get("absorption")
                                if globals().get("absorption") is not None else 0.6),
        rain_absorption=float(globals().get("regenanteil")
                              if globals().get("regenanteil") is not None else 0.7),
        name=bezeichnung or "aussen")
elif typ in ("innen", "interior", "intern"):
    if klima is None:
        raise ValueError("Fuer typ='innen' muss 'klima' angeschlossen werden")
    bedingung = bnd.interior_surface(
        klima, sd=sd, alpha=float(alpha) if alpha is not None else 8.0,
        name=bezeichnung or "innen")
else:
    raise ValueError(f"Unbekannter Randtyp '{typ}'. Erlaubt: aussen, innen, "
                     "fest, adiabat")

rand = (selektor, bedingung)
info = f"{selektor.describe()} -> {bedingung.describe()}"
