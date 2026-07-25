"""wufi2d | gemeinsamer Kopf fuer alle Grasshopper-Komponenten.

Dieser Block steht am Anfang jeder Komponente. Er macht das Paket
importierbar -- ueber den Eingang ``pfad``, den Sticky-Speicher (von
``01_Setup``) oder die Umgebungsvariable ``WUFI2D_PATH``.

Nicht als eigene Komponente verwenden; nur zum Nachlesen bzw. Kopieren.
"""

# r: numpy

import os
import sys

import scriptcontext

STICKY_KEY = "wufi2d.pfad"


def bootstrap(explicit_path=None):
    """Pfad zum Paket ermitteln, in ``sys.path`` eintragen und merken."""
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
        "wufi2d nicht gefunden. Bitte zuerst die Komponente '01 Setup' mit dem "
        "Pfad zum Ordner 'wufi2d/src' ausfuehren oder den Pfad direkt am "
        "Eingang 'pfad' angeben.")


def as_list(value):
    """Eingang robust in eine Liste wandeln (Item- oder List-Access)."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v is not None]
    return [value]


def first(value, default=None):
    """Ersten Wert eines Eingangs liefern (oder ``default``)."""
    items = as_list(value)
    return items[0] if items else default
