"""
VideoCutPub - Batch Queue Manager
Orchestrates multi-video batch cutting queues, manages job lifecycle, progress metrics, and error isolation.
"""

import os
import time
import uuid
from pathlib import Path
from typing import List, Optional, Callable, Dict, Set, Union

from core.models import CutMode, JobStatus, VideoJob, QueueProgress, CutResult
from core.video_cutter import VideoCutter
from ffmpeg.ffmpeg_manager import FFmpegManager


class DuplicateJobError(Exception):
    """Exception levée lors d'une tentative d'ajout d'une vidéo déjà présente dans la file."""
    pass


class QueueManager:
    """
    Gestionnaire de file d'attente Batch pour le traitement de plusieurs vidéos.
    """

    def __init__(self, cutter: Optional[VideoCutter] = None):
        self.cutter = cutter or VideoCutter()
        self.jobs: List[VideoJob] = []
        self._registered_paths: Set[str] = set()
        self._is_cancelled: bool = False
        self._is_running: bool = False
        self._start_time: Optional[float] = None
        self.progress_callbacks: List[Callable[[QueueProgress], None]] = []

    def register_progress_callback(self, callback: Callable[[QueueProgress], None]) -> None:
        """Enregistre une fonction de rappel (callback / observer) pour la progression."""
        self.progress_callbacks.append(callback)

    def add_job(
        self,
        source_path: str,
        output_base_dir: str,
        segment_duration: Union[int, float, str],
        cut_mode: CutMode = CutMode.FAST,
    ) -> VideoJob:
        """
        Ajoute une vidéo à la file d'attente.
        Empêche le double traitement d'une même vidéo source.
        """
        abs_path = str(Path(source_path).resolve())
        if abs_path in self._registered_paths:
            raise DuplicateJobError(f"La vidéo '{source_path}' est déjà présente dans la file d'attente.")

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job = VideoJob(
            job_id=job_id,
            source_path=abs_path,
            output_base_dir=str(Path(output_base_dir).resolve()),
            segment_duration=segment_duration,
            cut_mode=cut_mode,
            status=JobStatus.PENDING,
            progress_percent=0.0
        )
        self.jobs.append(job)
        self._registered_paths.add(abs_path)
        return job

    def add_jobs_from_directory(
        self,
        directory_path: str,
        output_base_dir: str,
        segment_duration: Union[int, float, str],
        cut_mode: CutMode = CutMode.FAST,
        extensions: Optional[List[str]] = None,
    ) -> List[VideoJob]:
        """Scanne un dossier et ajoute toutes les vidéos trouvées à la file d'attente."""
        dir_path = Path(directory_path)
        if not dir_path.is_dir():
            raise FileNotFoundError(f"Répertoire source introuvable : {directory_path}")

        valid_exts = set(ext.lower() if ext.startswith(".") else f".{ext.lower()}" 
                       for ext in (extensions or [".mp4", ".mov", ".avi", ".mkv"]))

        added_jobs: List[VideoJob] = []
        for file in sorted(dir_path.iterdir()):
            if file.is_file() and file.suffix.lower() in valid_exts:
                try:
                    job = self.add_job(str(file), output_base_dir, segment_duration, cut_mode)
                    added_jobs.append(job)
                except DuplicateJobError:
                    pass
        return added_jobs

    def clear(self) -> None:
        """Réinitialise la file d'attente."""
        if self._is_running:
            raise RuntimeError("Impossible de vider la file pendant l'exécution des traitements.")
        self.jobs.clear()
        self._registered_paths.clear()
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'annulation du traitement en cours."""
        self._is_cancelled = True
        for job in self.jobs:
            if job.status == JobStatus.PENDING:
                job.status = JobStatus.CANCELLED

    def process_queue(self) -> List[CutResult]:
        """
        Exécute la file d'attente séquentiellement.
        Capture les erreurs par vidéo et continue automatiquement avec la vidéo suivante.
        """
        self._is_running = True
        results: List[CutResult] = []

        total_jobs = len(self.jobs)

        for idx, job in enumerate(self.jobs, start=1):
            if self._is_cancelled:
                job.status = JobStatus.CANCELLED
                self._notify_progress(idx, job)
                continue

            job.status = JobStatus.RUNNING
            job.progress_percent = 0.0
            self._notify_progress(idx, job)

            try:
                # Exécution du découpage via VideoCutter
                result = self.cutter.cut_video(
                    source_path=job.source_path,
                    output_base_dir=job.output_base_dir,
                    segment_duration=job.segment_duration,
                    mode=job.cut_mode,
                )
                
                job.result = result
                job.progress_percent = 100.0
                
                if result.success:
                    job.status = JobStatus.COMPLETED
                    results.append(result)
                else:
                    job.status = JobStatus.FAILED
                    job.error_message = result.error_message or "Échec de découpage d'un ou plusieurs segments."

            except Exception as e:
                # Isolation de l'erreur : marquer le job comme FAILED et continuer la file
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                job.progress_percent = 0.0

            self._notify_progress(idx, job)

        self._is_running = False
        return results

    def get_progress(self) -> QueueProgress:
        """Calcule un instantané de la progression globale."""
        total = len(self.jobs)
        completed = sum(1 for j in self.jobs if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in self.jobs if j.status == JobStatus.FAILED)
        cancelled = sum(1 for j in self.jobs if j.status == JobStatus.CANCELLED)

        current_idx = 0
        current_filename = ""
        current_job_prog = 0.0

        running_job = next((j for j in self.jobs if j.status == JobStatus.RUNNING), None)
        if running_job:
            current_idx = self.jobs.index(running_job) + 1
            current_filename = Path(running_job.source_path).name
            current_job_prog = running_job.progress_percent

        processed_count = completed + failed + cancelled
        overall_percent = (processed_count / total * 100.0) if total > 0 else 0.0

        elapsed = (time.time() - self._start_time) if self._start_time else 0.0
        eta = 0.0
        if processed_count > 0 and processed_count < total:
            avg_per_job = elapsed / processed_count
            eta = avg_per_job * (total - processed_count)

        return QueueProgress(
            total_jobs=total,
            completed_jobs=completed,
            failed_jobs=failed,
            cancelled_jobs=cancelled,
            current_job_index=current_idx,
            current_job_filename=current_filename,
            overall_progress_percent=round(overall_percent, 1),
            current_job_progress_percent=round(current_job_prog, 1),
            elapsed_seconds=round(elapsed, 1),
            estimated_remaining_seconds=round(eta, 1)
        )

    def get_results(self) -> List[CutResult]:
        """Retourne la liste des résultats des jobs terminés avec succès."""
        return [j.result for j in self.jobs if j.result is not None and j.status == JobStatus.COMPLETED]

    def _notify_progress(self, current_index: int, current_job: VideoJob) -> None:
        """Notifie les observateurs de la progression."""
        prog = self.get_progress()
        for callback in self.progress_callbacks:
            try:
                callback(prog)
            except Exception:
                pass
