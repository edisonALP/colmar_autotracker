import json
import os
import re
import sys
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".mts", ".m4v", ".wmv", ".webm"}


def sanitize_name(name: str) -> str:
    """Replace characters that break ffmpeg path parsing on Windows."""
    return re.sub(r"[^\w\-.]", "_", name)


@dataclass
class PipelineSettings:
    videos_dir: str
    use_gpu: bool = True
    overlap: int = 15
    max_image_size: int = 4096
    subsampling: str = "every_frame"  # every_frame | every_2nd | every_3rd | custom_fps
    custom_fps: int = 10
    tri_min_angle: float = 1.0
    focal_length_35mm: float | None = None  # None = COLMAP schätzt selbst


@dataclass
class BinaryPaths:
    colmap: str
    ffmpeg: str


def get_app_dir() -> str:
    if getattr(sys, "frozen", False):
        # PyInstaller 6+ puts bundled datas in _MEIPASS (_internal/), not beside the exe
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_binaries(app_dir: str = None) -> "BinaryPaths | None":
    base = app_dir or get_app_dir()
    dev_base = os.path.dirname(base)

    colmap = _first_existing([
        os.path.join(base, "colmap", "colmap.exe"),
        os.path.join(dev_base, "01 GLOMAP", "colmap.exe"),
    ])
    ffmpeg = _first_existing([
        os.path.join(base, "ffmpeg", "ffmpeg.exe"),
        os.path.join(base, "ffmpeg", "bin", "ffmpeg.exe"),
        os.path.join(dev_base, "03 FFMPEG", "ffmpeg.exe"),
        os.path.join(dev_base, "03 FFMPEG", "bin", "ffmpeg.exe"),
    ])

    if not colmap or not ffmpeg:
        return None
    return BinaryPaths(colmap=colmap, ffmpeg=ffmpeg)


def _first_existing(paths: list) -> str | None:
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


def get_video_resolution(ffprobe_exe: str, video_path: str):
    """Returns (width, height) tuple or None on failure."""
    cmd = [
        ffprobe_exe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0 or not result.stdout.strip():
            return None
        parts = result.stdout.strip().split(",")
        if len(parts) < 2:
            parts = result.stdout.strip().split("x")
        if len(parts) < 2:
            return None
        return int(parts[0]), int(parts[1])
    except Exception:
        return None


def suggest_max_image_size(width: int) -> int:
    """Returns smallest of 1024/2048/4096 that is >= width, capped at 4096."""
    for size in [1024, 2048, 4096]:
        if width <= size:
            return size
    return 4096


STEP_NAMES = [
    "Frame Extraction",
    "Feature Extraction",
    "Matching",
    "View Graph Calibration",
    "Global Mapper",
    "TXT Export",
]
TOTAL_STEPS = len(STEP_NAMES)


class PipelineRunner:
    def __init__(
        self,
        settings: PipelineSettings,
        bins: BinaryPaths,
        log_cb: Callable[[str, str], None],
        progress_cb: Callable[[str, int, int], None],
        done_cb: Callable[[], None],
        sub_progress_cb: Callable[[float, str], None] | None = None,
    ):
        self.settings = settings
        self.bins = bins
        self.log_cb = log_cb
        self.progress_cb = progress_cb
        self.done_cb = done_cb
        self.sub_progress_cb = sub_progress_cb or (lambda v, t: None)
        self._stop_event = threading.Event()
        self._current_proc = None

    def stop(self):
        self._stop_event.set()
        if self._current_proc:
            self._current_proc.terminate()

    def run(self):
        videos_dir = Path(self.settings.videos_dir)
        videos = [f for f in videos_dir.iterdir()
                  if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS]
        for video in videos:
            if self._stop_event.is_set():
                break
            self._process_video(video)
        if not self._stop_event.is_set():
            self.done_cb()

    def _process_video(self, video: Path):
        scenes_dir = video.parent.parent / "scenes"
        base_name = sanitize_name(video.stem)
        scene = scenes_dir / base_name
        if scene.exists():
            i = 1
            while (scenes_dir / f"{base_name}_{i}").exists():
                i += 1
            scene = scenes_dir / f"{base_name}_{i}"
        img_dir = scene / "images"
        sparse_dir = scene / "sparse"

        img_dir.mkdir(parents=True)
        sparse_dir.mkdir(parents=True)

        fps = self._get_video_fps(str(video))
        focal_35mm = self.settings.focal_length_35mm or self._get_focal_length_from_metadata(str(video))
        self._resolved_focal_35mm = focal_35mm

        if fps:
            self.log_cb(
                f"[INFO] Video FPS: {fps} → Blender Scene FPS auf {fps} setzen vor Import!",
                "ok",
            )
        if focal_35mm:
            source = "Metadaten" if not self.settings.focal_length_35mm else "Manuell"
            self.log_cb(f"[INFO] Brennweite: {focal_35mm}mm (35mm-Äquiv.) [{source}]", "ok")
        else:
            self.log_cb("[WARNUNG] Brennweite unbekannt – COLMAP schätzt selbst (niedriger Quality)", "info")

        (scene / "blender_info.txt").write_text(
            f"Video: {video.name}\n"
            f"FPS: {fps or 'unbekannt'}\n"
            f"Brennweite (35mm): {focal_35mm or 'unbekannt'}\n"
            f"\n"
            f"Blender Setup:\n"
            f"  1. Scene Properties → Frame Rate → {fps or '?'}\n"
            f"  2. Dann Tracking-Daten importieren\n",
            encoding="utf-8",
        )

        steps = [
            (self._run_ffmpeg, [str(video), str(img_dir)]),
            (self._run_feature_extractor, [str(scene), str(img_dir)]),
            (self._run_matcher, [str(scene)]),
            (self._run_view_graph_calibrator, [str(scene), str(img_dir)]),
            (self._run_global_mapper, [str(scene), str(img_dir), str(sparse_dir)]),
            (self._run_model_converter, [str(sparse_dir)]),
        ]

        for i, (fn, args) in enumerate(steps):
            if self._stop_event.is_set():
                return
            self.progress_cb(video.name, i + 1, TOTAL_STEPS)
            ok = fn(*args)
            if not ok:
                self.log_cb(f"[FEHLER] Schritt {i+1} fehlgeschlagen - ueberspringe {video.name}", "error")
                return

        self.log_cb(f"[OK] {video.name} fertig", "ok")

    def _get_ffprobe(self) -> str | None:
        ffprobe = os.path.join(os.path.dirname(self.bins.ffmpeg), "ffprobe.exe")
        return ffprobe if os.path.isfile(ffprobe) else None

    def _get_video_duration(self, video: str) -> float | None:
        ffprobe = self._get_ffprobe()
        if not ffprobe:
            return None
        cmd = [ffprobe, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=duration", "-of", "csv=p=0", video]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            val = result.stdout.strip()
            return float(val) if val else None
        except Exception:
            return None

    def _get_focal_length_from_metadata(self, video: str) -> float | None:
        """Try to extract 35mm-equivalent focal length from video stream metadata."""
        ffprobe = self._get_ffprobe()
        if not ffprobe:
            return None
        cmd = [ffprobe, "-v", "quiet", "-print_format", "json",
               "-show_streams", "-show_format", video]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            data = json.loads(result.stdout)
        except Exception:
            return None

        # Search common metadata tag names for focal length
        tag_names = [
            "com.apple.quicktime.camera.focal_length",
            "focal_length", "FocalLength", "Focal_Length",
            "focalLength", "FOCAL_LENGTH",
        ]
        sources = []
        for stream in data.get("streams", []):
            sources.append(stream.get("tags", {}))
        sources.append(data.get("format", {}).get("tags", {}))

        for tags in sources:
            for key in tag_names:
                val = tags.get(key)
                if val is not None:
                    try:
                        return float(str(val).split("/")[0]) / float(str(val).split("/")[1]) \
                            if "/" in str(val) else float(val)
                    except Exception:
                        continue
        return None

    def _get_video_fps(self, video: str) -> float | None:
        ffprobe = self._get_ffprobe()
        if not ffprobe:
            return None
        cmd = [ffprobe, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", video]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            val = result.stdout.strip()
            if not val:
                return None
            if "/" in val:
                num, den = val.split("/")
                return round(int(num) / int(den), 3) if int(den) else None
            return float(val)
        except Exception:
            return None

    def _run(self, cmd: list, line_cb=None) -> bool:
        self.log_cb(f"    > {' '.join(cmd[:3])}...", "info")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self._current_proc = proc
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.log_cb(line, "info")
                    if line_cb:
                        line_cb(line)
                if self._stop_event.is_set():
                    proc.terminate()
                    return False
            proc.wait()
            self._current_proc = None
            return proc.returncode == 0
        except Exception as e:
            self.log_cb(f"[FEHLER] {e}", "error")
            return False

    def _ffmpeg_cmd(self, video: str, img_dir: str) -> list:
        cmd = [self.bins.ffmpeg, "-loglevel", "error", "-stats", "-i", video]
        s = self.settings.subsampling
        if s == "every_2nd":
            cmd += ["-vf", r"select=not(mod(n\,2))", "-vsync", "vfr"]
        elif s == "every_3rd":
            cmd += ["-vf", r"select=not(mod(n\,3))", "-vsync", "vfr"]
        elif s == "custom_fps":
            cmd += ["-vf", f"fps={self.settings.custom_fps}"]
        cmd += ["-qscale:v", "2", f"{img_dir}/frame_%06d.jpg"]
        return cmd

    def _make_ffmpeg_line_cb(self, duration: float):
        _time_re = re.compile(r'time=(\d+):(\d+):(\d+(?:\.\d+)?)')
        _frame_re = re.compile(r'frame=\s*(\d+)')
        def cb(line: str):
            m = _time_re.search(line)
            if not m:
                return
            h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            current = h * 3600 + mn * 60 + s
            pct = min(current / duration, 1.0) if duration > 0 else 0.0
            fm = _frame_re.search(line)
            text = f"Frame {fm.group(1)}" if fm else ""
            self.sub_progress_cb(pct, text)
        return cb

    def _run_ffmpeg(self, video: str, img_dir: str) -> bool:
        self.log_cb("[1/6] Extrahiere Frames...", "info")
        duration = self._get_video_duration(video)
        line_cb = self._make_ffmpeg_line_cb(duration) if duration else None
        if not duration:
            self.sub_progress_cb(-1.0, "")
        result = self._run(self._ffmpeg_cmd(video, img_dir), line_cb=line_cb)
        self.sub_progress_cb(1.0 if result else 0.0, "")
        return result

    def _run_feature_extractor(self, scene: str, img_dir: str) -> bool:
        self.log_cb("[2/6] Feature Extraction...", "info")
        self.sub_progress_cb(-1.0, "")
        cmd = [
            self.bins.colmap, "feature_extractor",
            "--database_path", f"{scene}/database.db",
            "--image_path", img_dir,
            "--ImageReader.single_camera", "1",
            "--FeatureExtraction.use_gpu", "1" if self.settings.use_gpu else "0",
            "--FeatureExtraction.max_image_size", str(self.settings.max_image_size),
        ]
        focal_35mm = getattr(self, "_resolved_focal_35mm", None)
        if focal_35mm:
            # Focal length in pixels: f_px = f_35mm * image_width / 36.0
            # Use max_image_size as width proxy; COLMAP rescales internally
            f_px = focal_35mm * self.settings.max_image_size / 36.0
            cmd += [
                "--ImageReader.camera_model", "SIMPLE_RADIAL",
                "--ImageReader.camera_params", f"{f_px:.2f},0,0,0",
            ]
        return self._run(cmd)

    def _run_matcher(self, scene: str) -> bool:
        self.log_cb("[3/6] Matching...", "info")
        self.sub_progress_cb(-1.0, "")
        cmd = [
            self.bins.colmap, "sequential_matcher",
            "--database_path", f"{scene}/database.db",
            "--SequentialMatching.overlap", str(self.settings.overlap),
        ]
        return self._run(cmd)

    def _run_view_graph_calibrator(self, scene: str, img_dir: str) -> bool:
        self.log_cb("[4/6] View Graph Calibration...", "info")
        self.sub_progress_cb(-1.0, "")
        cmd = [
            self.bins.colmap, "view_graph_calibrator",
            "--database_path", f"{scene}/database.db",
        ]
        self._run(cmd)
        return True  # non-fatal

    def _run_global_mapper(self, scene: str, img_dir: str, sparse_dir: str) -> bool:
        self.log_cb("[5/6] Global Mapper...", "info")
        self.sub_progress_cb(-1.0, "")
        cmd = [
            self.bins.colmap, "global_mapper",
            "--database_path", f"{scene}/database.db",
            "--image_path", img_dir,
            "--output_path", sparse_dir,
            "--GlobalMapper.tri_min_angle", str(self.settings.tri_min_angle),
        ]
        return self._run(cmd)

    def _run_model_converter(self, sparse_dir: str) -> bool:
        self.log_cb("[6/6] TXT Export...", "info")
        self.sub_progress_cb(-1.0, "")
        model = f"{sparse_dir}/0"
        if not Path(model).exists():
            self.log_cb("[WARNUNG] Kein Modell in sparse/0 - Export uebersprungen", "info")
            return True
        for out in [model, sparse_dir]:
            cmd = [
                self.bins.colmap, "model_converter",
                "--input_path", model,
                "--output_path", out,
                "--output_type", "TXT",
            ]
            self._run(cmd)
        return True
