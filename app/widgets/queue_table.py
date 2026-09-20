"""
VideoCutPub - Queue Table Widget (PySide6)
Displays the video job queue with live status, progress, and Drag & Drop file drop support.
"""

from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QWidget
)
from core.models import VideoJob, JobStatus


class QueueTableWidget(QTableWidget):
    """Tableau d'affichage réactif des vidéos de la file d'attente avec Drag & Drop."""

    files_dropped_signal = Signal(list)

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Statut", "Fichier Vidéo", "Durée Segment", "Mode", "Chemin Source"])
        
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
            if paths:
                self.files_dropped_signal.emit(paths)
                event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def update_jobs(self, jobs: list[VideoJob]) -> None:
        """Met à jour le contenu du tableau à partir de la liste des VideoJobs."""
        self.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            status_text, color_code = self._get_status_display(job)
            
            item_status = QTableWidgetItem(status_text)
            item_status.setTextAlignment(Qt.AlignCenter)
            
            filename = Path(job.source_path).name
            item_name = QTableWidgetItem(filename)
            item_duration = QTableWidgetItem(str(job.segment_duration))
            item_duration.setTextAlignment(Qt.AlignCenter)
            
            mode_str = "Rapide (-c copy)" if "fast" in job.cut_mode.value else "Précis (Réencode)"
            item_mode = QTableWidgetItem(mode_str)
            item_mode.setTextAlignment(Qt.AlignCenter)
            
            item_path = QTableWidgetItem(job.source_path)

            self.setItem(row, 0, item_status)
            self.setItem(row, 1, item_name)
            self.setItem(row, 2, item_duration)
            self.setItem(row, 3, item_mode)
            self.setItem(row, 4, item_path)

    @staticmethod
    def _get_status_display(job: VideoJob) -> tuple[str, str]:
        status = job.status
        if status == JobStatus.COMPLETED:
            return "✓ Terminé", "#a6e3a1"
        elif status == JobStatus.RUNNING:
            return f"▶ En cours ({int(job.progress_percent)}%)", "#89b4fa"
        elif status == JobStatus.FAILED:
            return "❌ Échec", "#f38ba8"
        elif status == JobStatus.CANCELLED:
            return "⏹ Annulé", "#f9e2af"
        return "○ En attente", "#6c7086"
