"""wufi2d | 02 Region -- Kurven mit Material belegen.

Grasshopper-Skriptkomponente (Rhino 8/9, Python 3).

Eingaenge
---------
kurven      Curve  List   geschlossene Kurven in der XY-Ebene (Bauteilschnitt)
material    str    List   Materialname je Kurve (oder ein Name fuer alle)
loecher     Curve  List   optional: Aussparungen (werden allen Kurven abgezogen,
                          die sie umschliessen)
prioritaet  int    List   optional: bei Ueberlappung gewinnt der hoehere Wert
start_rf    float  List   optional: Anfangsfeuchte (0..1) je Region
start_temp  float  List   optional: Anfangstemperatur [degC] je Region
pfad        str    Item   optional: Pfad zu 'wufi2d/src' (siehe 01 Setup)

Ausgaenge
---------
regionen    Region-Objekte fuer die Modell-Komponente
info        Zusammenfassung (Flaeche, Material, Ausdehnung)

Hinweise
--------
* Die Kurven muessen geschlossen und in der XY-Ebene liegen. Der Schnitt wird
  als "1 m Bauteiltiefe" gerechnet (2D-Rechnung je Meter Bauteillaenge).
* Millimeter-Dokumente werden automatisch in Meter umgerechnet.
* Achsparallele Rechtecke sind ideal: ihre Kanten werden zu Gitterlinien.
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

from wufi2d import default_library  # noqa: E402
from wufi2d.rhino import document_unit_scale, polygon_from_curve, region_from_curve  # noqa: E402

kurven = _as_list(globals().get("kurven"))
namen = _as_list(globals().get("material"))
loecher_kurven = _as_list(globals().get("loecher"))
prioritaeten = _as_list(globals().get("prioritaet"))
start_feuchte = _as_list(globals().get("start_rf"))
start_temperatur = _as_list(globals().get("start_temp"))

if not kurven:
    regionen = []
    info = "Keine Kurve angeschlossen."
elif not namen:
    regionen = []
    info = ("Kein Material angegeben. Verfuegbare Namen liefert die Komponente "
            "'01 Setup'.")
else:
    library = default_library()
    scale = document_unit_scale()

    def _pick(values, index, default=None):
        if not values:
            return default
        return values[index] if index < len(values) else values[-1]

    # Aussparungen den umschliessenden Regionen zuordnen
    loch_polygone = [polygon_from_curve(c, unit_scale=scale) for c in loecher_kurven]

    regionen = []
    zeilen = []
    for index, kurve in enumerate(kurven):
        name = str(_pick(namen, index))
        library.get(name)  # prueft den Namen und meldet sonst klar
        aussen = polygon_from_curve(kurve, unit_scale=scale)
        from wufi2d.grid import points_in_polygon
        eigene_loecher = []
        for loch in loch_polygone:
            mittel_x = sum(p[0] for p in loch) / len(loch)
            mittel_y = sum(p[1] for p in loch) / len(loch)
            if bool(points_in_polygon([mittel_x], [mittel_y], aussen)[0]):
                eigene_loecher.append(loch)

        region = region_from_curve(
            kurve, name, priority=int(_pick(prioritaeten, index, 0) or 0),
            name=f"{name} #{index + 1}", unit_scale=scale,
            initial_rh=_pick(start_feuchte, index, None),
            initial_temperature=_pick(start_temperatur, index, None))
        region.holes = eigene_loecher
        regionen.append(region)

        x0, y0, x1, y1 = region.bounds()
        zeilen.append(f"{region.name}: {region.area() * 1e4:.1f} cm2, "
                      f"{(x1 - x0) * 1000:.0f} x {(y1 - y0) * 1000:.0f} mm"
                      + (f", {len(eigene_loecher)} Aussparung(en)"
                         if eigene_loecher else ""))

    gesamt = sum(r.area() for r in regionen)
    info = "\n".join(zeilen + [f"Summe: {gesamt * 1e4:.1f} cm2 "
                               f"({len(regionen)} Regionen)"])
