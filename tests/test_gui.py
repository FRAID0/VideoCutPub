"""
Unit tests for PySide6 GUI (MainWindow & QueueWorkerThread).
"""

import sys
import pytest
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.worker import QueueWorkerThread
from core.queue_manager import QueueManager
from core.models import JobStatus, CutMode


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_main_window_initialization(qapp, tmp_path):
    qm = QueueManager()
    win = MainWindow(queue_manager=qm)
    assert win.windowTitle() == "VideoCutPub - Studio de Découpage Vidéo"
    assert win.queue_manager == qm
    assert win.queue_table.rowCount() == 0


def test_main_window_add_jobs(qapp, tmp_path):
    qm = QueueManager()
    win = MainWindow(queue_manager=qm)
    
    # Simuler l'ajout de fichiers via la méthode d'aide de MainWindow
    dummy_file = tmp_path / "dummy_video.mp4"
    dummy_file.write_bytes(b"0" * 1024)
    
    win._add_paths_to_queue([str(dummy_file)])
    assert len(qm.jobs) == 1
    assert win.queue_table.rowCount() == 1
    assert qm.jobs[0].status == JobStatus.PENDING


def test_worker_thread_signals(qapp, tmp_path, monkeypatch):
    qm = QueueManager()
    dummy_file = tmp_path / "dummy_video.mp4"
    dummy_file.write_bytes(b"0" * 1024)
    qm.add_job(str(dummy_file), str(tmp_path), segment_duration=2)

    # Monkeypatch de cut_video pour simuler un succès immédiat sans lancer FFmpeg
    from core.models import CutResult, SegmentCutInfo
    def mock_cut_video(*args, **kwargs):
        return CutResult(
            source_file=str(dummy_file),
            output_dir=str(tmp_path),
            cut_mode=CutMode.FAST,
            target_segment_duration_seconds=2.0,
            total_segments=1,
            metadata_json_path=str(tmp_path / "metadata.json"),
            segments=[],
            success=True
        )

    monkeypatch.setattr(qm.cutter, "cut_video", mock_cut_video)

    worker = QueueWorkerThread(qm)
    progress_emitted = []
    finished_emitted = []

    worker.progress_signal.connect(lambda p: progress_emitted.append(p))
    worker.finished_signal.connect(lambda r: finished_emitted.append(r))

    worker.run()  # Exécution directe synchrone pour le test unit

    assert len(progress_emitted) > 0
    assert len(finished_emitted) == 1
    assert qm.jobs[0].status == JobStatus.COMPLETED
