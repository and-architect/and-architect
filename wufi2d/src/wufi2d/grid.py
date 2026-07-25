"""Rechengitter fuer die 2D-Berechnung.

Wie in WUFI 2D wird ein *strukturiertes, nicht-uniformes Rechteckgitter*
verwendet. Die Geometrie wird ueber achsparallele oder beliebige Polygone
("Regionen") beschrieben, denen jeweils ein Material zugeordnet ist. Zellen,
die in keiner Region liegen, sind inaktiv -- damit lassen sich auch
L-foermige Bauteile, Auskragungen und Aussparungen (Waermebruecken)
abbilden.

Das Modul ist bewusst frei von Rhino-Abhaengigkeiten: Regionen sind reine
Punktlisten. Der Rhino-/Grasshopper-Adapter wandelt Kurven lediglich in
Polygone um.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

Point = Tuple[float, float]

SIDES = ("left", "right", "bottom", "top")

_NORMALS = {
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
    "bottom": (0.0, -1.0),
    "top": (0.0, 1.0),
}


class GridError(ValueError):
    """Fehler bei der Gittererzeugung."""


# ---------------------------------------------------------------------------
# Geometrie-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _close_loop(points: Sequence[Point]) -> np.ndarray:
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise GridError("Polygon muss eine Liste von (x, y)-Punkten sein")
    if len(pts) < 3:
        raise GridError("Polygon braucht mindestens 3 Punkte")
    if np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    if len(pts) < 3:
        raise GridError("Polygon braucht mindestens 3 verschiedene Punkte")
    return pts


def points_in_polygon(x, y, polygon: Sequence[Point]) -> np.ndarray:
    """Vektorisierter Punkt-in-Polygon-Test (Ray-Casting, ungerade Anzahl).

    ``x`` und ``y`` sind gleich geformte Arrays. Punkte genau auf der Kante
    gelten als innen liegend, sofern sie durch die Strahlzaehlung erfasst
    werden -- fuer Zellmittelpunkte ist das unkritisch.
    """
    pts = _close_loop(polygon)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    inside = np.zeros(x.shape, dtype=bool)
    x0, y0 = pts[:, 0], pts[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    for ax, ay, bx, by in zip(x0, y0, x1, y1):
        if ay == by:
            continue
        crosses = (y > np.minimum(ay, by)) & (y <= np.maximum(ay, by))
        with np.errstate(divide="ignore", invalid="ignore"):
            x_cross = ax + (y - ay) * (bx - ax) / (by - ay)
        inside ^= crosses & (x < x_cross)
    return inside


def polygon_area(polygon: Sequence[Point]) -> float:
    """Flaeche eines Polygons [m2] (Gauss'sche Trapezformel, Betrag)."""
    pts = _close_loop(polygon)
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def rectangle(x0: float, y0: float, width: float, height: float) -> List[Point]:
    """Achsparalleles Rechteck als Polygon."""
    return [(x0, y0), (x0 + width, y0), (x0 + width, y0 + height), (x0, y0 + height)]


# ---------------------------------------------------------------------------
# Regionen
# ---------------------------------------------------------------------------

@dataclass
class Region:
    """Materialbereich in der Schnittebene.

    Attribute
    ---------
    material:
        Name des Materials (muss in der Materialbibliothek vorhanden sein).
    polygon:
        Aussenkontur als Punktliste ``[(x, y), ...]`` in Metern.
    holes:
        Optionale Innenkonturen (Aussparungen) als Liste von Punktlisten.
    priority:
        Bei Ueberlappung gewinnt die Region mit der hoeheren Prioritaet;
        bei Gleichstand die spaeter definierte.
    name:
        Freie Bezeichnung (z.B. "Daemmung aussen").
    initial_rh / initial_temperature:
        Optionale, regionsweise Anfangsbedingungen.
    """

    material: str
    polygon: List[Point]
    holes: List[List[Point]] = field(default_factory=list)
    priority: int = 0
    name: str = ""
    initial_rh: Optional[float] = None
    initial_temperature: Optional[float] = None

    def contains(self, x, y) -> np.ndarray:
        inside = points_in_polygon(x, y, self.polygon)
        for hole in self.holes:
            inside &= ~points_in_polygon(x, y, hole)
        return inside

    def bounds(self) -> Tuple[float, float, float, float]:
        pts = _close_loop(self.polygon)
        return (float(pts[:, 0].min()), float(pts[:, 1].min()),
                float(pts[:, 0].max()), float(pts[:, 1].max()))

    def coordinates(self) -> Tuple[List[float], List[float]]:
        """Alle x- und y-Koordinaten (Aussen- und Innenkonturen)."""
        xs: List[float] = []
        ys: List[float] = []
        for loop in [self.polygon, *self.holes]:
            pts = _close_loop(loop)
            xs.extend(pts[:, 0].tolist())
            ys.extend(pts[:, 1].tolist())
        return xs, ys

    def area(self) -> float:
        return polygon_area(self.polygon) - sum(polygon_area(h) for h in self.holes)

    def to_dict(self) -> Dict:
        data = {
            "material": self.material,
            "polygon": [[float(p[0]), float(p[1])] for p in self.polygon],
        }
        if self.holes:
            data["holes"] = [[[float(p[0]), float(p[1])] for p in h] for h in self.holes]
        if self.priority:
            data["priority"] = self.priority
        if self.name:
            data["name"] = self.name
        if self.initial_rh is not None:
            data["initial_rh"] = self.initial_rh
        if self.initial_temperature is not None:
            data["initial_temperature"] = self.initial_temperature
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "Region":
        return cls(
            material=data["material"],
            polygon=[tuple(p) for p in data["polygon"]],
            holes=[[tuple(p) for p in h] for h in data.get("holes", [])],
            priority=int(data.get("priority", 0)),
            name=data.get("name", ""),
            initial_rh=data.get("initial_rh"),
            initial_temperature=data.get("initial_temperature"),
        )


# ---------------------------------------------------------------------------
# Randflaechen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Face:
    """Freiliegende Zellflaeche am Rand des aktiven Gebiets."""

    i: int
    j: int
    side: str
    x: float
    y: float
    length: float

    @property
    def normal(self) -> Tuple[float, float]:
        return _NORMALS[self.side]

    @property
    def midpoint(self) -> Point:
        return (self.x, self.y)


# ---------------------------------------------------------------------------
# Gitter
# ---------------------------------------------------------------------------

@dataclass
class Grid2D:
    """Strukturiertes, nicht-uniformes Rechteckgitter mit Materialzuordnung.

    Indexkonvention: ``material_id[j, i]`` mit ``i`` = Spalte (x-Richtung),
    ``j`` = Zeile (y-Richtung). ``material_id < 0`` bedeutet inaktive Zelle.
    """

    x_edges: np.ndarray
    y_edges: np.ndarray
    material_id: np.ndarray
    material_names: List[str]
    depth: float = 1.0
    region_index: Optional[np.ndarray] = None

    def __post_init__(self) -> None:
        self.x_edges = np.asarray(self.x_edges, dtype=float)
        self.y_edges = np.asarray(self.y_edges, dtype=float)
        self.material_id = np.asarray(self.material_id, dtype=int)
        if self.material_id.shape != (self.ny, self.nx):
            raise GridError(
                f"material_id hat Form {self.material_id.shape}, erwartet "
                f"{(self.ny, self.nx)}"
            )
        if np.any(np.diff(self.x_edges) <= 0) or np.any(np.diff(self.y_edges) <= 0):
            raise GridError("Gitterlinien muessen streng monoton steigen")
        if not self.active.any():
            raise GridError("Gitter enthaelt keine aktive Zelle")

    # -- Basisgroessen --------------------------------------------------
    @property
    def nx(self) -> int:
        return len(self.x_edges) - 1

    @property
    def ny(self) -> int:
        return len(self.y_edges) - 1

    @property
    def shape(self) -> Tuple[int, int]:
        return (self.ny, self.nx)

    @property
    def dx(self) -> np.ndarray:
        """Zellbreiten [m], Form ``(nx,)``."""
        return np.diff(self.x_edges)

    @property
    def dy(self) -> np.ndarray:
        """Zellhoehen [m], Form ``(ny,)``."""
        return np.diff(self.y_edges)

    @property
    def xc(self) -> np.ndarray:
        return 0.5 * (self.x_edges[:-1] + self.x_edges[1:])

    @property
    def yc(self) -> np.ndarray:
        return 0.5 * (self.y_edges[:-1] + self.y_edges[1:])

    @property
    def active(self) -> np.ndarray:
        return self.material_id >= 0

    @property
    def n_active(self) -> int:
        return int(self.active.sum())

    @property
    def cell_volume(self) -> np.ndarray:
        """Zellvolumen [m3] (Flaeche x Bauteiltiefe), Form ``(ny, nx)``."""
        return np.outer(self.dy, self.dx) * self.depth

    def cell_centers(self) -> Tuple[np.ndarray, np.ndarray]:
        return np.meshgrid(self.xc, self.yc)

    def bounds(self) -> Tuple[float, float, float, float]:
        return (float(self.x_edges[0]), float(self.y_edges[0]),
                float(self.x_edges[-1]), float(self.y_edges[-1]))

    def material_of(self, j: int, i: int) -> Optional[str]:
        mid = int(self.material_id[j, i])
        return self.material_names[mid] if mid >= 0 else None

    def cell_at(self, x: float, y: float) -> Optional[Tuple[int, int]]:
        """Zellindex ``(j, i)`` fuer einen Punkt, oder ``None``."""
        if not (self.x_edges[0] <= x <= self.x_edges[-1]):
            return None
        if not (self.y_edges[0] <= y <= self.y_edges[-1]):
            return None
        i = int(np.clip(np.searchsorted(self.x_edges, x, side="right") - 1, 0, self.nx - 1))
        j = int(np.clip(np.searchsorted(self.y_edges, y, side="right") - 1, 0, self.ny - 1))
        return (j, i) if self.active[j, i] else None

    def material_property_array(self, materials, getter) -> np.ndarray:
        """Materialkonstante als Feld ueber alle Zellen.

        ``materials`` ist ein Mapping Name -> Material, ``getter`` eine
        Funktion, die aus einem Material den Wert liefert. Inaktive Zellen
        erhalten 0.
        """
        values = np.zeros(self.shape, dtype=float)
        for mid, name in enumerate(self.material_names):
            mask = self.material_id == mid
            if mask.any():
                values[mask] = float(getter(materials[name]))
        return values

    # -- Randflaechen ---------------------------------------------------
    def exposed_faces(self) -> List[Face]:
        """Alle freiliegenden Zellflaechen (Gebietsrand und Aussparungen)."""
        faces: List[Face] = []
        active = self.active
        dx, dy = self.dx, self.dy
        xc, yc = self.xc, self.yc
        for j in range(self.ny):
            for i in range(self.nx):
                if not active[j, i]:
                    continue
                if i == 0 or not active[j, i - 1]:
                    faces.append(Face(i, j, "left", self.x_edges[i], yc[j], dy[j]))
                if i == self.nx - 1 or not active[j, i + 1]:
                    faces.append(Face(i, j, "right", self.x_edges[i + 1], yc[j], dy[j]))
                if j == 0 or not active[j - 1, i]:
                    faces.append(Face(i, j, "bottom", xc[i], self.y_edges[j], dx[i]))
                if j == self.ny - 1 or not active[j + 1, i]:
                    faces.append(Face(i, j, "top", xc[i], self.y_edges[j + 1], dx[i]))
        return faces

    # -- Ausgabe / Export -----------------------------------------------
    def cell_polygon(self, j: int, i: int) -> List[Point]:
        return rectangle(self.x_edges[i], self.y_edges[j], self.dx[i], self.dy[j])

    def mesh_data(self) -> Tuple[List[Point], List[Tuple[int, int, int, int]], List[Tuple[int, int]]]:
        """Quad-Mesh der aktiven Zellen.

        Rueckgabe: ``(vertices, quads, cells)`` -- ``vertices`` sind
        ``(x, y)``-Punkte des vollen Gitterknotenfelds, ``quads`` enthaelt je
        aktive Zelle vier Knotenindizes, ``cells`` die zugehoerigen
        ``(j, i)``-Indizes (fuer die Zuordnung von Ergebniswerten).
        """
        nxv = self.nx + 1
        vertices = [(float(x), float(y)) for y in self.y_edges for x in self.x_edges]
        quads: List[Tuple[int, int, int, int]] = []
        cells: List[Tuple[int, int]] = []
        for j in range(self.ny):
            for i in range(self.nx):
                if not self.active[j, i]:
                    continue
                v0 = j * nxv + i
                quads.append((v0, v0 + 1, v0 + nxv + 1, v0 + nxv))
                cells.append((j, i))
        return vertices, quads, cells

    def summary(self) -> str:
        x0, y0, x1, y1 = self.bounds()
        dx, dy = self.dx, self.dy
        lines = [
            f"Gitter: {self.nx} x {self.ny} Zellen, davon {self.n_active} aktiv",
            f"Ausdehnung: {x1 - x0:.3f} m x {y1 - y0:.3f} m, Tiefe {self.depth:.3f} m",
            f"Zellgroesse x: {dx.min() * 1000:.2f} - {dx.max() * 1000:.2f} mm",
            f"Zellgroesse y: {dy.min() * 1000:.2f} - {dy.max() * 1000:.2f} mm",
        ]
        volumes = self.cell_volume
        for mid, name in enumerate(self.material_names):
            mask = self.material_id == mid
            if mask.any():
                lines.append(f"  {name}: {int(mask.sum())} Zellen, "
                             f"{volumes[mask].sum():.4f} m3")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gittererzeugung
# ---------------------------------------------------------------------------

def graded_spacing(length: float, d_min: float, d_max: float,
                   growth: float = 1.3) -> List[float]:
    """Zellbreiten fuer ein Intervall mit Randverfeinerung.

    Von beiden Enden wachsen die Zellen geometrisch mit ``growth`` von
    ``d_min`` bis maximal ``d_max`` an und treffen sich in der Mitte -- das
    entspricht dem in WUFI ueblichen "expandierenden" Gitter, das die hohen
    Gradienten an Oberflaechen und Materialgrenzen aufloest.

    Die Aufteilung ist exakt spiegelsymmetrisch: eine Haelfte wird aufgebaut
    und gespiegelt. Damit liefern symmetrische Modelle auch symmetrische
    Ergebnisse.
    """
    if length <= 0:
        raise GridError("Intervall-Laenge muss > 0 sein")
    d_min = max(min(d_min, length), 1e-9)
    d_max = max(d_max, d_min)
    if length <= d_min * 1.5:
        return [length]

    half = 0.5 * length
    sizes: List[float] = []
    step = d_min
    total = 0.0
    while total < half - 1e-12:
        current = min(step, d_max, half - total)
        sizes.append(current)
        total += current
        step = current * growth

    # Sehr kleine Restzelle in der Mitte in den Nachbarn einrechnen, damit das
    # Gitter nicht mit einem Sprung von grob auf sehr fein endet.
    if len(sizes) > 1 and sizes[-1] < 0.5 * min(d_min, sizes[-2]):
        rest = sizes.pop()
        sizes[-1] += rest

    full = sizes + sizes[::-1]
    scale = length / sum(full)
    return [s * scale for s in full]


def _merge_coordinates(values: Iterable[float], tol: float) -> List[float]:
    ordered = sorted(float(v) for v in values)
    merged: List[float] = []
    for value in ordered:
        if not merged or value - merged[-1] > tol:
            merged.append(value)
        else:
            merged[-1] = 0.5 * (merged[-1] + value)
    return merged


def _edges_from_breaks(breaks: Sequence[float], d_min: float, d_max: float,
                       growth: float) -> np.ndarray:
    edges = [breaks[0]]
    for a, b in zip(breaks, breaks[1:]):
        for size in graded_spacing(b - a, d_min, d_max, growth):
            edges.append(edges[-1] + size)
        edges[-1] = b  # exakte Lage der Pflicht-Gitterlinie sicherstellen
    return np.asarray(edges, dtype=float)


def build_grid(regions: Sequence[Region],
               materials: Optional[object] = None,
               max_cell: float = 0.02,
               min_cell: float = 0.002,
               growth: float = 1.3,
               extra_x: Sequence[float] = (),
               extra_y: Sequence[float] = (),
               depth: float = 1.0,
               max_cell_y: Optional[float] = None,
               min_cell_y: Optional[float] = None,
               tol: float = 1e-6) -> Grid2D:
    """Rechengitter aus Regionen erzeugen.

    Parameter
    ---------
    regions:
        Materialbereiche. Alle Polygon-Eckpunktkoordinaten werden zu
        Pflicht-Gitterlinien, damit Materialgrenzen exakt auf Zellgrenzen
        liegen (bei achsparalleler Geometrie).
    materials:
        Optionale Materialbibliothek zur Namenspruefung.
    max_cell / min_cell:
        Groesste / kleinste Zellabmessung [m]. ``min_cell`` gilt an
        Materialgrenzen und Oberflaechen.
    growth:
        Wachstumsfaktor des Gitters von den Raendern zur Mitte.
    extra_x / extra_y:
        Zusaetzliche Pflicht-Gitterlinien [m].
    depth:
        Bauteiltiefe senkrecht zur Schnittebene [m]; 2D-Ergebnisse beziehen
        sich damit auf 1 m Bauteillaenge (Standard).
    max_cell_y / min_cell_y:
        Abweichende Zellgroessen in y-Richtung; ohne Angabe gelten
        ``max_cell`` / ``min_cell`` fuer beide Richtungen.
    """
    if not regions:
        raise GridError("Mindestens eine Region wird benoetigt")
    if min_cell <= 0 or max_cell <= 0:
        raise GridError("min_cell und max_cell muessen > 0 sein")
    if min_cell > max_cell:
        min_cell, max_cell = max_cell, min_cell
    if growth <= 1.0:
        raise GridError("growth muss > 1 sein")

    xs: List[float] = list(extra_x)
    ys: List[float] = list(extra_y)
    for region in regions:
        rx, ry = region.coordinates()
        xs.extend(rx)
        ys.extend(ry)

    x_breaks = _merge_coordinates(xs, tol)
    y_breaks = _merge_coordinates(ys, tol)
    if len(x_breaks) < 2 or len(y_breaks) < 2:
        raise GridError("Regionen haben keine Ausdehnung in x- und y-Richtung")

    max_y = max_cell if max_cell_y is None else float(max_cell_y)
    min_y = min_cell if min_cell_y is None else float(min_cell_y)
    if min_y > max_y:
        min_y, max_y = max_y, min_y

    x_edges = _edges_from_breaks(x_breaks, min_cell, max_cell, growth)
    y_edges = _edges_from_breaks(y_breaks, min_y, max_y, growth)

    names: List[str] = []
    for region in regions:
        if region.material not in names:
            names.append(region.material)
    if materials is not None:
        for name in names:
            materials.get(name)  # loest MaterialError aus, wenn unbekannt

    xc = 0.5 * (x_edges[:-1] + x_edges[1:])
    yc = 0.5 * (y_edges[:-1] + y_edges[1:])
    grid_x, grid_y = np.meshgrid(xc, yc)

    material_id = np.full(grid_x.shape, -1, dtype=int)
    region_index = np.full(grid_x.shape, -1, dtype=int)
    order = sorted(range(len(regions)), key=lambda k: (regions[k].priority, k))
    for k in order:
        region = regions[k]
        inside = region.contains(grid_x, grid_y)
        material_id[inside] = names.index(region.material)
        region_index[inside] = k

    if not (material_id >= 0).any():
        raise GridError(
            "Keine Zelle liegt innerhalb einer Region -- Gitter zu grob oder "
            "Polygone fehlerhaft (Reihenfolge/Orientierung der Punkte pruefen)"
        )

    return Grid2D(x_edges=x_edges, y_edges=y_edges, material_id=material_id,
                  material_names=names, depth=depth, region_index=region_index)


def build_layered_grid(layers: Sequence[Tuple[str, float]],
                       height: float = 0.1,
                       max_cell: float = 0.02,
                       min_cell: float = 0.002,
                       growth: float = 1.3,
                       n_rows: int = 1,
                       depth: float = 1.0,
                       materials: Optional[object] = None) -> Grid2D:
    """Gitter fuer einen geschichteten Aufbau (1D-Fall im 2D-Loeser).

    ``layers`` ist eine Liste ``[(Materialname, Dicke [m]), ...]`` von
    aussen nach innen. Die Hoehe wird in ``n_rows`` gleiche Zeilen geteilt;
    die horizontalen Raender sind standardmaessig adiabat/dampfdicht, sodass
    sich ein rein eindimensionaler Fall ergibt.
    """
    if not layers:
        raise GridError("Mindestens eine Schicht wird benoetigt")
    regions: List[Region] = []
    x = 0.0
    for name, thickness in layers:
        if thickness <= 0:
            raise GridError(f"Schichtdicke von '{name}' muss > 0 sein")
        regions.append(Region(material=name, polygon=rectangle(x, 0.0, thickness, height),
                              name=name))
        x += thickness
    row_height = height / max(int(n_rows), 1)
    return build_grid(regions, materials=materials, max_cell=max_cell,
                      min_cell=min_cell, growth=growth,
                      extra_y=np.linspace(0.0, height, int(n_rows) + 1).tolist(),
                      max_cell_y=row_height, min_cell_y=row_height,
                      depth=depth)
