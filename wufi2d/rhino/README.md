# wufi2d in Rhino 8/9 (ohne Grasshopper)

Zwei Befehlsskripte für den interaktiven Gebrauch:

| Skript | Aufgabe |
|---|---|
| `WufiSchnellstart.py` | kompletter Ablauf: Kurven wählen → Materialien zuordnen → Oberflächen → Klima → rechnen → farbiges Mesh |
| `WufiErgebnisAnzeigen.py` | gespeicherte `.npz`-Ergebnisse (oder das letzte Ergebnis der Sitzung) darstellen, mehrere Zeitpunkte gestapelt |

## Starten

Direkt über die Befehlszeile:

```
_-RunPythonScript "C:\Pfad\zu\wufi2d\rhino\WufiSchnellstart.py"
```

Beim ersten Start fragt das Skript nach dem Ordner `wufi2d/src`, falls er nicht
über die Umgebungsvariable `WUFI2D_PATH` oder eine frühere Grasshopper-Sitzung
bekannt ist. Der Pfad wird im Dokument gemerkt.

## Als benannter Befehl einrichten

**Variante A — Alias** (schnell): *Werkzeuge → Optionen → Aliase*, neuen Alias
anlegen:

| Alias | Befehlsmakro |
|---|---|
| `Wufi` | `_-RunPythonScript "C:\Pfad\zu\wufi2d\rhino\WufiSchnellstart.py"` |
| `WufiZeigen` | `_-RunPythonScript "C:\Pfad\zu\wufi2d\rhino\WufiErgebnisAnzeigen.py"` |

Danach genügt die Eingabe von `Wufi` in der Befehlszeile.

**Variante B — Schaltfläche:** eine Werkzeugkasten-Schaltfläche anlegen und
dasselbe Makro eintragen.

**Variante C — Script-Editor:** Datei im Rhino-Script-Editor öffnen
(`_ScriptEditor`) und von dort ausführen; der Editor installiert NumPy über die
Zeile `# r: numpy` beim ersten Lauf automatisch.

## Ablauf von WufiSchnellstart

1. **Kurven wählen** — geschlossene Kurven des Bauteilschnitts in der XY-Ebene.
   Nicht geschlossene Kurven werden gemeldet und übersprungen.
2. **Material je Kurve** — Auswahlliste aus der Richtwert-Datenbank. Die jeweils
   bearbeitete Kurve wird währenddessen markiert.
3. **Diskretisierung** — größte und kleinste Zellabmessung in Millimetern.
4. **Oberflächen** — je Seite entweder eine Kurve wählen oder eine Bauteilseite
   (`links`/`rechts`/`oben`/`unten`). Nicht zugeordnete Ränder bleiben adiabat.
5. **Klima** — konstant oder Jahresgang (Sinus), Innenklima konstant.
6. **Dauer, Zeitschritt, Anfangszustand.**
7. Vor dem Start werden Zellzahl und Zeitschrittzahl angezeigt — Rhino ist
   während der Rechnung blockiert, der Fortschritt erscheint in der
   Befehlszeile.
8. Das Ergebnis wird als Mesh auf dem Layer **WUFI Ergebnis** abgelegt und kann
   als `.npz` gespeichert werden.

## Hinweise

* Die Farben sind Vertex-Farben: Anzeigemodus **Schattiert** oder **Gerendert**.
* Millimeter- und Zentimeter-Dokumente werden automatisch umgerechnet; das Mesh
  entsteht wieder in Dokumenteinheiten.
* Für Parameterstudien, Jahresrechnungen mit feinem Gitter und alles, was länger
  dauert, ist die Kommandozeile die bessere Wahl:

  ```bash
  python -m wufi2d rechne modell.json --npz ergebnis.npz --csv verlauf.csv
  ```

  Das Ergebnis lässt sich anschließend mit `WufiErgebnisAnzeigen.py` in Rhino
  darstellen.
* Mehr Steuerung (Schlagregen, Strahlung, `s_d`-Werte, feuchtevariable
  Dampfbremsen, tabellierte Klimadaten, eigene Materialien) bietet der
  Grasshopper-Ablauf oder die Python-API — siehe `../README.md`.
