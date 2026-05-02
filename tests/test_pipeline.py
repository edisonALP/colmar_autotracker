from pipeline import PipelineSettings, sanitize_name, VIDEO_EXTENSIONS

def test_sanitize_name_removes_special_chars():
    assert sanitize_name("0429 (1) 2") == "0429__1__2"
    assert sanitize_name("normal_name") == "normal_name"
    assert sanitize_name("my-video.mp4") == "my-video.mp4"

def test_video_extensions_filters_non_video():
    assert ".mp4" in VIDEO_EXTENSIONS
    assert ".exe" not in VIDEO_EXTENSIONS
    assert ".png" not in VIDEO_EXTENSIONS

def test_settings_defaults():
    s = PipelineSettings(videos_dir="C:/videos")
    assert s.use_gpu is True
    assert s.overlap == 15
    assert s.max_image_size == 4096
    assert s.subsampling == "every_frame"

def test_settings_custom():
    s = PipelineSettings(
        videos_dir="C:/test",
        use_gpu=False,
        overlap=10,
        max_image_size=2048,
        subsampling="every_2nd",
    )
    assert s.use_gpu is False
    assert s.overlap == 10
    assert s.max_image_size == 2048
    assert s.subsampling == "every_2nd"


from pipeline import find_binaries, BinaryPaths

def test_find_binaries_found(tmp_path):
    colmap_dir = tmp_path / "colmap"
    ffmpeg_dir = tmp_path / "ffmpeg"
    colmap_dir.mkdir()
    ffmpeg_dir.mkdir()
    (colmap_dir / "colmap.exe").write_text("")
    (ffmpeg_dir / "ffmpeg.exe").write_text("")

    result = find_binaries(str(tmp_path))
    assert result.colmap == str(colmap_dir / "colmap.exe")
    assert result.ffmpeg == str(ffmpeg_dir / "ffmpeg.exe")

def test_find_binaries_missing_colmap(tmp_path):
    ffmpeg_dir = tmp_path / "ffmpeg"
    ffmpeg_dir.mkdir()
    (ffmpeg_dir / "ffmpeg.exe").write_text("")
    result = find_binaries(str(tmp_path))
    assert result is None

def test_find_binaries_missing_ffmpeg(tmp_path):
    colmap_dir = tmp_path / "colmap"
    colmap_dir.mkdir()
    (colmap_dir / "colmap.exe").write_text("")
    result = find_binaries(str(tmp_path))
    assert result is None


from unittest.mock import patch, MagicMock
from pipeline import PipelineRunner

FAKE_BINS = BinaryPaths(colmap="colmap.exe", ffmpeg="ffmpeg.exe")

def make_runner(settings=None):
    s = settings or PipelineSettings(videos_dir="C:/videos")
    log_cb = MagicMock()
    progress_cb = MagicMock()
    done_cb = MagicMock()
    runner = PipelineRunner(s, FAKE_BINS, log_cb, progress_cb, done_cb)
    return runner, log_cb, progress_cb, done_cb

def test_runner_builds_ffmpeg_command_every_frame():
    runner, _, _, _ = make_runner()
    cmd = runner._ffmpeg_cmd("C:/vid.mp4", "C:/out/images")
    assert "ffmpeg.exe" in cmd[0]
    assert "C:/vid.mp4" in cmd
    assert "frame_%06d.jpg" in cmd[-1]
    assert "-vf" not in cmd

def test_runner_builds_ffmpeg_command_every_2nd():
    s = PipelineSettings(videos_dir="C:/v", subsampling="every_2nd")
    runner, _, _, _ = make_runner(s)
    cmd = runner._ffmpeg_cmd("C:/vid.mp4", "C:/out/images")
    assert "-vf" in cmd
    vf_idx = cmd.index("-vf")
    assert "mod(n,2)" in cmd[vf_idx + 1]

def test_runner_builds_ffmpeg_command_custom_fps():
    s = PipelineSettings(videos_dir="C:/v", subsampling="custom_fps", custom_fps=5)
    runner, _, _, _ = make_runner(s)
    cmd = runner._ffmpeg_cmd("C:/vid.mp4", "C:/out/images")
    assert "-vf" in cmd
    vf_idx = cmd.index("-vf")
    assert "fps=5" in cmd[vf_idx + 1]

def test_runner_stop_sets_flag():
    runner, _, _, _ = make_runner()
    assert runner._stop_event.is_set() is False
    runner.stop()
    assert runner._stop_event.is_set() is True


from pipeline import get_video_resolution, suggest_max_image_size

def test_get_video_resolution_parses_output(tmp_path):
    video = tmp_path / "test.mp4"
    video.write_text("")
    with patch("pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="1920,1080\n")
        result = get_video_resolution("ffprobe.exe", str(video))
    assert result == (1920, 1080)

def test_get_video_resolution_returns_none_on_failure(tmp_path):
    video = tmp_path / "test.mp4"
    video.write_text("")
    with patch("pipeline.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = get_video_resolution("ffprobe.exe", str(video))
    assert result is None

def test_suggest_max_image_size():
    assert suggest_max_image_size(1920) == 2048
    assert suggest_max_image_size(3840) == 4096
    assert suggest_max_image_size(800) == 1024
    assert suggest_max_image_size(4096) == 4096
    assert suggest_max_image_size(5000) == 4096
