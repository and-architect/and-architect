"""Beispiel 1: Innendaemmung eines Ziegelbestands (1D-Fall im 2D-Loeser).

Fragestellung: Eine 365 mm Vollziegelwand wird innen mit 50 mm kapillaraktivem
Calciumsilikat gedaemmt. Trocknet der Aufbau aus, und bleibt die Grenzflaeche
zwischen Daemmung und Mauerwerk unkritisch?

Aufruf::

    python beispiele/01_innendaemmung.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from wufi2d import analysis
from wufi2d import boundary as bnd
from wufi2d.climate import InteriorClimateFromExterior, synthetic_year
from wufi2d.grid import rectangle
from wufi2d.model import Model
from wufi2d.solver import InitialConditions, SolverOptions

TAG = 86400.0
STUNDE = 3600.0

# --- Aufbau von aussen nach innen ------------------------------------------
SCHICHTEN = [
    ("Kalkzementputz", 0.020),                  # Aussenputz
    ("Vollziegel (Altbau)", 0.365),             # Bestandsmauerwerk
    ("Klebemoertel (Innendaemmung)", 0.005),    # Ansetzmoertel
    ("Calciumsilikat (Innendaemmung)", 0.050),  # kapillaraktive Innendaemmung
    ("Kalkputz", 0.010),                        # Innenputz
]
HOEHE = 0.10  # Ausschnitthoehe; oben/unten adiabat -> eindimensionaler Fall


def modell_aufbauen() -> Model:
    modell = Model(name="Ziegelwand mit Calciumsilikat-Innendaemmung",
                   description="Aufbau nach WTA-Prinzip, kapillaraktiv, ohne Dampfsperre")

    x = 0.0
    for material, dicke in SCHICHTEN:
        modell.add_region(material, rectangle(x, 0.0, dicke, HOEHE), name=material)
        x += dicke

    # Gitter: fein an Oberflaechen und Schichtgrenzen, grob in der Wandmitte
    modell.grid_options.max_cell = 0.015
    modell.grid_options.min_cell = 0.001
    modell.grid_options.max_cell_y = HOEHE
    modell.grid_options.min_cell_y = HOEHE

    # Aussenklima: synthetisches Referenzjahr mit Jahres- und Tagesgang,
    # Einstrahlung und Schlagregenereignissen (350 mm/a auf die Fassade).
    # Fuer Nachweise stattdessen ein TRY einlesen:
    #   from wufi2d import read_climate_csv
    #   aussen = read_climate_csv("try_muenchen.csv", rain_unit="mm/h")
    aussen = synthetic_year(mean_temperature=9.0, amplitude_temperature=9.5,
                            mean_rh=0.78, amplitude_rh=0.09,
                            daily_temperature_amplitude=3.0, solar_peak=350.0,
                            annual_rain=350.0)
    # Innenklima nach dem Ansatz von EN 15026 (normale Feuchtelast)
    innen = InteriorClimateFromExterior(aussen, moisture_load="normal")

    modell.add_boundary("links", bnd.exterior_surface(
        aussen, alpha=17.0, solar_absorptance=0.6, rain_absorption=0.7,
        name="aussen"))
    modell.add_boundary("rechts", bnd.interior_surface(innen, alpha=8.0, name="innen"))

    # Startzustand: durchfeuchtetes Bestandsmauerwerk
    modell.initial = InitialConditions(
        temperature=15.0, rh=0.8,
        per_material={"Vollziegel (Altbau)": {"rh": 0.9}})
    modell.options = SolverOptions(duration=2 * 365 * TAG, dt=STUNDE,
                                   output_interval=12 * STUNDE)
    return modell


def main() -> None:
    modell = modell_aufbauen()
    print(modell.describe())
    for warnung in modell.validate():
        print(f"Warnung: {warnung}")

    loeser = modell.build_solver()
    print()
    print(loeser.grid.summary())
    print("\nrechnet ...")
    ergebnis = loeser.run()

    print()
    print(analysis.report(ergebnis, surfaces=["innen", "aussen"]))

    # Grenzflaeche Daemmung / Mauerwerk -- der kritische Punkt dieses Aufbaus
    x_grenze = sum(d for _, d in SCHICHTEN[:2]) + 0.0025
    risiko = analysis.mould_risk_at_point(ergebnis, x_grenze, HOEHE / 2)
    print()
    print("Grenzflaeche Mauerwerk / Innendaemmung:")
    print("  " + risiko.summary())

    # Jahresweise Feuchtebilanz: trocknet der Aufbau aus?
    print("\nWassergehalt des Mauerwerks je Jahresende:")
    ziegel = ergebnis.water_by_material["Vollziegel (Altbau)"]
    for jahr in range(1, 3):
        index = ergebnis.index_at(jahr * 365 * TAG)
        print(f"  nach {jahr} Jahr(en): {ziegel[index]:.2f} kg "
              f"({ziegel[index] / ziegel[0] * 100:.0f} % des Startwerts)")
    bilanz = analysis.moisture_balance(ergebnis, material="Vollziegel (Altbau)")
    print("  " + bilanz.summary())

    # Temperaturprofil im Winter des letzten Jahres
    winter = 365 * TAG + 15 * TAG
    x, temperatur = ergebnis.profile("temperature", time=winter)
    _, feuchte = ergebnis.profile("rh", time=winter)
    print(f"\nProfil am Tag {winter / TAG:.0f} (Winter):")
    for tiefe in np.linspace(0.0, x[-1], 9):
        k = int(np.argmin(np.abs(x - tiefe)))
        print(f"  x = {x[k] * 1000:6.1f} mm: {temperatur[k]:6.2f} degC, "
              f"{feuchte[k] * 100:5.1f} % rF")


if __name__ == "__main__":
    main()
