# AutoTracker v2.1

GUI-Tool für automatische COLMAP-Photogrammetrie-Pipelines. Videos rein, Sparse-Rekonstruktion raus.

> Basiert auf der Arbeit von [@polyfjord](https://gist.github.com/polyfjord/4ed7e8988bdb9674145f1c270440200d)

## Changelog

### v2.1
- **Shot Presets** — Dropdown mit optimierten Settings für verschiedene Shot-Typen (Klippe/weiter Hintergrund, Interior, Drohne, Handheld)
- **Brennweite** — Automatische Erkennung aus Video-Metadaten + manuelles Eingabefeld (35mm-Äquivalent); wird als Prior an COLMAP übergeben für bessere Rekonstruktionsqualität
- **FPS-Info** — Video-FPS wird im Log angezeigt + `blender_info.txt` im Scene-Ordner für korrekten Blender-Import
- **Bugfix** — `view_graph_calibrator` erhielt falsches `--image_path` Flag → entfernt
- **Bugfix** — Start-Button verschwand bei langen Dateipfaden → Pfad wird jetzt truncated angezeigt
- **Overlap-Slider** — Maximum von 30 auf 60 erhöht (nötig für Shots mit weitem Hintergrund)

## Pipeline

Für jedes Video im gewählten Ordner:
1. **Frame Extraction** — ffmpeg extrahiert JPG-Frames
2. **Feature Extraction** — COLMAP SIFT (GPU oder CPU)
3. **Sequential Matching** — Feature-Matching mit konfigurierbarem Overlap
4. **View Graph Calibration** — Kamerakalibration
5. **Global Mapper** — Globale Rekonstruktion (GLOMAP)
6. **TXT Export** — Sparse-Modell als TXT

Output landet im `scenes/`-Ordner neben dem `videos/`-Ordner.

## Download (fertige .exe)

→ [Releases](https://github.com/edisonALP/colmar_autotracker/releases)

ZIP entpacken, `AutoTracker.exe` starten. Fertig — kein Python nötig.

Die COLMAP-Binaries und ffmpeg sind im Release bereits enthalten.

## Aus dem Source bauen

### Voraussetzungen

- Python 3.11+
- COLMAP 4.x Windows-Binaries → in `../01 GLOMAP/` entpacken (so dass `../01 GLOMAP/colmap.exe` existiert)
- ffmpeg Windows-Binaries → in `../03 FFMPEG/bin/` entpacken (so dass `../03 FFMPEG/bin/ffmpeg.exe` existiert)

**COLMAP herunterladen:** https://github.com/colmap/colmap/releases  
**ffmpeg herunterladen:** https://www.gyan.dev/ffmpeg/builds/ (ffmpeg-release-essentials)

### Installation

```bash
pip install -r requirements.txt
```

### Starten

```bash
python main.py
```

### .exe bauen

```bash
build.bat
```

Erzeugt `dist\AutoTracker\AutoTracker.exe` + `dist\AutoTracker.zip`.

## Ordnerstruktur (Source)

```
COLMAR\
├── 01 GLOMAP\          # COLMAP-Binaries (nicht im Repo)
│   └── colmap.exe
├── 03 FFMPEG\          # ffmpeg-Binaries (nicht im Repo)
│   └── bin\
│       ├── ffmpeg.exe
│       └── ffprobe.exe
└── 06 GUI\             # Dieses Repo
    ├── main.py
    ├── pipeline.py
    ├── requirements.txt
    ├── autotracker.spec
    ├── build.bat
    └── tests\
```

## Einstellungen

| Einstellung | Beschreibung |
|---|---|
| Shot Preset | Vordefinierte Settings für verschiedene Shot-Typen (Standard, Klippe/weiter Hintergrund, Interior, Drohne, Handheld) |
| GPU | COLMAP Feature Extraction auf GPU (schneller) |
| Matching Overlap | Anzahl benachbarter Frames beim Sequential Matching (1–60) |
| Max Image Size | Maximale Bildgröße für Feature Extraction (px) |
| Brennweite (35mm) | 35mm-Äquivalent der Kamera/Linse — leer lassen für Auto-Erkennung aus Metadaten |
| Frame Subsampling | Jeden Frame / jeden 2. / jeden 3. / Custom FPS |

### Shot Presets

| Preset | Overlap | Tri Min Angle | Empfohlen für |
|---|---|---|---|
| Standard | 15 | 1.0° | Allgemein |
| Klippe / Weiter Hintergrund | 45 | 0.5° | Shots mit Person vorne + weitem Hintergrund |
| Interior / Nahaufnahme | 10 | 2.0° | Innenräume, Makro |
| Drohne / Luftaufnahme | 30 | 0.5° | Aerial Footage |
| Handheld / Schnellschnitt | 20 | 1.5° | Schnell bewegte Kamera |

## Unterstützte Videoformate

`.mp4` `.mov` `.avi` `.mkv` `.mts` `.m4v` `.wmv` `.webm`

## Tests

```bash
pytest tests/
```
