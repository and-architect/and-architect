# AND Architect – Grasshopper Floorplan Plugin

Generiert 3-D-Grundrissvarianten in Grasshopper / Rhino 8 (Mac & Windows).
Räume werden automatisch nach Sonneneinstrahlung, Ausblick und Raumbeziehungen
ausgerichtet. Ein KI-Assistent (Claude / Anthropic) nimmt Textbefehle entgegen
und schlägt Layoutänderungen vor.

---

## Komponenten-Übersicht

```
AND Architect
├── 01 Setup
│   ├── AND_Room      – Raumdefinition (Fläche, Geschoss, Typ, Solar, Beziehungen)
│   ├── AND_Building  – Gebäude-Hülle (Grundriss, Geschosszahl, Geschosshöhe)
│   └── AND_Orient    – Orientierung (Nord-Vektor, Aussichtspunkte, Breitengrad)
├── 02 Generate
│   ├── AND_Gen       – Grundriss-Generator (3 D-Solver mit Scoring)
│   └── AND_Solar     – Sonnen-Studie (vereinfachte Einstrahlung pro Raum)
├── 03 AI
│   └── AND_AI        – KI-Assistent (Claude API, Textbefehle → Vorschläge)
└── 04 Visualize
    └── AND_Viz       – Visualisierung (Farbkodierung, Grundriss-Kurven, Labels)
```

---

## Voraussetzungen

| Software | Version |
|----------|---------|
| Rhino | 8.x (Mac oder Windows) |
| Grasshopper | integriert in Rhino 8 |
| .NET SDK | 7.0 |
| Anthropic API Key | optional – nur für AND_AI |

---

## Installation

### Schritt 1 – Plugin bauen

```bash
cd grasshopper-floorplan-plugin
chmod +x build.sh
./build.sh
```

Das Skript:
1. Baut das Plugin mit `dotnet build`
2. Benennt die DLL in `.gha` um
3. Kopiert sie in `~/Library/Application Support/McNeel/Rhinoceros/8.0/Plug-ins/Grasshopper/Libraries/`

### Schritt 2 – Rhino neu starten

Nach dem Neustart erscheinen die AND-Architect-Komponenten in der
Grasshopper-Toolbar unter **AND Architect**.

### Manuell installieren (ohne build.sh)

```bash
dotnet build AndArchitectGH.csproj -c Release
cp bin/Release/net7.0/AndArchitectGH.dll \
   "$HOME/Library/Application Support/McNeel/Rhinoceros/8.0/Plug-ins/Grasshopper/Libraries/AndArchitectGH.gha"
```

---

## Schnell-Start

Lies [`ExampleDefinition.md`](ExampleDefinition.md) für ein vollständiges
Schritt-für-Schritt-Beispiel mit allen Komponenten.

### Minimales Beispiel

```
AND_Room  → AND_Gen → AND_Viz
AND_Building →
```

### Mit KI

Verbinde AND_AI mit einem Text-Panel und einem Button.
Schreibe z.B.:

> „Das Wohnzimmer soll nach Süden zeigen, die Küche muss neben dem Esszimmer liegen."

Drücke den Button – Claude analysiert das aktuelle Layout und gibt
strukturierte Vorschläge zurück.

---

## Algorithmus

### Placement-Solver

Der Solver platziert Räume geschossweise auf einem 1-m-Raster.
Jede Raumposition wird nach vier Kriterien bewertet (gewichtet):

| Kriterium | Gewicht | Beschreibung |
|-----------|---------|--------------|
| Solar | 35 % | Abweichung von der gewünschten Himmelsrichtung |
| Ausblick | 25 % | Winkel zwischen Raumfassade und Aussichtspunkt |
| Beziehungen | 20 % | Entfernung zu Räumen in `MustBeNear`/`MustBeAway` |
| Position | 20 % | Globale Lage im Gebäude (z.B. Wohnraum → Süd) |

Drei Varianten entstehen mit unterschiedlichen Seitenverhältnissen
(1:1,4 / 1:1 / 1:1,7), sortiert nach Gesamt-Score.

### Sonnen-Studie

Einfaches geometrisches Modell: Azimut und Höhenwinkel werden für
jeden Stundenschritt nach astronomischen Formeln berechnet.
Für jeden Raum wird gezählt, wie viele Sonnen-Vektoren eine Außenfläche
treffen (Dot-Product > 0,15 ≈ >15° Einfallswinkel).

---

## KI-Integration (AND_AI)

Die Komponente sendet:
- **System-Prompt**: Architektur-Experte mit klarem JSON-Ausgabe-Format
- **Kontext**: Aktuelles Layout (Räume, Positionen, Gebäudedaten)
- **User-Prompt**: Ihr Text

Claude antwortet mit:
```json
{
  "suggestions": ["..."],
  "room_changes": [{"name":"...", "field":"...", "value":"...", "reason":"..."}],
  "global_changes": [{"field":"...", "value":"...", "reason":"..."}]
}
```

Der `Changes`-Output listet Änderungen als `Raum|Feld|Wert|Begründung` –
ideal zum Parsen mit einem GHPython-Script, das Ihre Panel-Werte automatisch
aktualisiert.

### API Key

```
ANTHROPIC_API_KEY=sk-ant-…  (Umgebungsvariable)
```

Oder direkt in den `K`-Eingang der AND_AI-Komponente (nutze dafür
eine `Secret`-Panel-Komponente, keine normale Text-Eingabe).

---

## Lizenz

MIT – freie Nutzung, Änderung und Weitergabe.
