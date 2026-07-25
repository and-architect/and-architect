"""Kommandozeile: Modelle rechnen, pruefen und Materialien anzeigen.

Aufruf::

    python -m wufi2d materialien
    python -m wufi2d info  modell.json
    python -m wufi2d rechne modell.json --npz ergebnis.npz --csv ergebnis.csv
    python -m wufi2d stationaer modell.json --dt-innen 20 --dt-aussen -5
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import List, Optional

import numpy as np

from . import analysis
from .material import default_library
from .model import Model
from .results import Results

SECONDS_PER_DAY = 86400.0


def _progress_printer(total: float):
    state = {"last": -1, "start": time.time()}

    def progress(t: float, duration: float) -> None:
        percent = int(100.0 * t / max(duration, 1e-9))
        if percent > state["last"]:
            state["last"] = percent
            elapsed = time.time() - state["start"]
            sys.stderr.write(f"\r  {percent:3d} %  ({t / SECONDS_PER_DAY:7.1f} d, "
                             f"{elapsed:5.1f} s)")
            sys.stderr.flush()
            if percent >= 100:
                sys.stderr.write("\n")

    return progress


def cmd_materials(args: argparse.Namespace) -> int:
    library = default_library()
    if args.name:
        print(library.get(args.name).describe())
        material = library.get(args.name)
        for phi in (0.0, 0.5, 0.8, 0.95, 1.0):
            print(f"  phi = {phi:4.2f}: w = {float(material.w(phi)):8.2f} kg/m3, "
                  f"dw/dphi = {float(material.dw_dphi(phi)):10.1f} kg/m3, "
                  f"D_ws = {float(material.dw_suction(material.w(phi))):.3e} m2/s")
        return 0
    for category, names in library.by_category().items():
        print(f"{category}:")
        for name in names:
            print(f"  {library.get(name).describe()}")
    print("\nHinweis: Richtwerte aus der Literatur, keine geprueften Messdaten.")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    model = Model.load(args.model)
    print(model.describe())
    print()
    grid = model.build_grid()
    print(grid.summary())
    print()
    print(model.boundary_set().assign(grid.exposed_faces()).summary())
    warnings = model.validate()
    if warnings:
        print("\nWarnungen:")
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("\nModell ist plausibel.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    model = Model.load(args.model)
    if args.duration_days:
        model.options.duration = float(args.duration_days) * SECONDS_PER_DAY
    if args.dt_hours:
        model.options.dt = float(args.dt_hours) * 3600.0
    for warning in model.validate():
        print(f"Warnung: {warning}", file=sys.stderr)
    print(model.describe())
    solver = model.build_solver()
    print()
    print(solver.grid.summary())
    print()
    results = solver.run(progress=None if args.quiet else _progress_printer(
        model.options.duration))
    print()
    print(analysis.report(results, wood_materials=[
        name for name in results.grid.material_names
        if model.library().get(name).category == "Holz"]))
    print(f"\nRechenzeit: {results.meta['runtime_s']:.1f} s "
          f"({results.meta['steps']} Zeitschritte)")
    if args.npz:
        print(f"Felder gespeichert: {results.to_npz(args.npz)}")
    if args.csv:
        print(f"Zeitreihen gespeichert: {results.to_csv(args.csv)}")
    return 0


def cmd_steady(args: argparse.Namespace) -> int:
    model = Model.load(args.model)
    solver = model.build_solver()
    temperature, rh = solver.solve_steady_state()
    active = solver.grid.active
    print(solver.grid.summary())
    print()
    print(f"Temperatur: {np.nanmin(temperature[active]):.2f} .. "
          f"{np.nanmax(temperature[active]):.2f} degC")
    print(f"Rel. Feuchte: {np.nanmin(rh[active]) * 100:.1f} .. "
          f"{np.nanmax(rh[active]) * 100:.1f} %")
    if args.interior is None or args.exterior is None:
        print("\nFuer L2D, f_Rsi und Psi zusaetzlich --innen und --aussen angeben.")
        return 0

    delta = float(args.interior) - float(args.exterior)
    # Die Bilanzgroessen (Waermestrom je Randgruppe) liefert ein einzelner
    # Zeitschritt, der auf dem stationaeren Zustand aufsetzt.
    results = _steady_results(solver)
    print()
    for name in results.surfaces:
        l2d = analysis.thermal_coupling_coefficient(results, name, delta)
        flux = results.surfaces[name].heat_flux[-1]
        print(f"  '{name}': q = {flux:+.3f} W je m Bauteil, "
              f"L2D = {l2d:.4f} W/(m K)")

    warm = args.warm_surface or _warmest_surface(results)
    if warm in results.surfaces:
        l2d = analysis.thermal_coupling_coefficient(results, warm, delta)
        factor = analysis.temperature_factor(results, warm, float(args.interior),
                                             float(args.exterior))
        t_min = float(np.min(results.surfaces[warm].min_temperature))
        print(f"\nAuswertung an der warmen Seite '{warm}':")
        print(f"  L2D      = {l2d:.4f} W/(m K)")
        print(f"  T_si,min = {t_min:.2f} degC")
        print(f"  f_Rsi    = {factor:.3f} "
              f"({'>= 0.70 eingehalten' if factor >= 0.7 else '< 0.70 -- kritisch'})")
        u_values = [float(v) for v in (args.u or [])]
        lengths = [float(v) for v in (args.l or [])]
        if u_values and len(u_values) == len(lengths):
            psi = analysis.psi_value(l2d, list(zip(u_values, lengths)))
            summe = sum(u * length for u, length in zip(u_values, lengths))
            print(f"  Summe U*l = {summe:.4f} W/(m K)")
            print(f"  Psi      = {psi:+.4f} W/(m K)")
        elif u_values:
            print("  Hinweis: --u und --l muessen gleich viele Werte haben.")
        else:
            print("  Psi-Wert: --u und --l der ungestoerten Bauteile angeben.")
    return 0


def _warmest_surface(results: Results) -> str:
    """Randgruppe mit der hoechsten mittleren Oberflaechentemperatur."""
    return max(results.surfaces,
               key=lambda name: float(np.mean(results.surfaces[name].temperature)))


def _steady_results(solver) -> Results:
    """Bilanzgroessen des stationaeren Zustands als ``Results`` verpacken."""
    options = solver.options
    original = (options.duration, options.dt, options.output_interval)
    options.duration = options.dt
    options.output_interval = options.dt
    try:
        return solver.run()
    finally:
        options.duration, options.dt, options.output_interval = original


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wufi2d",
        description="Gekoppelte 2D-Waerme- und Feuchtesimulation "
                    "(WUFI-/Kuenzel-Prinzip)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_mat = sub.add_parser("materialien", aliases=["materials"],
                           help="Materialdatenbank anzeigen")
    p_mat.add_argument("name", nargs="?", help="Einzelnes Material im Detail")
    p_mat.set_defaults(func=cmd_materials)

    p_info = sub.add_parser("info", help="Modell pruefen und beschreiben")
    p_info.add_argument("model", help="Modelldatei (JSON)")
    p_info.set_defaults(func=cmd_info)

    p_run = sub.add_parser("rechne", aliases=["run"], help="Transiente Berechnung")
    p_run.add_argument("model", help="Modelldatei (JSON)")
    p_run.add_argument("--npz", help="Felder als .npz speichern")
    p_run.add_argument("--csv", help="Zeitreihen als CSV speichern")
    p_run.add_argument("--duration-days", type=float, help="Dauer ueberschreiben [d]")
    p_run.add_argument("--dt-hours", type=float, help="Zeitschritt ueberschreiben [h]")
    p_run.add_argument("--quiet", action="store_true", help="Keine Fortschrittsanzeige")
    p_run.set_defaults(func=cmd_run)

    p_steady = sub.add_parser("stationaer", aliases=["steady"],
                              help="Stationaere Loesung und Waermebrueckenkennwerte")
    p_steady.add_argument("model", help="Modelldatei (JSON)")
    p_steady.add_argument("--innen", dest="interior", type=float,
                          help="Innenlufttemperatur [degC] fuer L2D und f_Rsi")
    p_steady.add_argument("--aussen", dest="exterior", type=float,
                          help="Aussenlufttemperatur [degC] fuer L2D und f_Rsi")
    p_steady.add_argument("--flaeche", dest="warm_surface",
                          help="Name der warmen Randbedingung (Standard: "
                               "waermste Gruppe)")
    p_steady.add_argument("--u", nargs="*", type=float,
                          help="U-Werte der ungestoerten Bauteile [W/m2K] "
                               "fuer den Psi-Wert")
    p_steady.add_argument("--l", nargs="*", type=float,
                          help="zugehoerige Laengen [m] fuer den Psi-Wert")
    p_steady.set_defaults(func=cmd_steady)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
