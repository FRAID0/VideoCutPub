"""
Unit and Integration tests for VideoCutter (Fast & Precise modes).
"""

import json
import os
import pytest
from pathlib import Path

from ffmpeg.ffmpeg_manager import FFmpegManager
from core.video_analyzer import VideoAnalyzer
from core.video_cutter import VideoCutter
from core.models import CutMode


@pytest.fixture(scope="module")
def ffmpeg_mgr():
    mgr = FFmpegManager()
    if not mgr.is_available():
        pytest.skip("FFmpeg/FFprobe introuvable sur le système")
    return mgr


@pytest.fixture(scope="module")
def test_video_15s(tmp_path_factory, ffmpeg_mgr):
    """Génère une vidéo de 15 secondes pour les tests de découpage."""
    temp_dir = tmp_path_factory.mktemp("cutter_15s")
    video_path = temp_dir / "sample_15s.mp4"
    
    args = [
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=15:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=15",
        "-c:v", "libx264", "-c:a", "aac",
        str(video_path)
    ]
    ffmpeg_mgr.run_ffmpeg(args)
    return str(video_path)


@pytest.fixture(scope="module")
def test_video_no_audio(tmp_path_factory, ffmpeg_mgr):
    """Génère une vidéo de 10 secondes sans audio."""
    temp_dir = tmp_path_factory.mktemp("cutter_no_audio")
    video_path = temp_dir / "sample_no_audio.mp4"
    
    args = [
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=10:size=320x240:rate=30",
        "-an",
        "-c:v", "libx264",
        str(video_path)
    ]
    ffmpeg_mgr.run_ffmpeg(args)
    return str(video_path)


@pytest.fixture(scope="module")
def test_video_accented_name(tmp_path_factory, ffmpeg_mgr):
    """Génère une vidéo avec espaces et accents."""
    temp_dir = tmp_path_factory.mktemp("cutter_special")
    video_path = temp_dir / "Vidéo d'essai (très long) & spécial.mp4"
    
    args = [
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=30",
        "-an",
        "-c:v", "libx264",
        str(video_path)
    ]
    ffmpeg_mgr.run_ffmpeg(args)
    return str(video_path)


def test_fast_cut_10s_segments(tmp_path, ffmpeg_mgr, test_video_15s):
    cutter = VideoCutter(ffmpeg_mgr)
    out_dir = tmp_path / "output_fast"
    
    result = cutter.cut_video(
        source_path=test_video_15s,
        output_base_dir=str(out_dir),
        segment_duration=10,  # 10s -> doit créer 2 segments (10s et 5s)
        mode=CutMode.FAST
    )
    
    assert result.success is True
    assert result.total_segments == 2
    assert os.path.isfile(result.metadata_json_path)
    
    # Vérification des fichiers générés
    target_folder = Path(result.output_dir)
    assert target_folder.is_dir()
    
    # Vérification du metadata.json
    with open(result.metadata_json_path, "r", encoding="utf-8") as f:
        meta_data = json.load(f)
    
    assert meta_data["cut_mode"] == "fast_stream_copy"
    assert len(meta_data["segments"]) == 2
    
    seg1 = meta_data["segments"][0]
    assert "requested_start" in seg1
    assert "requested_end" in seg1
    assert "actual_start" in seg1
    assert "actual_end" in seg1


def test_precise_cut_5s_segments(tmp_path, ffmpeg_mgr, test_video_15s):
    cutter = VideoCutter(ffmpeg_mgr)
    out_dir = tmp_path / "output_precise"
    
    result = cutter.cut_video(
        source_path=test_video_15s,
        output_base_dir=str(out_dir),
        segment_duration=5,  # 5s -> doit créer 3 segments
        mode=CutMode.PRECISE
    )
    
    assert result.success is True
    assert result.total_segments == 3
    assert result.cut_mode == CutMode.PRECISE


def test_cut_no_audio_video(tmp_path, ffmpeg_mgr, test_video_no_audio):
    cutter = VideoCutter(ffmpeg_mgr)
    out_dir = tmp_path / "output_no_audio"
    
    result = cutter.cut_video(
        source_path=test_video_no_audio,
        output_base_dir=str(out_dir),
        segment_duration=5,
        mode=CutMode.PRECISE
    )
    
    assert result.success is True
    assert result.total_segments == 2


def test_cut_accented_filename_isolation(tmp_path, ffmpeg_mgr, test_video_accented_name):
    cutter = VideoCutter(ffmpeg_mgr)
    out_dir = tmp_path / "output_accented"
    
    result = cutter.cut_video(
        source_path=test_video_accented_name,
        output_base_dir=str(out_dir),
        segment_duration=2,
        mode=CutMode.FAST
    )
    
    assert result.success is True
    target_folder = Path(result.output_dir)
    assert target_folder.exists()
    assert "?" not in target_folder.name
    assert ":" not in target_folder.name


def test_cut_custom_duration_string(tmp_path, ffmpeg_mgr, test_video_15s):
    cutter = VideoCutter(ffmpeg_mgr)
    out_dir = tmp_path / "output_custom_duration"
    
    # "00:05" -> 5 secondes
    result = cutter.cut_video(
        source_path=test_video_15s,
        output_base_dir=str(out_dir),
        segment_duration="00:05",
        mode=CutMode.FAST
    )
    
    assert result.success is True
    assert result.total_segments == 3


def test_cut_non_existent_file(tmp_path, ffmpeg_mgr):
    cutter = VideoCutter(ffmpeg_mgr)
    with pytest.raises(FileNotFoundError):
        cutter.cut_video(
            source_path="non_existent_video_file.mp4",
            output_base_dir=str(tmp_path),
            segment_duration=10
        )
