"""
VideoCutPub - Gate MVP Real Video Smoke Test
Simulates processing across various video formats (MP4, MOV, MKV), audio-less streams,
accented filenames, fast and precise modes, and batch queue execution.
"""

import json
import os
import tempfile
import pytest
from pathlib import Path

from ffmpeg.ffmpeg_manager import FFmpegManager
from core.video_analyzer import VideoAnalyzer
from core.video_cutter import VideoCutter
from core.queue_manager import QueueManager
from core.models import CutMode, JobStatus


@pytest.fixture(scope="module")
def ffmpeg_mgr():
    mgr = FFmpegManager()
    if not mgr.is_available():
        pytest.skip("FFmpeg non disponible sur le système")
    return mgr


@pytest.fixture(scope="module")
def real_test_media_set(tmp_path_factory, ffmpeg_mgr):
    """Génère un lot complet de vraies vidéos de test aux formats variés."""
    media_dir = tmp_path_factory.mktemp("smoke_media")

    # 1. MP4 classique avec audio (12 sec)
    mp4_classic = media_dir / "01_Grand_Tourisme_Classic.mp4"
    ffmpeg_mgr.run_ffmpeg([
        "-y", "-f", "lavfi", "-i", "testsrc=duration=12:size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
        "-c:v", "libx264", "-c:a", "aac", str(mp4_classic)
    ])

    # 2. MKV avec espaces et accents (10 sec)
    mkv_accented = media_dir / "02_Vidéo d'été & Vacances en Hongrie (2026).mkv"
    ffmpeg_mgr.run_ffmpeg([
        "-y", "-f", "lavfi", "-i", "testsrc=duration=10:size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=880:duration=10",
        "-c:v", "libx264", "-c:a", "aac", str(mkv_accented)
    ])

    # 3. MOV sans piste audio (8 sec)
    mov_no_audio = media_dir / "03_Clip_Cinématique_NoAudio.mov"
    ffmpeg_mgr.run_ffmpeg([
        "-y", "-f", "lavfi", "-i", "testsrc=duration=8:size=640x360:rate=30",
        "-an", "-c:v", "libx264", str(mov_no_audio)
    ])

    return str(mp4_classic), str(mkv_accented), str(mov_no_audio)


def test_gate_mvp_complete_smoke_flow(tmp_path, ffmpeg_mgr, real_test_media_set):
    mp4_path, mkv_path, mov_path = real_test_media_set
    out_dir = tmp_path / "smoke_output"

    analyzer = VideoAnalyzer(ffmpeg_mgr)
    cutter = VideoCutter(ffmpeg_mgr, analyzer)
    qm = QueueManager(cutter)

    # Ajout du lot mixte
    job1 = qm.add_job(mp4_path, str(out_dir), segment_duration=5, cut_mode=CutMode.FAST)
    job2 = qm.add_job(mkv_path, str(out_dir), segment_duration="00:03", cut_mode=CutMode.PRECISE)
    job3 = qm.add_job(mov_path, str(out_dir), segment_duration=4, cut_mode=CutMode.FAST)

    assert len(qm.jobs) == 3

    # Exécution de la file d'attente
    results = qm.process_queue()

    # Vérifications du Gate MVP
    assert len(results) == 3
    assert all(j.status == JobStatus.COMPLETED for j in qm.jobs)

    # Job 1 : MP4 Fast mode (12s / 5s -> 3 segments)
    dir1 = Path(job1.result.output_dir)
    assert dir1.is_dir()
    assert dir1.name == "01_Grand_Tourisme_Classic"
    assert (dir1 / "metadata.json").is_file()
    assert len(list(dir1.glob("*.mp4"))) == 3

    # Job 2 : MKV Precise mode avec nom accentué (10s / 3s -> 4 segments)
    dir2 = Path(job2.result.output_dir)
    assert dir2.is_dir()
    for illegal_char in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        assert illegal_char not in dir2.name
    assert (dir2 / "metadata.json").is_file()
    assert len(list(dir2.glob("*.mkv"))) == 4

    # Job 3 : MOV sans audio (8s / 4s -> 2 segments)
    dir3 = Path(job3.result.output_dir)
    assert dir3.is_dir()
    assert (dir3 / "metadata.json").is_file()
    assert len(list(dir3.glob("*.mov"))) == 2

    # Vérification du contenu d'un metadata.json
    with open(dir1 / "metadata.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
        assert meta["source_file"] == str(Path(mp4_path).resolve())
        assert meta["cut_mode"] == "fast_stream_copy"
        assert meta["total_segments"] == 3
        assert "requested_start" in meta["segments"][0]
        assert "actual_start" in meta["segments"][0]
