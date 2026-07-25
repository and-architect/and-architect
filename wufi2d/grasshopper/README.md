# wufi2d in Grasshopper (Rhino 8/9)

Acht Skriptkomponenten, die zusammen einen vollständigen Ablauf bilden:
Geometrie → Material → Klima → Rand → Modell → Rechnen → Darstellen → Bewerten.

## Einmalige Einrichtung

1. In Grasshopper eine **Script**-Komponente ablegen und auf **Python 3**
   umstellen (Kontextmenü der Komponente).
2. Inhalt von `01_Setup.py` in den Editor kopieren.
3. Ein- und Ausgänge anlegen, wie im Kopf der Datei beschrieben — bei `01_Setup`:
   Eingänge `pfad`, `filter`; Ausgänge `info`, `materialien`, `kennwerte`.
4. `pfad` mit einem Panel verbinden, das auf den Ordner `…/wufi2d/src` zeigt.
5. Komponente ausführen. `info` meldet Version, Python-Version und ob SciPy
   vorhanden ist. Der Pfad wird im Dokument gespeichert
   (`scriptcontext.sticky`) — die übrigen Komponenten finden das Paket dann von
   selbst.

NumPy installiert der Script-Editor beim ersten Lauf über die Zeile
`# r: numpy` automatisch. SciPy ist optional (`# r: scipy` ergänzen); ohne
SciPy rechnet ein SOR-Verfahren, das nur NumPy braucht — langsamer, aber
ergebnisgleich (getestet).

Alternativ zum `pfad`-Eingang: Umgebungsvariable `WUFI2D_PATH` setzen.

## Die Komponenten

| Datei | Aufgabe | Wichtigste Eingänge |
|---|---|---|
| `01_Setup.py` | Pfad setzen, Materialliste | `pfad`, `filter` |
| `02_Region.py` | Kurven mit Material belegen | `kurven`, `material`, `loecher`, `prioritaet` |
| `03_Klima.py` | Außen-/Innenklima | `typ`, `temperatur`, `rf`, `datei`, `aussenklima` |
| `04_Rand.py` | Randbedingung je Oberfläche | `kurve` oder `seite`, `klima`, `typ`, `alpha`, `sd` |
| `05_Modell.py` | Gitter + Modell, Vorschau | `regionen`, `raender`, `zellgroesse`, `dauer_tage`, `dt_stunden` |
| `06_Rechnen.py` | Berechnung starten | `modell`, `rechnen`, `stationaer`, `speichern` |
| `07_Ergebnis.py` | farbiges Mesh, Isolinien | `ergebnis`, `groesse`, `zeit_tage`, `palette` |
| `08_Auswertung.py` | Bericht und Kennwerte | `ergebnis`, `oberflaeche`, `t_innen`, `t_aussen` |

Jede Datei listet im Kopf **alle** anzulegenden Ein- und Ausgänge mit Typ und
Zugriffsart (Item/List). `_bootstrap.py` ist keine Komponente, sondern der
gemeinsame Kopfblock zum Nachlesen.

Die Komponenten geben echte Python-Objekte weiter (Regionen, Klima, Modell,
Ergebnis) — sie müssen daher alle in derselben Rhino-Sitzung laufen. Wer
Zwischenstände auf Platte braucht: `06_Rechnen` schreibt über `speichern` eine
`.npz`-Datei, `07_Ergebnis` und `08_Auswertung` akzeptieren auch einen Dateipfad
statt des Objekts.

## Geometrieregeln

* Geschlossene Kurven **in der XY-Ebene**. Der Schnitt gilt je **1 m
  Bauteiltiefe**.
* Achsparallele Rechtecke sind die beste Wahl: alle Eckpunktkoordinaten werden
  zu Pflicht-Gitterlinien, Materialgrenzen liegen dann exakt auf Zellgrenzen.
* Schräge und gekrümmte Kurven sind erlaubt; sie werden über die Zellmittelpunkte
  in das Rechteckgitter eingepasst (Treppenapproximation) — dafür `zellgroesse`
  klein genug wählen.
* Überlappungen löst `prioritaet`: höherer Wert gewinnt (z.B. Betonrippe in der
  Dämmebene). Aussparungen (Hohlräume) über `loecher`.
* Millimeter- oder Zentimeter-Dokumente werden automatisch in Meter
  umgerechnet.

## Randbedingungen

* **Kurve** (empfohlen): die Oberfläche als Kurve zeichnen, `toleranz` ≈ halbe
  kleinste Zellgröße. `05_Modell` zeigt in `info`, wie viele Flächen und wie
  viele Meter jeder Randbedingung zugeordnet wurden — dort prüfen, ob die
  Zuordnung stimmt.
* **Seite**: `links`, `rechts`, `oben`, `unten` — für einfache Wandschnitte.
* Nicht zugeordnete Ränder sind **adiabat** (dampf- und wärmedicht). Für
  Schnittkanten eines Ausschnitts ist das richtig; wird eine Oberfläche
  versehentlich nicht getroffen, meldet `05_Modell` eine Warnung.

## Rechenzeit im Griff behalten

Die Rechnung läuft im Grasshopper-Thread — Rhino ist währenddessen blockiert.
Deshalb:

1. Erst mit `dauer_tage = 10` testen, ob Gitter und Ränder stimmen.
2. `dt_stunden = 2` bis `6` für Jahresrechnungen (Feuchte reagiert träge).
3. `ausgabe_h = 24` reicht meist; jede Ausgabe kostet Speicher.
4. Für Wärmebrückenkennwerte `stationaer = True` in `06_Rechnen` — das dauert
   Sekunden statt Minuten.
5. Lange Läufe headless rechnen und das Ergebnis laden:

   ```bash
   python -m wufi2d rechne modell.json --npz ergebnis.npz
   ```

   Ein in Grasshopper aufgebautes Modell lässt sich dafür speichern:
   `modell.save("modell.json")` in einer kleinen Zusatzkomponente.

## Darstellung

`07_Ergebnis` liefert ein Mesh mit **einer Fläche je Rechenzelle** und flacher
Färbung — so ist die Diskretisierung sichtbar. Die Farben sind Vertex-Farben:
Anzeigemodus **Schattiert** oder **Gerendert** verwenden. `legende` und
`grenzen` speisen eine eigene Legende (z.B. Text-Tags), `punkte` liefert
Isolinienpunkte zum Verbinden.
