# wufi2d — hygrothermische 2D-Bauteilsimulation für Rhino 8/9 und Grasshopper

Gekoppelte Wärme- und Feuchteberechnung für zweidimensionale Bauteilschnitte
nach dem Modell von **Künzel (Fraunhofer-Institut für Bauphysik, IBP)** — dem
Rechenprinzip, auf dem WUFI aufbaut. Geometrie kommt aus Rhino/Grasshopper, der
Rechenkern ist reines Python + NumPy und läuft auch headless (CLI, CI,
Parameterstudien).

> **Abgrenzung:** Dies ist eine eigenständige Implementierung der
> *veröffentlichten Modellgleichungen* (Künzel 1995). Es ist **nicht WUFI**,
> keine Portierung von WUFI-Code und enthält **nicht** die lizenzpflichtige
> WUFI-/IBP-Materialdatenbank. „WUFI“ ist eine Marke des Fraunhofer IBP. Für
> Nachweise mit Zertifizierungsbedarf ist die validierte Originalsoftware zu
> verwenden; dieses Werkzeug ist für Entwurf, Variantenvergleich und
> Lehre/Forschung gedacht.

---

## Was gerechnet wird

Zwei gekoppelte Bilanzgleichungen mit den Potentialen Temperatur `T` und
relativer Feuchte `φ` (Künzel 1995):

```
Feuchte:  dw/dφ · ∂φ/∂t = ∇·( D_φ ∇φ  +  δ_p ∇(φ·p_sat) )
Wärme:    dH/dT · ∂T/∂t = ∇·( λ ∇T )  +  h_v ∇·( δ_p ∇(φ·p_sat) )
```

| Effekt | Umsetzung |
|---|---|
| Wärmeleitung | feuchteabhängiges `λ(w) = λ_dry·(1 + b/100·u)` |
| Wasserdampfdiffusion | `δ_p = δ_a(T)/µ`, µ optional feuchteabhängig (Dry-/Wet-Cup) |
| Kapillarer Flüssigtransport | `D_w` aus dem Wasseraufnahmekoeffizienten `A_w` nach Künzel, getrennt für Saugen (`D_ws`) und Weiterverteilung (`D_ww`) |
| Feuchtespeicherung | Sorptionsisotherme aus `w_80`/`w_f` (Künzel-Approximation) oder tabelliert |
| Latentwärme | Verdunstung/Kondensation aus der Dampfstrombilanz |
| Wärme-/Dampfübergang | `α`, `β` (Lewis), Beschichtung als `s_d`-Wert |
| Kurzwellige Einstrahlung | Sol-Air-Temperatur mit Absorptionsgrad |
| Langwellige Abstrahlung | optional über Himmelstemperatur |
| Schlagregen | Regenlast mit Aufnahmefaktor, Ablaufen bei Sättigung |
| Baufeuchte | material- oder regionsweise Anfangsbedingungen |
| 2D-Geometrie | beliebige Polygone, Aussparungen, L-Formen, Wärmebrücken |

### Numerik

* **Finite Volumen** auf strukturiertem, randverfeinertem Rechteckgitter
  (wie WUFI 2D), Transportkoeffizienten an Zellgrenzen als Reihenschaltung der
  Halbzellenwiderstände → Materialsprünge korrekt abgebildet.
* **Implizites Euler-Verfahren**, Picard-Iteration für die Nichtlinearität mit
  **automatischer Dämpfung** (erkennt Pendeln) und adaptivem Zeitschritt.
* **Massenkonservative Feuchtebilanz** über das modifizierte Picard-Schema
  (Celia et al. 1990) — die Massenbilanz schließt auch bei stark nichtlinearer
  Sorptionsisotherme (Testnachweis: relativer Fehler < 1e-9 bei linearer,
  < 1e-4 bei realer Isotherme).
* **Gleichungslöser:** SciPy-Sparse, sonst automatisch SOR-Fallback (nur NumPy)
  — läuft damit auch in schlanken Rhino-Python-Umgebungen.

### Verifikation

Die Testsuite vergleicht mit analytischen Lösungen, nicht nur mit sich selbst:

| Testfall | Referenz | Ergebnis |
|---|---|---|
| Stationärer Wärmedurchgang, Mehrschichtaufbau | Reihenschaltung der `R`-Werte | Abweichung < 0,05 K bzw. < 2 % im Wärmestrom |
| Stationäre Dampfdiffusion | Reihenschaltung der `s_d`-Werte (Glaser-Fall) | < 2 % im Dampfdruckprofil |
| Instationäre Erwärmung, halbunendlicher Körper | `erf`-Lösung | max. Abweichung < 0,15 K |
| Instationäre Feuchteaufnahme (lineare Isotherme) | `erf`-Lösung | max. Abweichung < 0,02 in `φ` |
| Geschlossenes Gebiet | Massen- und Energieerhaltung | exakt bis Lösertoleranz |
| Symmetrisches Modell | Spiegelsymmetrie des Feldes | exakt bis 1e-6 |
| Wärmebrücke (Balkonplatte) | `Ψ = L2D − ΣU·l`, EN ISO 10211 | Ψ = 0,94 W/(m·K), plausibel |

```bash
python -m pytest wufi2d/tests -q     # 121 Tests, ca. 30 s
```

**Nicht enthalten** (bewusste Grenzen): Luftströmung/Konvektion in Hohlräumen
und Fugen, Eisbildung und Frost-Tau-Wechsel, Salztransport, hygrische
Verformung, 3D. Der überhygroskopische Bereich über der freien Wassersättigung
wird auf `φ = 1` begrenzt (überschüssiges Wasser läuft ab), nicht wie in WUFI
bis `w_max` weitergeführt.

---

## Installation

**Voraussetzung:** Rhino 8 oder 9 (Python 3 / CPython) bzw. Python ≥ 3.9 headless.

```bash
git clone <dieses Repository>
cd and-architect/wufi2d
python -m pip install numpy          # scipy ist optional, aber deutlich schneller
python -m pip install scipy
python -m pytest tests -q            # Selbsttest
```

In Rhino/Grasshopper wird nichts installiert: die Komponenten hängen den Ordner
`wufi2d/src` in `sys.path`. NumPy holt sich der Rhino-Script-Editor über die
Zeile `# r: numpy` selbst.

---

## Schnellstart

### Grasshopper

1. **`01_Setup.py`** in eine Python-3-Skriptkomponente kopieren, Eingang `pfad`
   auf `…/wufi2d/src` setzen. Ausgang `materialien` zeigt die Materialliste.
2. Bauteilschnitt als **geschlossene Kurven in der XY-Ebene** zeichnen
   (achsparallele Rechtecke sind ideal — ihre Kanten werden zu Gitterlinien).
3. **`02_Region.py`**: Kurven + Materialnamen → Regionen.
4. **`03_Klima.py`**: Außenklima (konstant / Sinus / CSV) und Innenklima.
5. **`04_Rand.py`**: Oberflächenkurve oder Seite (`links`/`rechts`/…) + Klima
   → Randbedingung. Nicht zugewiesene Ränder sind adiabat (Schnittkanten).
6. **`05_Modell.py`**: Regionen + Ränder + Zellgröße + Dauer → Modell,
   Vorschau-Mesh, Warnungen.
7. **`06_Rechnen.py`**: Schalter `rechnen` auf `True`.
8. **`07_Ergebnis.py`**: farbiges Mesh, Isolinien, Legende.
9. **`08_Auswertung.py`**: Bericht, Schimmelrisiko, Feuchtebilanz, L2D/f_Rsi/Ψ.

Jede Komponentendatei beginnt mit der Liste der anzulegenden Ein- und Ausgänge.
Details: [`grasshopper/README.md`](grasshopper/README.md).

### Rhino (interaktiv, ohne Grasshopper)

```
_-RunPythonScript "…/wufi2d/rhino/WufiSchnellstart.py"
```

Fragt Kurven, Materialien, Oberflächen, Klima und Dauer ab, rechnet und legt das
Ergebnis als farbiges Mesh ab. Ergebnisse später wieder anzeigen:
`rhino/WufiErgebnisAnzeigen.py`. Details: [`rhino/README.md`](rhino/README.md).

### Python

```python
from wufi2d import ConstantClimate, Model, SolverOptions, analysis, rectangle
from wufi2d import boundary as bnd

modell = Model(name="Außenwand")
modell.add_region("Vollziegel (Altbau)", rectangle(0.0, 0.0, 0.365, 0.1))
modell.add_region("Kalkputz",            rectangle(0.365, 0.0, 0.015, 0.1))
modell.add_boundary("links",  bnd.exterior_surface(ConstantClimate(-5.0, 0.8)))
modell.add_boundary("rechts", bnd.interior_surface(ConstantClimate(20.0, 0.5)))
modell.options = SolverOptions(duration=90 * 86400.0, dt=3600.0)

ergebnis = modell.run()
print(analysis.report(ergebnis))
```

### Kommandozeile

```bash
python -m wufi2d materialien                     # Datenbank anzeigen
python -m wufi2d info       modell.json          # Gitter und Ränder prüfen
python -m wufi2d rechne     modell.json --npz ergebnis.npz --csv verlauf.csv
python -m wufi2d stationaer modell.json --innen 20 --aussen -5 --u 0.199 --l 1.2
```

---

## Beispiele

| Datei | Fall |
|---|---|
| [`beispiele/01_innendaemmung.py`](beispiele/01_innendaemmung.py) | Kapillaraktive Calciumsilikat-Innendämmung auf 365 mm Ziegel, 2 Jahre, Trocknungsverlauf und Grenzflächenfeuchte |
| [`beispiele/02_waermebruecke.json`](beispiele/02_waermebruecke.json) | Auskragende Balkonplatte im WDVS — L2D, Ψ, f_Rsi (stationär, < 1 s) |
| [`beispiele/03_holzbalkenkopf.py`](beispiele/03_holzbalkenkopf.py) | Holzbalkenkopf in innengedämmter Ziegelwand (echt 2D), Holzfeuchte gegen 20 M.-%, Vergleich mit/ohne Dämmung |

```bash
python beispiele/01_innendaemmung.py
python -m wufi2d stationaer beispiele/02_waermebruecke.json --innen 20 --aussen -5 --u 0.1988 --l 1.2
python beispiele/03_holzbalkenkopf.py --jahre 1
python beispiele/03_holzbalkenkopf.py --jahre 1 --ohne-daemmung   # Vergleich
```

---

## Materialdaten

`python -m wufi2d materialien` listet rund 28 Materialien (Mauerwerk, Putze,
Dämmstoffe, Holz, Platten, Metalle) mit Dichte, `c_p`, `λ`, `µ`, `w_80`, `w_f`,
`A_w`.

> ⚠️ **Die Datenbank enthält Richtwerte aus der Literatur, keine geprüften
> Messdaten und keine WUFI-/IBP-Daten.** Für Nachweise sind produktspezifische,
> gemessene Kennwerte einzusetzen:

```python
from wufi2d import Material, MaterialLibrary, Model

produkt = Material(
    name="Dämmplatte XY", rho=155.0, cp=2100.0, lambda_dry=0.040, mu=3.2,
    w_f=480.0, w_80=25.0, a_w=0.018, lambda_moisture_supplement=0.5,
)
modell = Model(materials=MaterialLibrary([produkt]))   # ergänzt die Standard-DB
```

Hilfsfunktionen: `air_layer(dicke)` für ruhende Luftschichten,
`membrane(sd)` für Folien, `variable_membrane(sd_trocken, sd_feucht)` für
feuchtevariable Dampfbremsen.

## Klimadaten

```python
from wufi2d import read_climate_csv                    # TRY/Messdaten (CSV)
from wufi2d.climate import synthetic_year              # synthetisches Jahr
from wufi2d import InteriorClimateFromExterior         # Innenklima nach EN 15026

aussen = read_climate_csv("try.csv", rain_unit="mm/h")  # deutsche und englische
innen  = InteriorClimateFromExterior(aussen, moisture_load="normal")
```

Der CSV-Leser erkennt gängige Spaltennamen (`Temperatur`/`Temperature`,
`rF`/`RH`, `Strahlung`/`Solar`, `Regen`/`Rain`, `Wind`), Dezimalkomma und
Semikolon; abweichende Kopfzeilen über `column_map`. Schlagregen aus
Horizontalniederschlag und Wind: `driving_rain(...)`.

Die Zahlenwerte des EN-15026-Innenklimas und die kritische Feuchtekurve für
Schimmel (`analysis.DEFAULT_CRITICAL_RH`) sind **Näherungen** und als Parameter
zugänglich — für Nachweise gegen die geltende Normfassung prüfen.

---

## Auswertung

```python
from wufi2d import analysis

analysis.report(ergebnis)                                  # Gesamtbericht
analysis.annual_balance(ergebnis)                          # Bilanz des letzten Jahres
analysis.worst_cell(ergebnis, "Brettschichtholz", "water_content")   # kritische Stelle
analysis.wood_moisture_check(ergebnis, "Brettschichtholz", limit=20) # DIN 68800-2
analysis.mould_risk_at_surface(ergebnis, "innen")           # Isoplethen-Näherung
analysis.thermal_coupling_coefficient(ergebnis, "innen", 25.0)       # L2D
analysis.temperature_factor(ergebnis, "innen", 20.0, -5.0)           # f_Rsi
analysis.psi_value(l2d, [(0.1988, 1.2)])                             # Ψ
```

Ergebnisexport: `ergebnis.to_npz(...)`, `ergebnis.to_csv(...)`,
`Results.from_npz(...)`, `ergebnis.field("rh", time=…)`,
`ergebnis.profile("temperature")`, `ergebnis.cell_series(x, y)`.

---

## Diskretisierung und Rechenzeit

Die kleinste Zelle gehört an Oberflächen und Materialgrenzen, die Wandmitte darf
grob sein — genau das macht das expandierende Gitter automatisch
(`min_cell` … `max_cell`, `growth`).

Gemessen auf einem Standard-Kern (SciPy vorhanden):

| Fall | Zellen | Zeitschritte | Rechenzeit |
|---|---|---|---|
| Wärmebrücke stationär (Beispiel 2) | 4 300 | — | < 1 s |
| 1D-Aufbau, 2 Jahre, dt = 1 h (Beispiel 1) | 82 | 17 500 | ≈ 3 min |
| 2D-Detail, 1 Jahr, dt = 2 h (Beispiel 3) | 1 900 | 4 400 | 6,2 min (gemessen) |

Schneller wird es mit größerem `dt` (Feuchte reagiert träge — 2–6 h sind für
Jahresrechnungen meist ausreichend), gröberem `max_cell` und größerem
`output_interval`. Für Wärmebrückenkennwerte genügt `solve_steady_state()`.
Lange Läufe besser headless über die CLI als in Grasshopper — dort blockiert die
Rechnung die Rhino-Oberfläche.

---

## Aufbau des Codes

```
wufi2d/
├─ src/wufi2d/
│  ├─ physics.py     p_sat, δ_a, Kelvin-Gleichung, Konstanten
│  ├─ material.py    Material, Sorptionsisotherme, D_w, λ(w), Bibliothek
│  ├─ materials_db.json   Richtwerte-Datenbank
│  ├─ grid.py        Regionen (Polygone), expandierendes Gitter, Randflächen
│  ├─ climate.py     konstant/Sinus/CSV/synthetisch, Innenklima, Schlagregen
│  ├─ boundary.py    Übergang/Festwert/adiabat, Selektoren (Seite, Kurve, Box)
│  ├─ solver.py      FVM-Assemblierung, Picard-Iteration, Zeitschleife
│  ├─ linalg.py      5-Punkt-Löser (SciPy oder SOR-Fallback)
│  ├─ results.py     Felder, Oberflächenreihen, Bilanzen, Export
│  ├─ analysis.py    L2D/Ψ/f_Rsi, Feuchtebilanz, Schimmel, Holzschutz
│  ├─ model.py       Modell als JSON (Grasshopper ↔ CLI)
│  ├─ rhino.py       Kurve→Region, Mesh, Farbverläufe, Isolinien
│  └─ cli.py         python -m wufi2d
├─ grasshopper/      8 Skriptkomponenten (Rhino 8/9, Python 3)
├─ rhino/            Befehlsskripte
├─ beispiele/        drei durchgerechnete Fälle
└─ tests/            121 Tests (Physik, Gitter, Löser-Verifikation, Adapter)
```

Der Rechenkern kennt Rhino nicht — `rhino.py` ist die einzige Brücke, und ihre
geometriefreien Teile (Mesh-Aufbau, Farbverläufe, Isolinien) sind mitgetestet.

---

## Quellen

* Künzel, H.M. (1995): *Simultaneous Heat and Moisture Transport in Building
  Components. One- and two-dimensional calculation using simple parameters.*
  Fraunhofer IRB Verlag, Stuttgart. — Modellgleichungen, `D_w`-Approximation,
  Sorptionsisotherme, `p_sat`
* Celia, M.A.; Bouloutas, E.T.; Zarba, R.L. (1990): *A general
  mass-conservative numerical solution for the unsaturated flow equation.*
  Water Resources Research 26(7). — modifizierte Picard-Iteration
* Patankar, S.V. (1980): *Numerical Heat Transfer and Fluid Flow.* —
  FVM-Diskretisierung, Quelltermlinearisierung
* EN 15026, EN ISO 13788, EN ISO 10211, EN ISO 6946, DIN 4108-3,
  DIN 68800-2, WTA 6-2 / 6-3 — Bewertungsgrößen und Randbedingungen
  (Zahlenwerte im Code als Näherung markiert und parametrierbar)
