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
        self._start_time = time.time()
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
                has_extra = bool(job.social_transform or getattr(job, "transcribe", False) or getattr(job, "burn_subtitles", False))

                def _seg_progress(seg_idx: int, seg_total: int, seg_pct: float) -> None:
                    job.progress_percent = (seg_pct * 0.2) if has_extra else seg_pct
                    self._notify_progress(idx, job)

                # Exécution du découpage via VideoCutter
                result = self.cutter.cut_video(
                    source_path=job.source_path,
                    output_base_dir=job.output_base_dir,
                    segment_duration=job.segment_duration,
                    mode=job.cut_mode,
                    progress_callback=_seg_progress,
                )
                
                job.result = result
                job.progress_percent = 20.0 if has_extra else 100.0
                self._notify_progress(idx, job)
                
                if result.success:
                    # 1. Transformation Format Réseaux Sociaux (optionnel)
                    transformed_files = []
                    valid_segs = [s for s in result.segments if s.status == "completed"]
                    total_segs = max(1, len(valid_segs))

                    if job.social_transform:
                        try:
                            from core.video_transformer import VideoTransformer
                            from social.aspect_ratio import TransformConfig
                            cfg = TransformConfig(**job.social_transform)
                            transformer = VideoTransformer(self.cutter.ffmpeg_manager, self.cutter.analyzer)
                            for s_i, seg in enumerate(valid_segs, start=1):
                                t_res = transformer.transform(seg.output_path, result.output_dir, config=cfg)
                                if t_res.success:
                                    transformed_files.append((seg, t_res.output_path))
                                job.progress_percent = 20.0 + (35.0 * (s_i / total_segs))
                                self._notify_progress(idx, job)
                        except Exception as e_trans:
                            pass

                    # 2. Transcription IA & Sous-Titres (optionnel)
                    if getattr(job, "transcribe", False) or getattr(job, "burn_subtitles", False):
                        try:
                            from ai.transcription import TranscriptionEngine, TranscriptionConfig
                            model_name = getattr(job, "whisper_model", "base")
                            trans_cfg = TranscriptionConfig(model_name=model_name)
                            trans_engine = TranscriptionEngine(trans_cfg)

                            targets = transformed_files if transformed_files else [(seg, seg.output_path) for seg in valid_segs]
                            n_targets = max(1, len(targets))

                            for t_i, (seg, video_target) in enumerate(targets, start=1):
                                video_p = Path(video_target)
                                trans_res = trans_engine.transcribe(str(video_p), output_dir=str(video_p.parent))
                                job.progress_percent = 55.0 + (25.0 * (t_i / n_targets))
                                self._notify_progress(idx, job)

                                # 3. Incrustation définitive (Burn-In) si demandée
                                if getattr(job, "burn_subtitles", False) and trans_res.success and trans_res.srt_file_path:
                                    try:
                                        from subtitles.style import get_preset_style, SubtitlePresetName
                                        from subtitles.ass_generator import ASSGenerator
                                        from subtitles.renderer import SubtitleRenderer, BurnJob

                                        preset_name = getattr(job, "subtitle_preset", "tiktok_high_contrast")
                                        meta_target = self.cutter.analyzer.analyze(str(video_p))
                                        style = get_preset_style(
                                            preset_name,
                                            target_width=meta_target.width,
                                            target_height=meta_target.height
                                        )

                                        ass_gen = ASSGenerator(style=style, width=meta_target.width, height=meta_target.height)
                                        ass_file = video_p.parent / f"{video_p.stem}.ass"
                                        ass_gen.export_to_file(trans_res.segments, str(ass_file))

                                        renderer = SubtitleRenderer(self.cutter.ffmpeg_manager, self.cutter.analyzer)
                                        burn_job = BurnJob(
                                            video_path=str(video_p),
                                            subtitle_path=str(ass_file),
                                            output_dir=str(video_p.parent / "rendered")
                                        )
                                        renderer.burn(burn_job)
                                    except Exception as e_burn:
                                        pass

                                job.progress_percent = 80.0 + (20.0 * (t_i / n_targets))
                                self._notify_progress(idx, job)

                        except Exception as e_transcribe:
                            pass

                    job.progress_percent = 100.0

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
        running_fraction = (current_job_prog / 100.0) if running_job else 0.0
        effective_fraction = ((processed_count + running_fraction) / total) if total > 0 else 0.0
        overall_percent = effective_fraction * 100.0

        elapsed = (time.time() - self._start_time) if self._start_time else 0.0
        eta = 0.0
        if effective_fraction > 0.01 and effective_fraction < 1.0 and elapsed > 0:
            total_est_time = elapsed / effective_fraction
            eta = max(0.0, total_est_time - elapsed)

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
