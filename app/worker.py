"""
VideoCutPub - PySide6 Async Queue Worker Thread
Executes QueueManager in a background thread to prevent UI freezing.
Emits Qt Signals for progress updates and completion.
"""

from PySide6.QtCore import QThread, Signal
from core.queue_manager import QueueManager
from core.models import QueueProgress, CutResult
from typing import List


class QueueWorkerThread(QThread):
    """Worker QThread pour l'exécution asynchrone de la file d'attente."""

    progress_signal = Signal(QueueProgress)
    finished_signal = Signal(list)
    error_signal = Signal(str)

    def __init__(self, queue_manager: QueueManager, parent=None):
        super().__init__(parent)
        self.queue_manager = queue_manager
        # Enregistrement du callback de progression vers le signal Qt
        self.queue_manager.register_progress_callback(self._on_queue_progress)

    def _on_queue_progress(self, progress: QueueProgress) -> None:
        """Transmet le callback du QueueManager vers le Signal Qt (Thread-safe)."""
        self.progress_signal.emit(progress)

    def run(self) -> None:
        """Point d'entrée du thread de traitement."""
        try:
            results: List[CutResult] = self.queue_manager.process_queue()
            self.finished_signal.emit(results)
        except Exception as e:
            self.error_signal.emit(str(e))
