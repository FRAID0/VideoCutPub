"""
Unit tests for VideoAnalyzer & FFmpegManager.
"""

import os
import shutil
import tempfile
import pytest
from pathlib import Path

from ffmpeg.ffmpeg_manager import FFmpegManager, FFmpegNotFoundError
from core.video_analyzer import VideoAnalyzer, VideoAnalysisError
from core.video_cutter import parse_duration_input


@pytest.fixture(scope="module")
def ffmpeg_mgr():
    """Fixture retournant une instance de FFmpegManager."""
    mgr = FFmpegManager()
    if not mgr.is_available():
        pytest.skip("FFmpeg/FFprobe introuvable sur le système")
    return mgr


@pytest.fixture(scope="module")
def sample_video_with_audio(tmp_path_factory, ffmpeg_mgr):
    """Génère une vidéo de synthèse de 5 secondes avec piste audio."""
    temp_dir = tmp_path_factory.mktemp("test_media")
    video_path = temp_dir / "test_with_audio.mp4"
    
    args = [
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",
        "-c:v", "libx264", "-c:a", "aac",
        str(video_path)
    ]
    ffmpeg_mgr.run_ffmpeg(args)
    return str(video_path)


@pytest.fixture(scope="module")
def sample_video_no_audio(tmp_path_factory, ffmpeg_mgr):
    """Génère une vidéo de synthèse de 3 secondes sans piste audio."""
    temp_dir = tmp_path_factory.mktemp("test_media_no_audio")
    video_path = temp_dir / "test_no_audio.mp4"
    
    args = [
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=30",
        "-an",
        "-c:v", "libx264",
        str(video_path)
    ]
    ffmpeg_mgr.run_ffmpeg(args)
    return str(video_path)


@pytest.fixture(scope="module")
def sample_video_special_chars(tmp_path_factory, ffmpeg_mgr):
    """Génère une vidéo de 4 secondes avec espaces et caractères accentués dans le nom."""
    temp_dir = tmp_path_factory.mktemp("test_special_name")
    video_path = temp_dir / "Vidéo d'été & test (2026) [v1].mp4"
    
    args = [
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=30",
        "-an",
        "-c:v", "libx264",
        str(video_path)
    ]
    ffmpeg_mgr.run_ffmpeg(args)
    return str(video_path)


def test_ffmpeg_manager_availability(ffmpeg_mgr):
    assert ffmpeg_mgr.is_available() is True
    assert os.path.isfile(ffmpeg_mgr.ffmpeg_path)
    assert os.path.isfile(ffmpeg_mgr.ffprobe_path)


def test_missing_ffmpeg_raises_error():
    with pytest.raises(FFmpegNotFoundError):
        mgr = FFmpegManager(custom_ffmpeg_path="/path/non/existant/ffmpeg", custom_ffprobe_path="/path/non/existant/ffprobe")
        mgr.run_ffmpeg(["-version"])


def test_analyze_video_with_audio(ffmpeg_mgr, sample_video_with_audio):
    analyzer = VideoAnalyzer(ffmpeg_mgr)
    meta = analyzer.analyze(sample_video_with_audio)
    
    assert meta.duration_seconds >= 4.9
    assert meta.width == 320
    assert meta.height == 240
    assert meta.has_audio is True
    assert meta.audio_codec is not None
    assert meta.video_codec.lower() in ["h264", "avc1"]
    assert meta.file_size_bytes > 0


def test_analyze_video_no_audio(ffmpeg_mgr, sample_video_no_audio):
    analyzer = VideoAnalyzer(ffmpeg_mgr)
    meta = analyzer.analyze(sample_video_no_audio)
    
    assert meta.duration_seconds >= 2.9
    assert meta.has_audio is False
    assert meta.audio_codec is None


def test_analyze_non_existent_file(ffmpeg_mgr):
    analyzer = VideoAnalyzer(ffmpeg_mgr)
    with pytest.raises(FileNotFoundError):
        analyzer.analyze("path/to/invalid_non_existent_video_file.mp4")


def test_parse_duration_input():
    assert parse_duration_input(10) == 10.0
    assert parse_duration_input(30.0) == 30.0
    assert parse_duration_input("10s") == 10.0
    assert parse_duration_input("2m") == 120.0
    assert parse_duration_input("00:30") == 30.0
    assert parse_duration_input("01:30") == 90.0
    assert parse_duration_input("01:00:00") == 3600.0

    with pytest.raises(ValueError):
        parse_duration_input(-5)
    with pytest.raises(ValueError):
        parse_duration_input("invalid")
