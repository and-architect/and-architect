"""Beispiel 3: Holzbalkenkopf in einer innengedaemmten Ziegelwand (echt 2D).

Der kritische Punkt jeder Innendaemmung im Altbau: der Holzbalkenkopf liegt im
kalten Bereich des Mauerwerks, die Innendaemmung unterbricht die Waermezufuhr
aus dem Raum. Gerechnet wird ein Jahr, ausgewertet werden Holzfeuchte
(Grenzwert 20 M.-% nach DIN 68800-2), Schimmelrisiko an der Auflagerflaeche und
die Feuchtebilanz.

Aufruf::

    python beispiele/03_holzbalkenkopf.py [--jahre 2] [--ohne-daemmung]

Rechenzeit: etwa 2-4 Minuten je Jahr (rund 1000 Zellen, 2-h-Zeitschritt).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from wufi2d import analysis
from wufi2d import boundary as bnd
from wufi2d.climate import InteriorClimateFromExterior, synthetic_year
from wufi2d.grid import Region, rectangle
from wufi2d.model import Model
from wufi2d.solver import InitialConditions, SolverOptions

TAG = 86400.0
STUNDE = 3600.0

# --- Geometrie (x = 0 ist die Aussenkante des Mauerwerks) -------------------
PUTZ_AUSSEN = 0.020
MAUERWERK = 0.365
DAEMMUNG = 0.060
PUTZ_INNEN = 0.010
HOEHE = 0.60           # Ausschnitt: halbe Geschosshoehe ueber/unter dem Balken
BALKEN_HOEHE = 0.18
BALKEN_UNTEN = 0.21    # Unterkante des Balkens
AUFLAGERTIEFE = 0.12   # verbleibendes Mauerwerk zwischen Balkenkopf und aussen
BALKEN_INNEN = 0.60    # Balken laeuft bis hierher (Schnittkante, adiabat)

X_AUSSEN = -PUTZ_AUSSEN
X_DAEMMUNG = MAUERWERK
X_PUTZ_INNEN = MAUERWERK + DAEMMUNG
X_INNEN = X_PUTZ_INNEN + PUTZ_INNEN
X_BALKENKOPF = AUFLAGERTIEFE


def modell_aufbauen(jahre: float = 1.0, mit_daemmung: bool = True) -> Model:
    modell = Model(
        name="Holzbalkenkopf in innengedaemmter Ziegelwand",
        description=("2D-Detail: Balkenkopf im Mauerwerk, "
                     + ("mit 60 mm Holzfaser-Innendaemmung" if mit_daemmung
                        else "ohne Innendaemmung (Vergleichsfall)")))

    # Wandaufbau ueber die volle Hoehe
    modell.regions.append(Region("Kalkzementputz",
                                 rectangle(X_AUSSEN, 0.0, PUTZ_AUSSEN, HOEHE),
                                 name="Aussenputz"))
    modell.regions.append(Region("Vollziegel (Altbau)",
                                 rectangle(0.0, 0.0, MAUERWERK, HOEHE),
                                 name="Mauerwerk"))
    if mit_daemmung:
        modell.regions.append(Region("Holzfaserdaemmplatte",
                                     rectangle(X_DAEMMUNG, 0.0, DAEMMUNG, HOEHE),
                                     name="Innendaemmung"))
        modell.regions.append(Region("Kalkputz",
                                     rectangle(X_PUTZ_INNEN, 0.0, PUTZ_INNEN, HOEHE),
                                     name="Innenputz"))
    else:
        modell.regions.append(Region("Kalkputz",
                                     rectangle(X_DAEMMUNG, 0.0, PUTZ_INNEN, HOEHE),
                                     name="Innenputz"))

    # Der Balken ueberschreibt Mauerwerk, Daemmung und Innenputz (Prioritaet 1)
    balken_start = X_BALKENKOPF
    modell.regions.append(Region(
        "Brettschichtholz",
        rectangle(balken_start, BALKEN_UNTEN, BALKEN_INNEN - balken_start,
                  BALKEN_HOEHE),
        priority=1, name="Holzbalken"))

    # Gitter: fein an Oberflaechen und um den Balkenkopf
    modell.grid_options.max_cell = 0.030
    modell.grid_options.min_cell = 0.005
    modell.grid_options.growth = 1.4

    # Klima
    aussen = synthetic_year(mean_temperature=8.5, amplitude_temperature=9.5,
                            mean_rh=0.80, amplitude_rh=0.08,
                            daily_temperature_amplitude=3.0, solar_peak=300.0,
                            annual_rain=250.0)
    innen = InteriorClimateFromExterior(aussen, moisture_load="normal")

    innenkante = X_INNEN if mit_daemmung else X_DAEMMUNG + PUTZ_INNEN
    modell.add_boundary(bnd.BoxSelector(X_AUSSEN - 0.01, -0.05, X_AUSSEN + 0.005,
                                        HOEHE + 0.05),
                        bnd.exterior_surface(aussen, solar_absorptance=0.6,
                                             rain_absorption=0.7, name="aussen"))
    modell.add_boundary(bnd.BoxSelector(innenkante - 0.005, -0.05,
                                        BALKEN_INNEN + 0.01, HOEHE + 0.05),
                        bnd.interior_surface(innen, name="innen"))
    # Schnittkante des Balkens (der Balken laeuft in die Decke weiter)
    modell.add_boundary(bnd.BoxSelector(BALKEN_INNEN - 0.005, BALKEN_UNTEN - 0.01,
                                        BALKEN_INNEN + 0.005,
                                        BALKEN_UNTEN + BALKEN_HOEHE + 0.01,
                                        sides=["rechts"]),
                        bnd.AdiabaticBoundary())

    # Anfangszustand: feuchtes Bestandsmauerwerk, Holz bei ca. 15 M.-%
    modell.initial = InitialConditions(
        temperature=12.0, rh=0.8,
        per_material={"Vollziegel (Altbau)": {"rh": 0.9},
                      "Brettschichtholz": {"rh": 0.78}})
    modell.options = SolverOptions(duration=jahre * 365 * TAG, dt=2 * STUNDE,
                                   output_interval=TAG)
    return modell


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jahre", type=float, default=1.0,
                        help="Simulationsdauer in Jahren (Standard 1)")
    parser.add_argument("--ohne-daemmung", action="store_true",
                        help="Vergleichsfall ohne Innendaemmung")
    args = parser.parse_args()

    modell = modell_aufbauen(args.jahre, not args.ohne_daemmung)
    print(modell.describe())
    for warnung in modell.validate():
        print(f"Warnung: {warnung}")

    loeser = modell.build_solver()
    print()
    print(loeser.grid.summary())
    print()
    print(loeser.assignment.summary())

    print("\nrechnet ...")
    ergebnis = loeser.run(progress=lambda t, dauer: None)
    print(f"Rechenzeit: {ergebnis.meta['runtime_s']:.1f} s "
          f"({ergebnis.meta['steps']} Zeitschritte)")

    print()
    print(analysis.report(ergebnis, surfaces=["innen"],
                          wood_materials=["Brettschichtholz"]))

    # Kritischste Stelle des Holzes automatisch suchen
    holz = modell.library().get("Brettschichtholz")
    kritisch = analysis.worst_cell(ergebnis, "Brettschichtholz", "water_content")
    print(f"\nFeuchteste Stelle im Balken: x = {kritisch['x'] * 1000:.0f} mm, "
          f"y = {kritisch['y'] * 1000:.0f} mm "
          f"(Tag {kritisch['zeit_d']:.0f})")
    print(f"  {kritisch['wert']:.1f} kg/m3 = "
          f"{100.0 * kritisch['wert'] / holz.rho:.1f} M.-%, "
          f"{kritisch['temperatur']:.1f} degC, {kritisch['rh'] * 100:.1f} % rF")
    print("  " + analysis.mould_risk_at_point(ergebnis, kritisch["x"],
                                              kritisch["y"]).summary())

    # Auflagerflaeche des Balkenkopfs
    kopf_x = X_BALKENKOPF + 0.01
    kopf_y = BALKEN_UNTEN + BALKEN_HOEHE / 2
    print("\nBalkenkopf, 10 mm hinter der Auflagerflaeche:")
    reihe = ergebnis.cell_series(kopf_x, kopf_y)
    print(f"  Temperatur {reihe['temperature'].min():.1f} .. "
          f"{reihe['temperature'].max():.1f} degC")
    print(f"  rel. Feuchte {reihe['rh'].min() * 100:.1f} .. "
          f"{reihe['rh'].max() * 100:.1f} %")
    feuchte_ma = 100.0 * reihe["water_content"] / holz.rho
    print(f"  Holzfeuchte {feuchte_ma.min():.1f} .. {feuchte_ma.max():.1f} M.-% "
          f"(Grenzwert 20 M.-%)")

    # Vergleich mit dem Balkeninneren (raumseitig, warm)
    innen_reihe = ergebnis.cell_series(BALKEN_INNEN - 0.02, kopf_y)
    print(f"\nBalken raumseitig: {innen_reihe['temperature'].min():.1f} .. "
          f"{innen_reihe['temperature'].max():.1f} degC, "
          f"{100.0 * innen_reihe['water_content'].max() / holz.rho:.1f} M.-% max")

    # Jahreswerte des Wassergehalts im Holz
    print("\nWassergehalt des Balkens:")
    for jahr, wert in analysis.yearly_water_content(ergebnis, "Brettschichtholz"):
        print(f"  nach {jahr:.0f} Jahr(en): {wert:.3f} kg")

    ziel = Path(__file__).with_name("03_holzbalkenkopf_ergebnis.npz")
    print(f"\nFelder gespeichert: {ergebnis.to_npz(ziel)}")
    print("Darstellung in Rhino: rhino/WufiErgebnisAnzeigen.py")


if __name__ == "__main__":
    main()
