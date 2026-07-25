"""wufi2d | 01 Setup -- Pfad setzen und Materialdatenbank anzeigen.

Grasshopper-Skriptkomponente (Rhino 8/9, Python 3).

Eingaenge (im Komponenten-Editor anlegen)
-----------------------------------------
pfad       str   Item    Pfad zum Ordner ``wufi2d/src`` dieses Repositorys
filter     str   Item    optional: Kategorie oder Namensteil zum Filtern

Ausgaenge
---------
info          str   Versions- und Statusmeldung
materialien   str   Liste der verfuegbaren Materialnamen
kennwerte     str   Kurzbeschreibung je Material

Die Komponente legt den Pfad in ``scriptcontext.sticky`` ab. Alle weiteren
Komponenten finden das Paket dann ohne erneute Pfadangabe -- sie muessen aber
*nach* dieser Komponente ausgefuehrt werden (Datenfluss ueber ``info``
verbinden oder die Komponente einfach im gleichen Dokument platzieren).
"""

# r: numpy

import os
import sys

import scriptcontext

STICKY_KEY = "wufi2d.pfad"


def _bootstrap(explicit_path):
    """wufi2d importierbar machen: expliziter Pfad, Sticky oder Umgebung."""
    candidates = [explicit_path,
                  scriptcontext.sticky.get(STICKY_KEY),
                  os.environ.get("WUFI2D_PATH")]
    for candidate in candidates:
        if not candidate:
            continue
        candidate = str(candidate)
        if not os.path.isdir(candidate):
            continue
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
    raise RuntimeError(
        "wufi2d nicht gefunden. Bitte den Pfad zum Ordner 'wufi2d/src' "
        "(oder zum Repository-Ordner 'wufi2d') am Eingang 'pfad' angeben.")


root = _bootstrap(globals().get("pfad"))

import wufi2d  # noqa: E402
from wufi2d.linalg import HAS_SCIPY  # noqa: E402

library = wufi2d.default_library()
suchbegriff = (globals().get("filter") or "").strip().lower()

namen = []
for kategorie, eintraege in library.by_category().items():
    for name in eintraege:
        if not suchbegriff or suchbegriff in name.lower() or suchbegriff in kategorie.lower():
            namen.append(name)

materialien = namen
kennwerte = [library.get(name).describe() for name in namen]
info = "\n".join([
    f"wufi2d {wufi2d.__version__} geladen aus {root}",
    f"Python {sys.version.split()[0]}, SciPy: {'ja' if HAS_SCIPY else 'nein (NumPy-Fallback)'}",
    f"{len(library)} Materialien in der Richtwert-Datenbank, {len(namen)} angezeigt",
    "Hinweis: Richtwerte aus der Literatur, keine geprueften Messdaten.",
])
