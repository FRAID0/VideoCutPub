"""
Unit and Integration tests for QueueManager (Batch Multi-Video Queue Processing).
"""

import os
import pytest
from pathlib import Path

from ffmpeg.ffmpeg_manager import FFmpegManager
from core.video_cutter import VideoCutter
from core.queue_manager import QueueManager, DuplicateJobError
from core.models import CutMode, JobStatus, QueueProgress


@pytest.fixture(scope="module")
def ffmpeg_mgr():
    mgr = FFmpegManager()
    if not mgr.is_available():
        pytest.skip("FFmpeg/FFprobe introuvable sur le système")
    return mgr


@pytest.fixture(scope="module")
def queue_test_videos(tmp_path_factory, ffmpeg_mgr):
    """Génère 3 vidéos de synthèse pour les tests de file d'attente."""
    temp_dir = tmp_path_factory.mktemp("queue_media")
    
    vid_a = temp_dir / "Video_A.mp4"
    vid_b = temp_dir / "Video_B.mp4"
    vid_c = temp_dir / "Video_C.mp4"
    
    for v_path, dur in [(vid_a, 6), (vid_b, 4), (vid_c, 5)]:
        args = [
            "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={dur}:size=320x240:rate=30",
            "-an",
            "-c:v", "libx264",
            str(v_path)
        ]
        ffmpeg_mgr.run_ffmpeg(args)
        
    return str(vid_a), str(vid_b), str(vid_c)


def test_single_video_queue(tmp_path, ffmpeg_mgr, queue_test_videos):
    vid_a, _, _ = queue_test_videos
    qm = QueueManager(VideoCutter(ffmpeg_mgr))
    out_dir = tmp_path / "out_single"
    
    job = qm.add_job(vid_a, str(out_dir), segment_duration=2)
    assert job.status == JobStatus.PENDING
    assert len(qm.jobs) == 1
    
    results = qm.process_queue()
    assert len(results) == 1
    assert job.status == JobStatus.COMPLETED
    assert Path(results[0].output_dir).is_dir()


def test_multiple_videos_queue_and_independent_folders(tmp_path, ffmpeg_mgr, queue_test_videos):
    vid_a, vid_b, vid_c = queue_test_videos
    qm = QueueManager(VideoCutter(ffmpeg_mgr))
    out_dir = tmp_path / "out_multi"
    
    job1 = qm.add_job(vid_a, str(out_dir), segment_duration=2)
    job2 = qm.add_job(vid_b, str(out_dir), segment_duration=2)
    job3 = qm.add_job(vid_c, str(out_dir), segment_duration=2)
    
    assert len(qm.jobs) == 3
    
    results = qm.process_queue()
    assert len(results) == 3
    assert job1.status == JobStatus.COMPLETED
    assert job2.status == JobStatus.COMPLETED
    assert job3.status == JobStatus.COMPLETED
    
    # Vérification des dossiers d'isolation indépendants
    folder1 = Path(job1.result.output_dir)
    folder2 = Path(job2.result.output_dir)
    folder3 = Path(job3.result.output_dir)
    
    assert folder1 != folder2 and folder2 != folder3
    assert folder1.name == "Video_A"
    assert folder2.name == "Video_B"
    assert folder3.name == "Video_C"


def test_error_isolation_and_continuation(tmp_path, ffmpeg_mgr, queue_test_videos):
    vid_a, _, vid_c = queue_test_videos
    invalid_vid = str(tmp_path / "invalid_non_existent.mp4")
    
    qm = QueueManager(VideoCutter(ffmpeg_mgr))
    out_dir = tmp_path / "out_error_test"
    
    job1 = qm.add_job(vid_a, str(out_dir), segment_duration=2)
    job2 = qm.add_job(invalid_vid, str(out_dir), segment_duration=2)
    job3 = qm.add_job(vid_c, str(out_dir), segment_duration=2)
    
    results = qm.process_queue()
    
    # La vidéo 2 échoue mais la vidéo 3 DOIT être traitée normalement
    assert job1.status == JobStatus.COMPLETED
    assert job2.status == JobStatus.FAILED
    assert job2.error_message is not None
    assert job3.status == JobStatus.COMPLETED
    assert len(results) == 2  # 2 vidéos réussies


def test_duplicate_job_prevention(tmp_path, queue_test_videos):
    vid_a, _, _ = queue_test_videos
    qm = QueueManager()
    out_dir = tmp_path / "out_dup"
    
    qm.add_job(vid_a, str(out_dir), segment_duration=2)
    with pytest.raises(DuplicateJobError):
        qm.add_job(vid_a, str(out_dir), segment_duration=2)


def test_queue_cancellation(tmp_path, ffmpeg_mgr, queue_test_videos):
    vid_a, vid_b, vid_c = queue_test_videos
    qm = QueueManager(VideoCutter(ffmpeg_mgr))
    out_dir = tmp_path / "out_cancel"
    
    qm.add_job(vid_a, str(out_dir), segment_duration=2)
    qm.add_job(vid_b, str(out_dir), segment_duration=2)
    qm.add_job(vid_c, str(out_dir), segment_duration=2)
    
    # Annulation immédiate avant de traiter
    qm.cancel()
    qm.process_queue()
    
    assert all(j.status == JobStatus.CANCELLED for j in qm.jobs)


def test_progress_tracking_callbacks(tmp_path, ffmpeg_mgr, queue_test_videos):
    vid_a, vid_b, _ = queue_test_videos
    qm = QueueManager(VideoCutter(ffmpeg_mgr))
    out_dir = tmp_path / "out_progress"
    
    qm.add_job(vid_a, str(out_dir), segment_duration=2)
    qm.add_job(vid_b, str(out_dir), segment_duration=2)
    
    progress_snapshots = []
    qm.register_progress_callback(lambda p: progress_snapshots.append(p))
    
    qm.process_queue()
    
    assert len(progress_snapshots) > 0
    last_prog = progress_snapshots[-1]
    assert last_prog.total_jobs == 2
    assert last_prog.completed_jobs == 2
    assert last_prog.overall_progress_percent == 100.0


def test_add_jobs_from_directory(tmp_path, ffmpeg_mgr, queue_test_videos):
    vid_a, vid_b, vid_c = queue_test_videos
    source_dir = Path(vid_a).parent
    
    qm = QueueManager(VideoCutter(ffmpeg_mgr))
    out_dir = tmp_path / "out_dir_scan"
    
    added_jobs = qm.add_jobs_from_directory(str(source_dir), str(out_dir), segment_duration=2)
    assert len(added_jobs) == 3
