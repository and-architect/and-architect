"""Adapter zwischen Rhino/Grasshopper und dem Rechenkern.

Das Modul ist so aufgebaut, dass es *auch ohne Rhino* importiert werden kann:
Die Umrechnung von Geometrie in Regionen, die Mesh-Erzeugung und die
Farbverlaeufe sind reines Python und damit testbar. Nur die Funktionen, die
echte Rhino-Objekte erzeugen, benoetigen ``Rhino``/``rhinoscriptsyntax`` und
melden sonst einen verstaendlichen Fehler.

Typischer Ablauf in Grasshopper:

1. Geschlossene Kurven in der XY-Ebene zeichnen (Schnitt durch das Bauteil).
2. Je Kurve ein Material zuordnen -> :func:`region_from_curve`.
3. Aussen- und Innenoberflaeche als Kurve angeben -> :func:`selector_from_curve`.
4. Modell zusammensetzen, rechnen, Ergebnis als farbiges Mesh ausgeben
   -> :func:`result_mesh`.

Die Laengeneinheit des Rhino-Dokuments wird ueber ``unit_scale`` in Meter
umgerechnet (z.B. 0.001 bei Millimeter-Dokumenten). :func:`document_unit_scale`
ermittelt den Faktor in Rhino automatisch.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .boundary import PolylineSelector, Selector
from .grid import Grid2D, Region

Point = Tuple[float, float]

_MISSING_RHINO = (
    "Diese Funktion benoetigt Rhino (RhinoCommon). Sie laeuft nur in Rhino 8/9 "
    "oder Grasshopper, nicht in einer reinen Python-Umgebung."
)


def _rhino_modules():
    try:  # pragma: no cover - nur in Rhino verfuegbar
        import Rhino  # type: ignore
        import Rhino.Geometry as rg  # type: ignore
        return Rhino, rg  # noqa: F401 -- Rhino wird von Aufrufern gebraucht
    except ImportError as error:  # pragma: no cover
        raise RuntimeError(_MISSING_RHINO) from error


def has_rhino() -> bool:
    """``True``, wenn RhinoCommon importierbar ist."""
    try:  # pragma: no cover
        import Rhino  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Geometrie -> Regionen
# ---------------------------------------------------------------------------

def document_unit_scale() -> float:  # pragma: no cover - benoetigt Rhino
    """Faktor, der Dokumenteinheiten in Meter umrechnet."""
    Rhino, _ = _rhino_modules()
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return 1.0
    return float(Rhino.RhinoMath.UnitScale(doc.ModelUnitSystem,
                                           Rhino.UnitSystem.Meters))


def polygon_from_curve(curve, tolerance: float = 0.001, unit_scale: float = 1.0,
                       max_segments: int = 400) -> List[Point]:  # pragma: no cover
    """Geschlossene Kurve in einen Polygonzug ``[(x, y), ...]`` in Meter wandeln.

    Polylinien werden exakt uebernommen, gekruemmte Kurven mit der Toleranz
    ``tolerance`` (Dokumenteinheiten) angenaehert.
    """
    _, rg = _rhino_modules()
    if curve is None:
        raise ValueError("Kurve ist None")
    if isinstance(curve, rg.Brep):
        loops = brep_boundary_curves(curve)
        if not loops:
            raise ValueError("Brep enthaelt keine Randkurve")
        curve = loops[0]

    polyline = None
    ok, candidate = curve.TryGetPolyline()
    if ok:
        polyline = candidate
    else:
        polycurve = curve.ToPolyline(tolerance, tolerance, 0.0, 0.0)
        if polycurve is not None:
            ok, polyline = polycurve.TryGetPolyline()
    if polyline is None:
        # Fallback: gleichmaessig unterteilen
        parameters = curve.DivideByCount(max_segments, True) or []
        points = [curve.PointAt(t) for t in parameters]
    else:
        points = [polyline[k] for k in range(polyline.Count)]

    coordinates = [(float(p.X) * unit_scale, float(p.Y) * unit_scale) for p in points]
    if len(coordinates) > 1 and abs(coordinates[0][0] - coordinates[-1][0]) < 1e-12 \
            and abs(coordinates[0][1] - coordinates[-1][1]) < 1e-12:
        coordinates = coordinates[:-1]
    if len(coordinates) < 3:
        raise ValueError("Kurve ergibt kein Polygon mit mindestens drei Punkten")
    return coordinates


def brep_boundary_curves(brep) -> List:  # pragma: no cover - benoetigt Rhino
    """Aussen- und Innenkonturen einer planaren Flaeche als Kurven."""
    _, rg = _rhino_modules()
    curves = []
    for face in brep.Faces:
        for loop in face.Loops:
            curve = loop.To3dCurve()
            if curve is not None:
                curves.append(curve)
    return curves


def region_from_curve(curve, material: str, holes: Optional[Sequence] = None,
                      priority: int = 0, name: str = "", tolerance: float = 0.001,
                      unit_scale: float = 1.0, initial_rh: Optional[float] = None,
                      initial_temperature: Optional[float] = None
                      ) -> Region:  # pragma: no cover - benoetigt Rhino
    """Region aus einer geschlossenen Rhino-Kurve erzeugen."""
    polygon = polygon_from_curve(curve, tolerance, unit_scale)
    hole_polygons = [polygon_from_curve(h, tolerance, unit_scale) for h in (holes or [])]
    return Region(material=material, polygon=polygon, holes=hole_polygons,
                  priority=priority, name=name, initial_rh=initial_rh,
                  initial_temperature=initial_temperature)


def polyline_points(curve, tolerance: float = 0.001, unit_scale: float = 1.0,
                    max_segments: int = 200) -> List[Point]:  # pragma: no cover
    """Offene oder geschlossene Kurve als Punktliste (fuer Selektoren)."""
    _, rg = _rhino_modules()
    ok, polyline = curve.TryGetPolyline()
    if ok:
        points = [polyline[k] for k in range(polyline.Count)]
    else:
        parameters = curve.DivideByCount(max_segments, True) or []
        points = [curve.PointAt(t) for t in parameters]
    return [(float(p.X) * unit_scale, float(p.Y) * unit_scale) for p in points]


def selector_from_curve(curve, tolerance: float = 0.005, unit_scale: float = 1.0,
                        sides: Optional[Sequence[str]] = None
                        ) -> Selector:  # pragma: no cover - benoetigt Rhino
    """Randbedingungs-Selektor aus einer Rhino-Kurve.

    ``tolerance`` ist der maximale Abstand [m] zwischen Kurve und
    Flaechenmittelpunkt -- er sollte etwa der halben kleinsten Zellgroesse
    entsprechen.
    """
    return PolylineSelector(polyline_points(curve, unit_scale=unit_scale),
                            tolerance=tolerance, sides=sides)


# ---------------------------------------------------------------------------
# Farbverlaeufe (reines Python, testbar)
# ---------------------------------------------------------------------------

PALETTES: Dict[str, Tuple[Tuple[int, int, int], ...]] = {
    # blau -> cyan -> gruen -> gelb -> rot (Temperatur)
    "temperatur": ((0, 32, 160), (0, 160, 220), (0, 170, 80), (245, 210, 0), (200, 30, 20)),
    # trocken (hell) -> feucht (blau) -> gesaettigt (violett)
    "feuchte": ((250, 250, 235), (150, 210, 230), (40, 130, 200), (25, 60, 150),
                (90, 20, 120)),
    # Wassergehalt: grau -> tuerkis -> dunkelblau
    "wasser": ((235, 235, 235), (140, 200, 190), (40, 140, 160), (20, 70, 120)),
    "graustufen": ((20, 20, 20), (245, 245, 245)),
}

QUANTITY_PALETTE = {
    "temperature": "temperatur",
    "rh": "feuchte",
    "water_content": "wasser",
    "moisture_mass_percent": "wasser",
    "vapour_pressure": "feuchte",
}


def colour_ramp(values: Sequence[float], v_min: Optional[float] = None,
                v_max: Optional[float] = None, palette: str = "temperatur"
                ) -> List[Tuple[int, int, int]]:
    """Werte auf RGB-Farben abbilden.

    ``NaN``-Werte (inaktive Zellen) erhalten ein neutrales Grau.
    """
    stops = PALETTES.get(palette)
    if stops is None:
        raise KeyError(f"Unbekannte Farbpalette '{palette}'. Verfuegbar: "
                       f"{sorted(PALETTES)}")
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    if v_min is None:
        v_min = float(finite.min()) if finite.size else 0.0
    if v_max is None:
        v_max = float(finite.max()) if finite.size else 1.0
    span = float(v_max) - float(v_min)
    if abs(span) < 1e-12:
        span = 1.0

    positions = np.linspace(0.0, 1.0, len(stops))
    reds = np.asarray([s[0] for s in stops], dtype=float)
    greens = np.asarray([s[1] for s in stops], dtype=float)
    blues = np.asarray([s[2] for s in stops], dtype=float)

    normalised = np.clip((array - float(v_min)) / span, 0.0, 1.0)
    colours: List[Tuple[int, int, int]] = []
    for k, value in enumerate(normalised):
        if not np.isfinite(array[k]):
            colours.append((190, 190, 190))
            continue
        colours.append((
            int(round(float(np.interp(value, positions, reds)))),
            int(round(float(np.interp(value, positions, greens)))),
            int(round(float(np.interp(value, positions, blues)))),
        ))
    return colours


def legend_steps(v_min: float, v_max: float, count: int = 6) -> List[float]:
    """Gleichmaessige Stuetzwerte fuer eine Legende."""
    if count < 2:
        raise ValueError("count muss >= 2 sein")
    return [float(v_min + (v_max - v_min) * k / (count - 1)) for k in range(count)]


# ---------------------------------------------------------------------------
# Mesh-Daten (reines Python, testbar)
# ---------------------------------------------------------------------------

def flat_mesh_data(grid: Grid2D, values: Sequence[float], z: float = 0.0,
                   unit_scale: float = 1.0
                   ) -> Tuple[List[Tuple[float, float, float]],
                              List[Tuple[int, int, int, int]], List[float]]:
    """Mesh mit *je Zelle eigenen* Eckpunkten (flache Faerbung).

    Rueckgabe ``(vertices, quads, cell_values)``. Jede aktive Zelle liefert
    vier eigene Eckpunkte, damit die Zellfarbe konstant bleibt und die
    Finite-Volumen-Struktur sichtbar ist. ``unit_scale`` rechnet Meter in
    Dokumenteinheiten zurueck (z.B. 1000 fuer Millimeter).
    """
    field = np.asarray(values, dtype=float)
    if field.shape == grid.shape:
        cells = [(j, i) for j in range(grid.ny) for i in range(grid.nx)
                 if grid.active[j, i]]
        cell_values = [float(field[j, i]) for j, i in cells]
    else:
        _, _, cells = grid.mesh_data()
        if len(field) != len(cells):
            raise ValueError(f"{len(field)} Werte passen nicht zu {len(cells)} "
                             "aktiven Zellen")
        cell_values = [float(v) for v in field]

    vertices: List[Tuple[float, float, float]] = []
    quads: List[Tuple[int, int, int, int]] = []
    for j, i in cells:
        x0 = float(grid.x_edges[i]) * unit_scale
        x1 = float(grid.x_edges[i + 1]) * unit_scale
        y0 = float(grid.y_edges[j]) * unit_scale
        y1 = float(grid.y_edges[j + 1]) * unit_scale
        base = len(vertices)
        vertices.extend([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)])
        quads.append((base, base + 1, base + 2, base + 3))
    return vertices, quads, cell_values


def result_mesh(grid: Grid2D, values: Sequence[float], v_min: Optional[float] = None,
                v_max: Optional[float] = None, palette: str = "temperatur",
                z: float = 0.0, unit_scale: float = 1.0):  # pragma: no cover
    """Rhino-Mesh der Ergebniswerte mit Zellfarben."""
    _, rg = _rhino_modules()
    from System.Drawing import Color  # type: ignore

    vertices, quads, cell_values = flat_mesh_data(grid, values, z=z,
                                                  unit_scale=unit_scale)
    colours = colour_ramp(cell_values, v_min, v_max, palette)
    mesh = rg.Mesh()
    for x, y, zz in vertices:
        mesh.Vertices.Add(x, y, zz)
    for quad in quads:
        mesh.Faces.AddFace(*quad)
    for index, colour in enumerate(colours):
        for _ in range(4):
            mesh.VertexColors.Add(Color.FromArgb(*colour))
        del index
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


def material_mesh(grid: Grid2D, z: float = 0.0, unit_scale: float = 1.0
                  ):  # pragma: no cover - benoetigt Rhino
    """Mesh, das die Materialverteilung des Gitters farbig zeigt."""
    ids = grid.material_id.astype(float)
    ids[~grid.active] = np.nan
    return result_mesh(grid, ids, v_min=0.0,
                       v_max=max(len(grid.material_names) - 1, 1),
                       palette="temperatur", z=z, unit_scale=unit_scale)


def grid_lines(grid: Grid2D, z: float = 0.0, unit_scale: float = 1.0
               ) -> List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    """Gitterlinien als Punktpaare (zur Kontrolle der Diskretisierung)."""
    x0, y0, x1, y1 = grid.bounds()
    lines = []
    for x in grid.x_edges:
        lines.append(((float(x) * unit_scale, y0 * unit_scale, z),
                      (float(x) * unit_scale, y1 * unit_scale, z)))
    for y in grid.y_edges:
        lines.append(((x0 * unit_scale, float(y) * unit_scale, z),
                      (x1 * unit_scale, float(y) * unit_scale, z)))
    return lines


def isotherm_points(grid: Grid2D, values: Sequence[float], level: float
                    ) -> List[Point]:
    """Punkte einer Isolinie (Isotherme, Isohygre) zum Wert ``level``.

    Gesucht werden die Nulldurchgaenge von ``values - level`` zwischen
    benachbarten Zellmittelpunkten -- in x- und in y-Richtung -- und linear
    interpoliert. Die Punkte lassen sich in Grasshopper zu einer Kurve
    verbinden (z.B. ueber "Polyline through points" bzw. "Nurbs Curve").
    """
    field = np.asarray(values, dtype=float)
    if field.shape != grid.shape:
        raise ValueError("values muss die Form des Gitters haben")
    level = float(level)
    xc, yc = grid.xc, grid.yc
    points: List[Point] = []

    def crossing(a: float, b: float) -> Optional[float]:
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
        if (a - level) * (b - level) > 0.0 or a == b:
            return None
        return (level - a) / (b - a)

    for j in range(grid.ny):
        for i in range(grid.nx - 1):
            if not (grid.active[j, i] and grid.active[j, i + 1]):
                continue
            t = crossing(field[j, i], field[j, i + 1])
            if t is not None:
                points.append((float(xc[i] + t * (xc[i + 1] - xc[i])), float(yc[j])))
    for j in range(grid.ny - 1):
        for i in range(grid.nx):
            if not (grid.active[j, i] and grid.active[j + 1, i]):
                continue
            t = crossing(field[j, i], field[j + 1, i])
            if t is not None:
                points.append((float(xc[i]), float(yc[j] + t * (yc[j + 1] - yc[j]))))
    return points


# ---------------------------------------------------------------------------
# Zustandsspeicher fuer Grasshopper
# ---------------------------------------------------------------------------

def sticky_set(key: str, value) -> None:  # pragma: no cover - benoetigt Rhino
    """Wert im Rhino-Dokumentspeicher (``scriptcontext.sticky``) ablegen."""
    import scriptcontext  # type: ignore
    scriptcontext.sticky[f"wufi2d.{key}"] = value


def sticky_get(key: str, default=None):  # pragma: no cover - benoetigt Rhino
    """Wert aus dem Rhino-Dokumentspeicher lesen."""
    try:
        import scriptcontext  # type: ignore
    except ImportError:
        return default
    return scriptcontext.sticky.get(f"wufi2d.{key}", default)
