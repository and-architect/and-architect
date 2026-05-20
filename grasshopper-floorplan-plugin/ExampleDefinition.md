# AND Architect – Beispiel-Grasshopper-Definition

## Minimal-Setup (Schritt für Schritt)

### 1 · Räume definieren

Jeder Raum braucht mindestens Name und Fläche.
Verbinde mehrere `AND_Room`-Komponenten mit einer `Merge`-Liste.

```
AND_Room  ──  N = "Wohnzimmer"  A = 30  FL = 0  T = LivingRoom
AND_Room  ──  N = "Küche"       A = 14  FL = 0  T = Kitchen
AND_Room  ──  N = "Esszimmer"   A = 16  FL = 0  T = DiningRoom  NR = ["Küche"]
AND_Room  ──  N = "Schlafzimmer"A = 18  FL = 1  T = MasterBedroom
AND_Room  ──  N = "Kinderzimmer"A = 14  FL = 1  T = ChildRoom
AND_Room  ──  N = "Bad"         A = 8   FL = 1  T = Bathroom     S = North
AND_Room  ──  N = "Büro"        A = 12  FL = 1  T = Office       S = North
AND_Room  ──  N = "Flur EG"     A = 8   FL = 0  T = Hallway
AND_Room  ──  N = "Flur OG"     A = 6   FL = 1  T = Hallway
```

### 2 · Gebäude-Hülle

```
AND_Building  ──  W = 12  D = 10  FL = 2  FH = 3.0
                  → Building (B)
                  → Envelope Brep (E)  ← preview in Rhino
                  → GFA (m²)
```

Alternativ: Schließe eine eigene Grundriss-Kurve (Polygon) an den `FP`-Eingang.

### 3 · Orientierung

```
AND_Orient  ──  North = (0,1,0)   ← Y+ = Norden
                Lat   = 48.1      ← München
                VP    = [pt1, pt2] ← Sicht auf Alpen
                → Orientation (O)
                → South/East/West-Vektoren
                → Wintersonnenwende-Sonnenstand [°]
```

### 4 · Grundriss generieren

```
[Rooms Merge] → AND_Gen ─── V = 3   (3 Varianten)
AND_Building  →             S = 0   (Variante 0 = beste Score)
AND_Orient    →
                → Geometry (Breps)  ← farbig in Rhino
                → Labels
                → Centres
                → Scores            ← pro Raum [0,1]
                → VariantScore
                → Report            ← Text-Panel
                → AllBreps          ← alle 3 Varianten nebeneinander
```

Nutze einen **Number Slider** (0–2) am `S`-Eingang um zwischen den drei
Varianten umzuschalten — die Geometrie aktualisiert sich sofort.

### 5 · Sonnen-Studie

```
AND_Gen → Geometry → AND_Solar ─── Hours = 8  Winter = true
AND_Gen → Labels   →               Orient = O
                      → SolarScores  ← Liste [0,1] pro Raum
                      → Report       ← Text-Panel
```

Verbinde `SolarScores` mit einem `GH_CustomPreview` und einem Gradient,
um die Räume nach Sonneneinstrahlung einzufärben.

### 6 · KI-Assistent

```
[Text Panel "Verlagere das Schlafzimmer nach Süden …"] → AND_AI ─── K = "sk-ant-…"
[Rooms Merge]  →                                                    S = [Button]
AND_Building   →
AND_Orient     →
                → Response    (Text-Panel)
                → Suggestions (Liste)
                → Changes     (Liste "Raum|Feld|Wert|Begründung")
                → JSON        (roher JSON-Block)
```

Drücke den **Button** am `S`-Eingang. Claude analysiert das aktuelle
Layout und gibt konkrete Änderungsvorschläge zurück, z.B.:

```
Wohnzimmer|SolarPref|South|Maximale Wintersonnen-Exposition im Süden
Küche|MustBeNear|["Esszimmer"]|Kurze Wege zwischen Küche und Essen
GLOBAL|Floors|3|Dritter Stock entlastet Grundriss und ermöglicht mehr Privatheit
```

### 7 · Visualisierung

```
AND_Gen → Geometry  → AND_Viz ─── FH = 3.0  ShowAll = true
AND_Gen → Labels    →
AND_Gen → Centres   →
                      → Rooms       (Breps, gefiltert)
                      → FloorPlates (Grundrisscurves für 2-D-Zeichnung)
                      → LabelPts    → TextTag3d-Komponente
                      → LabelText   → TextTag3d-Komponente
                      → ColourR/G/B → Custom Preview
```

## Tipps

| Ziel | Vorgehen |
|------|----------|
| Grundriss als Plan drucken | `FloorPlates`-Kurven → `Make2D` → Export DXF |
| IFC-Export | Breps → `BrepToIfc` (VisualARQ-Plugin) |
| Weitere Varianten | Slider `V` in AND_Gen auf 5–10 stellen |
| Andere Gebäudeform | L-Form als Polygon-Kurve an `FP`-Eingang |
| Ohne API-Key testen | AND_AI weglassen, Send=False lassen |
| Raumbeziehungen | `NR`-Eingang (NearRooms) als Text-Liste; Räume müssen gleich heißen |
