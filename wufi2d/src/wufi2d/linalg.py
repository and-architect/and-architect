"""Loeser fuer das 5-Punkt-Gleichungssystem des strukturierten Gitters.

Die Diskretisierung liefert je Zelle eine Gleichung der Form::

    aP*x[j,i] - aW*x[j,i-1] - aE*x[j,i+1] - aS*x[j-1,i] - aN*x[j+1,i] = b[j,i]

Die Koeffizienten werden als 2D-Arrays uebergeben. Inaktive Zellen werden
ueber die Maske ``active`` ausgeschlossen.

Bevorzugt wird ein direkter Sparse-Loeser (SciPy). Ist SciPy nicht verfuegbar
-- z.B. in einer schlanken Rhino-Python-Umgebung -- wird automatisch auf ein
SOR-Verfahren mit Schachbrett-Aktualisierung umgeschaltet, das nur NumPy
benoetigt.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

try:  # pragma: no cover - abhaengig von der Umgebung
    from scipy.sparse import csr_matrix
    from scipy.sparse.linalg import spsolve

    HAS_SCIPY = True
except Exception:  # pragma: no cover
    HAS_SCIPY = False


class ConvergenceError(RuntimeError):
    """Der iterative Loeser hat die Toleranz nicht erreicht."""


def neighbour_sum(x: np.ndarray, aW: np.ndarray, aE: np.ndarray,
                  aS: np.ndarray, aN: np.ndarray) -> np.ndarray:
    """Summe der Nachbarbeitraege ``aW*x_W + aE*x_E + aS*x_S + aN*x_N``."""
    total = np.zeros_like(x)
    total[:, 1:] += aW[:, 1:] * x[:, :-1]
    total[:, :-1] += aE[:, :-1] * x[:, 1:]
    total[1:, :] += aS[1:, :] * x[:-1, :]
    total[:-1, :] += aN[:-1, :] * x[1:, :]
    return total


def residual(x: np.ndarray, aP: np.ndarray, aW: np.ndarray, aE: np.ndarray,
             aS: np.ndarray, aN: np.ndarray, b: np.ndarray,
             active: np.ndarray) -> np.ndarray:
    """Residuum ``b - (aP*x - Nachbarbeitraege)`` auf den aktiven Zellen."""
    r = b - (aP * x - neighbour_sum(x, aW, aE, aS, aN))
    return np.where(active, r, 0.0)


def solve_five_point(aP: np.ndarray, aW: np.ndarray, aE: np.ndarray,
                     aS: np.ndarray, aN: np.ndarray, b: np.ndarray,
                     active: np.ndarray, x0: Optional[np.ndarray] = None,
                     tol: float = 1e-10, max_iter: int = 5000,
                     omega: float = 1.6,
                     use_scipy: Optional[bool] = None) -> Tuple[np.ndarray, int]:
    """Gleichungssystem loesen.

    Rueckgabe ``(x, iterationen)`` -- bei direkter Loesung ist
    ``iterationen = 0``.
    """
    aP = np.asarray(aP, dtype=float)
    if np.any(active & (aP <= 0.0)):
        raise ConvergenceError(
            "Hauptdiagonale enthaelt nichtpositive Werte -- Diskretisierung pruefen")

    prefer_scipy = HAS_SCIPY if use_scipy is None else (use_scipy and HAS_SCIPY)
    if prefer_scipy:
        return _solve_direct(aP, aW, aE, aS, aN, b, active), 0
    return _solve_sor(aP, aW, aE, aS, aN, b, active, x0, tol, max_iter, omega)


def _solve_direct(aP, aW, aE, aS, aN, b, active):  # pragma: no cover - SciPy-Pfad
    ny, nx = aP.shape
    index = np.full((ny, nx), -1, dtype=np.int64)
    index[active] = np.arange(int(active.sum()))
    n = int(active.sum())

    rows = [index[active]]
    cols = [index[active]]
    data = [aP[active]]

    def add_link(mask, source_slice, target_slice, coefficients):
        """Kopplung von ``source`` zu ``target`` mit ``-coefficients``."""
        sel = mask & active[source_slice] & active[target_slice]
        if not sel.any():
            return
        rows.append(index[source_slice][sel])
        cols.append(index[target_slice][sel])
        data.append(-coefficients[source_slice][sel])

    inner_x = (slice(None), slice(1, None))
    inner_x_left = (slice(None), slice(0, -1))
    inner_y = (slice(1, None), slice(None))
    inner_y_low = (slice(0, -1), slice(None))

    ones_x = np.ones((ny, nx - 1), dtype=bool) if nx > 1 else np.zeros((ny, 0), dtype=bool)
    ones_y = np.ones((ny - 1, nx), dtype=bool) if ny > 1 else np.zeros((0, nx), dtype=bool)

    add_link(ones_x, inner_x, inner_x_left, aW)      # West-Kopplung
    add_link(ones_x, inner_x_left, inner_x, aE)      # Ost-Kopplung
    add_link(ones_y, inner_y, inner_y_low, aS)       # Sued-Kopplung
    add_link(ones_y, inner_y_low, inner_y, aN)       # Nord-Kopplung

    matrix = csr_matrix((np.concatenate(data),
                         (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    solution = spsolve(matrix, b[active])
    x = np.zeros((ny, nx), dtype=float)
    x[active] = solution
    return x


def _solve_sor(aP, aW, aE, aS, aN, b, active, x0, tol, max_iter, omega):
    x = np.zeros_like(aP) if x0 is None else np.array(x0, dtype=float, copy=True)
    x[~active] = 0.0
    inv_aP = np.where(active, 1.0 / np.where(aP > 0.0, aP, 1.0), 0.0)

    ny, nx = aP.shape
    jj, ii = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    red = ((jj + ii) % 2 == 0) & active
    black = ((jj + ii) % 2 == 1) & active

    scale = max(float(np.abs(b[active]).max()), 1e-30)
    for iteration in range(1, max_iter + 1):
        for colour in (red, black):
            target = (b + neighbour_sum(x, aW, aE, aS, aN)) * inv_aP
            x = np.where(colour, x + omega * (target - x), x)
        r = residual(x, aP, aW, aE, aS, aN, b, active)
        if float(np.abs(r).max()) <= tol * scale:
            return x, iteration
    raise ConvergenceError(
        f"SOR-Verfahren nach {max_iter} Iterationen nicht konvergiert "
        f"(Restfehler {float(np.abs(r).max()) / scale:.2e} > {tol:.2e}). "
        "Zeitschritt verkleinern, Gitter vergroebern oder SciPy installieren."
    )
