# AutoTracker v2.0

GUI-Tool für automatische COLMAP-Photogrammetrie-Pipelines. Videos rein, Sparse-Rekonstruktion raus.

> Basiert auf der Arbeit von [@polyfjord](https://gist.github.com/polyfjord/4ed7e8988bdb9674145f1c270440200d)

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
| GPU | COLMAP Feature Extraction auf GPU (schneller) |
| Matching Overlap | Anzahl benachbarter Frames beim Sequential Matching |
| Max Image Size | Maximale Bildgröße für Feature Extraction (px) |
| Frame Subsampling | Jeden Frame / jeden 2. / jeden 3. / Custom FPS |

## Unterstützte Videoformate

`.mp4` `.mov` `.avi` `.mkv` `.mts` `.m4v` `.wmv` `.webm`

## Tests

```bash
pytest tests/
```
