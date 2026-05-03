import os
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
import customtkinter as ctk
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

from pipeline import PipelineSettings, PipelineRunner, find_binaries, STEP_NAMES, TOTAL_STEPS, get_video_resolution, suggest_max_image_size

# VS Code Dark colors
BG = "#1e1e1e"
PANEL = "#252526"
BORDER = "#3c3c3c"
ACCENT = "#0e639c"
LABEL = "#9cdcfe"
TEXT = "#d4d4d4"
OK_COLOR = "#4ec9b0"
INFO_COLOR = "#569cd6"
ERR_COLOR = "#f44747"
STATUS_BG = "#007acc"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SHOT_PRESETS = {
    "Standard": {"overlap": 15, "tri_min_angle": 1.0},
    "Klippe / Weiter Hintergrund": {"overlap": 45, "tri_min_angle": 0.5},
    "Interior / Nahaufnahme": {"overlap": 10, "tri_min_angle": 2.0},
    "Drohne / Luftaufnahme": {"overlap": 30, "tri_min_angle": 0.5},
    "Handheld / Schnellschnitt": {"overlap": 20, "tri_min_angle": 1.5},
}


class AutoTrackerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        if HAS_DND:
            TkinterDnD._require(self)
        self.title("AutoTracker v2.0")
        self.geometry("900x700")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        self.bins = find_binaries()
        if self.bins is None:
            messagebox.showerror(
                "Fehler",
                "colmap.exe oder ffmpeg.exe nicht gefunden.\n"
                "Stellen Sie sicher, dass colmap\\ und ffmpeg\\ neben der .exe liegen."
            )
            self.destroy()
            return

        self._runner = None
        self._thread = None

        self._build_ui()

    def _build_ui(self):
        # Title bar
        title_bar = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=36)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)
        ctk.CTkLabel(title_bar, text="⚙  AutoTracker v2.0", text_color=INFO_COLOR,
                     font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=14)
        ctk.CTkLabel(title_bar, text="COLMAP 4.x Pipeline", text_color="#888888",
                     font=ctk.CTkFont(size=11)).pack(side="right", padx=14)

        # Status bar
        self._status_bar = ctk.CTkFrame(self, fg_color=STATUS_BG, corner_radius=0, height=22)
        self._status_bar.pack(fill="x", side="bottom")
        self._status_bar.pack_propagate(False)
        self._status_left = ctk.CTkLabel(self._status_bar, text="Bereit", text_color="white",
                                          font=ctk.CTkFont(size=10))
        self._status_left.pack(side="left", padx=10)
        self._status_right = ctk.CTkLabel(self._status_bar, text="COLMAP 4.x  ·  GPU aktiv",
                                           text_color="white", font=ctk.CTkFont(size=10))
        self._status_right.pack(side="right", padx=10)

        # Main content area
        content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        content.pack(fill="both", expand=True)

        # Create progress panel first so it can be passed to settings panel
        self._progress_panel = ProgressPanel(content)
        self._progress_panel.pack(side="right", fill="both", expand=True)

        separator = ctk.CTkFrame(content, fg_color=BORDER, width=1, corner_radius=0)
        separator.pack(side="right", fill="y")

        self._settings_panel = SettingsPanel(content, self._on_start_stop, self._progress_panel)
        self._settings_panel.pack(side="left", fill="y", padx=0, pady=0)

    def _on_start_stop(self):
        if self._runner and self._thread and self._thread.is_alive():
            self._runner.stop()
            self._runner = None
            self._settings_panel.set_running(False)
            self._status_left.configure(text="Gestoppt")
        else:
            settings = self._settings_panel.get_settings()
            self._runner = PipelineRunner(
                settings=settings,
                bins=self.bins,
                log_cb=self._on_log,
                progress_cb=self._on_progress,
                done_cb=self._on_done,
                sub_progress_cb=self._on_sub_progress,
            )
            self._thread = threading.Thread(target=self._runner.run, daemon=True)
            self._thread.start()
            self._settings_panel.set_running(True)
            self._status_left.configure(text="Läuft...")
            self._progress_panel.clear()

    def _on_log(self, message: str, level: str):
        self.after(0, self._progress_panel.append_log, message, level)

    def _on_progress(self, video_name: str, step: int, total: int):
        step_name = STEP_NAMES[step - 1] if step <= len(STEP_NAMES) else ""
        self.after(0, self._progress_panel.set_progress, video_name, step, total, step_name)
        self.after(0, self._status_left.configure, {"text": f"Läuft: {video_name}"})

    def _on_sub_progress(self, value: float, text: str):
        self.after(0, self._progress_panel.set_sub_progress, value, text)

    def _on_done(self):
        self.after(0, self._settings_panel.set_running, False)
        self.after(0, self._status_left.configure, {"text": "Fertig!"})
        self.after(0, self._progress_panel.append_log, "=== Alle Videos fertig ===", "ok")


class SettingsPanel(ctk.CTkFrame):
    def __init__(self, parent, start_stop_cb, progress_panel_ref=None):
        super().__init__(parent, fg_color=PANEL, corner_radius=0, width=220)
        self.pack_propagate(False)
        self._start_stop_cb = start_stop_cb
        self._progress_panel_ref = progress_panel_ref
        self._build()

    def _build(self):
        pad = {"padx": 14, "pady": (6, 0)}

        # Video folder
        ctk.CTkLabel(self, text="VIDEO ORDNER", text_color=LABEL,
                     font=ctk.CTkFont(size=10)).pack(anchor="w", **pad)

        # Drop zone
        self._folder_var = tk.StringVar(value=os.path.join(os.getcwd(), "videos"))
        self._drop_zone = tk.Frame(
            self, bg=BG, relief="flat",
            highlightbackground=BORDER, highlightthickness=1,
            cursor="hand2",
        )
        self._drop_zone.pack(fill="x", padx=14, pady=(4, 0))

        self._drop_icon = tk.Label(
            self._drop_zone, text="📂", bg=BG, fg=ACCENT,
            font=("Segoe UI Emoji", 14),
        )
        self._drop_icon.pack(pady=(6, 1))

        self._drop_hint = tk.Label(
            self._drop_zone, text="Ordner hier reinziehen", bg=BG, fg="#888888",
            font=("Consolas", 9),
        )
        self._drop_hint.pack()

        self._drop_path = tk.Label(
            self._drop_zone, text=self._truncate_path(self._folder_var.get()),
            bg=BG, fg=TEXT, font=("Consolas", 8), wraplength=170, justify="center",
        )
        self._drop_path.pack(pady=(2, 2))

        browse_btn = tk.Button(
            self._drop_zone, text="📁  Durchsuchen", bg=PANEL, fg=ACCENT,
            activebackground=BORDER, activeforeground=ACCENT,
            relief="flat", bd=0, font=("Consolas", 9), cursor="hand2",
            command=self._pick_folder,
        )
        browse_btn.pack(pady=(0, 6))

        # Drag-and-drop binding
        if HAS_DND:
            for widget in (self._drop_zone, self._drop_icon, self._drop_hint,
                           self._drop_path, browse_btn):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)
                widget.dnd_bind("<<DragEnter>>", self._on_drag_enter)
                widget.dnd_bind("<<DragLeave>>", self._on_drag_leave)

        # Click whole zone to browse
        self._drop_zone.bind("<Button-1>", lambda e: self._pick_folder())
        self._drop_icon.bind("<Button-1>", lambda e: self._pick_folder())
        self._drop_hint.bind("<Button-1>", lambda e: self._pick_folder())

        # Divider + label
        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).pack(
            fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(self, text="SHOT PRESET", text_color=LABEL,
                     font=ctk.CTkFont(size=10)).pack(anchor="w", **pad)
        self._preset_var = tk.StringVar(value="Standard")
        self._tri_min_angle = 1.0
        ctk.CTkOptionMenu(self, values=list(SHOT_PRESETS.keys()),
                          variable=self._preset_var,
                          fg_color=BG, button_color=BORDER, button_hover_color=ACCENT,
                          text_color=TEXT,
                          command=self._on_preset_change).pack(
            fill="x", padx=14, pady=(4, 0))

        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).pack(
            fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(self, text="EINSTELLUNGEN", text_color=LABEL,
                     font=ctk.CTkFont(size=10)).pack(anchor="w", **pad)

        # GPU toggle
        gpu_row = ctk.CTkFrame(self, fg_color="transparent")
        gpu_row.pack(fill="x", padx=14, pady=(6, 0))
        ctk.CTkLabel(gpu_row, text="GPU", text_color=TEXT,
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self._gpu_var = tk.BooleanVar(value=True)
        ctk.CTkSwitch(gpu_row, variable=self._gpu_var, text="",
                      onvalue=True, offvalue=False,
                      button_color=ACCENT, progress_color=ACCENT).pack(side="right")

        # Overlap slider
        ctk.CTkLabel(self, text="Matching Overlap", text_color=TEXT,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=14, pady=(8, 0))
        overlap_row = ctk.CTkFrame(self, fg_color="transparent")
        overlap_row.pack(fill="x", padx=14, pady=(2, 0))
        self._overlap_var = tk.IntVar(value=15)
        self._overlap_label = ctk.CTkLabel(overlap_row, text="15", text_color=ACCENT,
                                            font=ctk.CTkFont(size=11), width=24)
        self._overlap_label.pack(side="right")
        ctk.CTkSlider(overlap_row, from_=1, to=60, number_of_steps=59,
                      variable=self._overlap_var,
                      button_color=ACCENT, progress_color=ACCENT,
                      command=lambda v: self._overlap_label.configure(text=str(int(v)))
                      ).pack(side="left", fill="x", expand=True)

        # Max image size
        size_row = ctk.CTkFrame(self, fg_color="transparent")
        size_row.pack(fill="x", padx=14, pady=(8, 0))
        ctk.CTkLabel(size_row, text="Max Image Size", text_color=TEXT,
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self._size_hint = ctk.CTkLabel(size_row, text="", text_color="#888888",
                                       font=ctk.CTkFont(size=9))
        self._size_hint.pack(side="right")
        self._max_size_var = tk.StringVar(value="4096")
        self._max_size_entry = ctk.CTkEntry(
            self, textvariable=self._max_size_var,
            fg_color=BG, border_color=BORDER, text_color=TEXT,
            font=ctk.CTkFont(size=11),
        )
        self._max_size_entry.pack(fill="x", padx=14, pady=(2, 0))

        # Focal length
        fl_row = ctk.CTkFrame(self, fg_color="transparent")
        fl_row.pack(fill="x", padx=14, pady=(8, 0))
        ctk.CTkLabel(fl_row, text="Brennweite (35mm)", text_color=TEXT,
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self._fl_hint = ctk.CTkLabel(fl_row, text="mm", text_color="#888888",
                                     font=ctk.CTkFont(size=9))
        self._fl_hint.pack(side="right")
        self._focal_var = tk.StringVar(value="")
        ctk.CTkEntry(
            self, textvariable=self._focal_var,
            placeholder_text="auto (aus Metadaten)",
            fg_color=BG, border_color=BORDER, text_color=TEXT,
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=14, pady=(2, 0))

        # Frame subsampling
        ctk.CTkLabel(self, text="Frame Subsampling", text_color=TEXT,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=14, pady=(8, 0))
        self._subsample_var = tk.StringVar(value="Jeden Frame")
        self._subsample_map = {
            "Jeden Frame": "every_frame",
            "Jeden 2. Frame": "every_2nd",
            "Jeden 3. Frame": "every_3rd",
            "Custom FPS": "custom_fps",
        }
        ctk.CTkOptionMenu(self, values=list(self._subsample_map.keys()),
                          variable=self._subsample_var,
                          fg_color=BG, button_color=BORDER, button_hover_color=ACCENT,
                          text_color=TEXT,
                          command=self._on_subsample_change).pack(
            fill="x", padx=14, pady=(2, 0))

        # Custom FPS (hidden by default)
        self._fps_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self._fps_frame, text="FPS", text_color=TEXT,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(14, 6))
        self._fps_var = tk.IntVar(value=10)
        ctk.CTkEntry(self._fps_frame, textvariable=self._fps_var, width=60,
                     fg_color=BG, border_color=BORDER, text_color=TEXT).pack(side="left")

        # Start button (pushed to bottom)
        ctk.CTkFrame(self, fg_color="transparent").pack(fill="y", expand=True)
        self._start_btn = ctk.CTkButton(
            self, text="▶  START", fg_color=ACCENT, hover_color="#1177bb",
            text_color="white", font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=4, height=38, command=self._start_stop_cb)
        self._start_btn.pack(fill="x", padx=14, pady=14)

    def _on_drag_enter(self, event):
        self._drop_zone.configure(highlightbackground=ACCENT, highlightthickness=2)
        self._drop_hint.configure(text="Loslassen zum Auswählen")

    def _on_drag_leave(self, event):
        self._drop_zone.configure(highlightbackground=BORDER, highlightthickness=1)
        self._drop_hint.configure(text="Ordner hier reinziehen")

    def _on_drop(self, event):
        self._drop_zone.configure(highlightbackground=BORDER, highlightthickness=1)
        self._drop_hint.configure(text="Ordner hier reinziehen")
        raw = event.data.strip()
        # tkinterdnd2 wraps paths with spaces in braces
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        path = Path(raw)
        if path.is_dir():
            folder = str(path)
        elif path.is_file():
            folder = str(path.parent)
        else:
            return
        self._set_folder(folder)

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Video-Ordner wählen")
        if not folder:
            return
        self._set_folder(folder)

    @staticmethod
    def _truncate_path(path: str, max_len: int = 34) -> str:
        return path if len(path) <= max_len else "..." + path[-(max_len - 3):]

    def _set_folder(self, folder: str):
        self._folder_var.set(folder)
        self._drop_path.configure(text=self._truncate_path(folder))
        self._drop_hint.configure(text="Ordner hier reinziehen")
        self._auto_detect_resolution(folder)

    def _on_preset_change(self, value: str):
        preset = SHOT_PRESETS[value]
        self._overlap_var.set(preset["overlap"])
        self._overlap_label.configure(text=str(preset["overlap"]))
        self._tri_min_angle = preset["tri_min_angle"]

    def _auto_detect_resolution(self, folder: str):
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".mts", ".m4v"}
        videos = [f for f in Path(folder).iterdir()
                  if f.is_file() and f.suffix.lower() in video_exts]
        if not videos:
            return
        bins = find_binaries()
        if bins is None:
            return
        ffprobe = os.path.join(os.path.dirname(bins.ffmpeg), "ffprobe.exe")
        if not os.path.isfile(ffprobe):
            return
        result = get_video_resolution(ffprobe, str(videos[0]))
        if result is None:
            return
        width, _ = result
        self._max_size_var.set(str(width))
        self._size_hint.configure(text=f"auto ({width}px)")
        if self._progress_panel_ref:
            self._progress_panel_ref.append_log(
                f"[OK] Video erkannt: {videos[0].name} ({width}px) → Max Size: {width}px", "ok"
            )

    def _on_subsample_change(self, value):
        if value == "Custom FPS":
            self._fps_frame.pack(fill="x", pady=(4, 0))
        else:
            self._fps_frame.pack_forget()

    def get_settings(self) -> PipelineSettings:
        try:
            max_size = int(self._max_size_var.get())
            if max_size < 64:
                raise ValueError
        except (ValueError, TypeError):
            max_size = 4096
            self._max_size_var.set("4096")
        try:
            focal = float(self._focal_var.get())
            focal = focal if focal > 0 else None
        except (ValueError, TypeError):
            focal = None

        return PipelineSettings(
            videos_dir=self._folder_var.get(),
            use_gpu=self._gpu_var.get(),
            overlap=self._overlap_var.get(),
            max_image_size=max_size,
            subsampling=self._subsample_map[self._subsample_var.get()],
            custom_fps=self._fps_var.get(),
            tri_min_angle=self._tri_min_angle,
            focal_length_35mm=focal,
        )

    def set_running(self, running: bool):
        if running:
            self._start_btn.configure(text="⏹  STOP", fg_color="#b71c1c", hover_color="#c62828")
        else:
            self._start_btn.configure(text="▶  START", fg_color=ACCENT, hover_color="#1177bb")


class ProgressPanel(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=BG, corner_radius=0)
        self._build()

    def _build(self):
        pad = {"padx": 14, "pady": (10, 0)}

        # Progress section
        ctk.CTkLabel(self, text="FORTSCHRITT", text_color=LABEL,
                     font=ctk.CTkFont(size=10)).pack(anchor="w", **pad)

        progress_box = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=4)
        progress_box.pack(fill="x", padx=14, pady=(4, 0))

        header_row = ctk.CTkFrame(progress_box, fg_color="transparent")
        header_row.pack(fill="x", padx=10, pady=(8, 2))
        self._video_label = ctk.CTkLabel(header_row, text="—", text_color=TEXT,
                                          font=ctk.CTkFont(size=11))
        self._video_label.pack(side="left")
        self._step_label = ctk.CTkLabel(header_row, text="", text_color=OK_COLOR,
                                         font=ctk.CTkFont(size=11))
        self._step_label.pack(side="right")

        self._progress_bar = ctk.CTkProgressBar(progress_box, fg_color=BORDER,
                                                  progress_color=ACCENT)
        self._progress_bar.pack(fill="x", padx=10, pady=(0, 2))
        self._progress_bar.set(0)

        self._step_name_label = ctk.CTkLabel(progress_box, text="", text_color="#888888",
                                              font=ctk.CTkFont(size=10))
        self._step_name_label.pack(anchor="w", padx=10, pady=(0, 4))

        self._sub_label = ctk.CTkLabel(progress_box, text="", text_color="#888888",
                                        font=ctk.CTkFont(size=10))
        self._sub_label.pack(anchor="w", padx=10)
        self._sub_progress_bar = ctk.CTkProgressBar(progress_box, fg_color=BORDER,
                                                      progress_color=OK_COLOR, height=8)
        self._sub_progress_bar.pack(fill="x", padx=10, pady=(2, 8))
        self._sub_progress_bar.set(0)

        self._anim_id = None
        self._anim_val = 0.0
        self._anim_dir = 1

        # Log section
        log_header = ctk.CTkFrame(self, fg_color="transparent")
        log_header.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(log_header, text="LOG", text_color=LABEL,
                     font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkButton(log_header, text="📋 Kopieren", width=90, height=22,
                      fg_color=BORDER, hover_color=ACCENT, text_color=TEXT,
                      font=ctk.CTkFont(size=10), corner_radius=3,
                      command=self._copy_log).pack(side="right", padx=(4, 0))
        ctk.CTkButton(log_header, text="💾 Speichern", width=90, height=22,
                      fg_color=BORDER, hover_color=ACCENT, text_color=TEXT,
                      font=ctk.CTkFont(size=10), corner_radius=3,
                      command=self._save_log).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            self, fg_color=BG, text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=11),
            border_width=1, border_color=BORDER,
            wrap="none", state="disabled",
        )
        self._log_box.pack(fill="both", expand=True, padx=14, pady=(4, 14))
        self._log_box.tag_config("ok", foreground=OK_COLOR)
        self._log_box.tag_config("info", foreground=INFO_COLOR)
        self._log_box.tag_config("error", foreground=ERR_COLOR)

    def set_progress(self, video_name: str, step: int, total: int, step_name: str):
        self._video_label.configure(text=video_name)
        self._step_label.configure(text=f"{step} / {total}")
        self._progress_bar.set(step / total)
        self._step_name_label.configure(text=f"[{step}/{total}] {step_name}...")

    def append_log(self, message: str, level: str):
        self._log_box.configure(state="normal")
        tag = level if level in ("ok", "info", "error") else "info"
        self._log_box.insert("end", message + "\n", tag)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def set_sub_progress(self, value: float, text: str = ""):
        if value < 0:
            self._sub_label.configure(text=text or "Verarbeite...")
            self._start_indeterminate()
        else:
            self._stop_indeterminate()
            self._sub_progress_bar.set(value)
            self._sub_label.configure(text=text)

    def _start_indeterminate(self):
        if self._anim_id is not None:
            return
        self._anim_val = 0.0
        self._anim_dir = 1
        self._animate()

    def _stop_indeterminate(self):
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _animate(self):
        self._anim_val += self._anim_dir * 0.04
        if self._anim_val >= 1.0:
            self._anim_val = 1.0
            self._anim_dir = -1
        elif self._anim_val <= 0.0:
            self._anim_val = 0.0
            self._anim_dir = 1
        self._sub_progress_bar.set(self._anim_val)
        self._anim_id = self.after(30, self._animate)

    def _get_log_text(self) -> str:
        return self._log_box.get("1.0", "end").strip()

    def _save_log(self):
        text = self._get_log_text()
        if not text:
            return
        default = f"autotracker_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Textdatei", "*.txt"), ("Alle Dateien", "*.*")],
            initialfile=default,
        )
        if not path:
            return
        Path(path).write_text(text, encoding="utf-8")

    def _copy_log(self):
        text = self._get_log_text()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)

    def clear(self):
        self._stop_indeterminate()
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self._progress_bar.set(0)
        self._sub_progress_bar.set(0)
        self._video_label.configure(text="—")
        self._step_label.configure(text="")
        self._step_name_label.configure(text="")
        self._sub_label.configure(text="")


if __name__ == "__main__":
    app = AutoTrackerApp()
    app.mainloop()
