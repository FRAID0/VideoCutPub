"""
VideoCutPub - Publishing Queue Orchestrator (Étape 10)
Manages the publishing job pipeline, pack manifest ingestion,
multi-account resolution, retry policies, and execution history.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable

from publishing.publishing_models import (
    PublishingJob,
    PublishPlatform,
    PublishStatus,
    PrivacyLevel,
)
from publishing.publisher_base import BasePublisher
from publishing.manual_publisher import ManualPublisher
from publishing.youtube_publisher import YouTubePublisher
from publishing.tiktok_publisher import TikTokPublisher
from publishing.account_manager import AccountManager


class PublishQueueManager:
    """
    Gestionnaire centralisé de la file d'attente de publication multi-plateformes.
    """

    def __init__(
        self,
        account_manager: Optional[AccountManager] = None,
        base_dir: Optional[str] = None
    ):
        self.account_manager = account_manager or AccountManager(base_dir=base_dir)
        self.base_dir = Path(base_dir) if base_dir else Path.cwd() / "output"
        self.history_file = self.base_dir / "publishing_history.json"

        self.jobs: List[PublishingJob] = []
        self._progress_callback: Optional[Callable[[PublishingJob], None]] = None

        # Registre des publishers
        self.publishers: Dict[PublishPlatform, BasePublisher] = {
            PublishPlatform.MANUAL: ManualPublisher(),
            PublishPlatform.YOUTUBE: YouTubePublisher(),
            PublishPlatform.TIKTOK: TikTokPublisher()
        }

    def set_progress_callback(self, callback: Callable[[PublishingJob], None]) -> None:
        self._progress_callback = callback

    def _notify_progress(self, job: PublishingJob) -> None:
        if self._progress_callback:
            try:
                self._progress_callback(job)
            except Exception:
                pass

    def create_job_from_pack(
        self,
        pack_dir: str,
        platform: PublishPlatform,
        account_id: str = "",
        prefer_subtitled: bool = True,
        privacy: PrivacyLevel = PrivacyLevel.PRIVATE
    ) -> PublishingJob:
        """
        Génère un PublishingJob directement à partir du manifeste unique pack_metadata.json.
        """
        p_dir = Path(pack_dir).resolve()
        manifest_path = p_dir / "pack_metadata.json"

        if not manifest_path.is_file():
            raise FileNotFoundError(f"Manifeste pack_metadata.json introuvable dans : {pack_dir}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        # Sélection de la meilleure vidéo : sous-titrée si disponible et demandée, sinon vidéo principale
        video_filename = None
        subtitles_info = manifest.get("subtitles", {})
        files_info = manifest.get("files", {})

        if prefer_subtitled and subtitles_info.get("burned_in"):
            video_filename = subtitles_info["burned_in"]
        elif prefer_subtitled and files_info.get("video_subtitled"):
            video_filename = files_info["video_subtitled"]
        else:
            video_filename = files_info.get("video") or "video.mp4"

        target_video = p_dir / video_filename
        if not target_video.is_file():
            # Fallback sur n'importe quel mp4 du dossier
            mp4s = list(p_dir.glob("*.mp4"))
            if not mp4s:
                raise FileNotFoundError(f"Aucun fichier vidéo trouvé dans le pack : {pack_dir}")
            target_video = mp4s[0]

        # Miniature
        thumb_name = manifest.get("thumbnail") or files_info.get("thumbnail") or "thumbnail.jpg"
        target_thumb = p_dir / thumb_name
        thumbnail_path = str(target_thumb.resolve()) if target_thumb.is_file() else None

        # Métadonnées
        meta_data = manifest.get("metadata") or {}
        title = meta_data.get("title", p_dir.name)
        desc = meta_data.get("description", "")
        hashtags = meta_data.get("hashtags", [])

        # Exigence de consentement pour TikTok
        requires_consent = (platform == PublishPlatform.TIKTOK)

        job = PublishingJob(
            platform=platform,
            account_id=account_id,
            source_video=str(target_video.resolve()),
            title=title,
            description=desc,
            hashtags=hashtags,
            thumbnail=thumbnail_path,
            privacy=privacy,
            status=PublishStatus.READY,
            requires_user_consent=requires_consent,
            pack_dir=str(p_dir),
            metadata={"manifest": manifest}
        )

        return job

    def add_job(self, job: PublishingJob) -> PublishingJob:
        """Ajoute un job à la file d'attente."""
        self.jobs.append(job)
        return job

    def remove_job(self, job_id: str) -> bool:
        """Retire un job non démarré de la file."""
        init_len = len(self.jobs)
        self.jobs = [j for j in self.jobs if j.job_id != job_id]
        return len(self.jobs) < init_len

    def cancel_job(self, job_id: str) -> bool:
        """Annule un job."""
        for j in self.jobs:
            if j.job_id == job_id and j.status not in (PublishStatus.PUBLISHED, PublishStatus.FAILED):
                j.status = PublishStatus.CANCELLED
                j.updated_at = datetime.now()
                self._notify_progress(j)
                return True
        return False

    def retry_job(self, job_id: str) -> bool:
        """Remet un job échoué en état READY pour une nouvelle tentative."""
        for j in self.jobs:
            if j.job_id == job_id and j.status == PublishStatus.FAILED:
                j.status = PublishStatus.READY
                j.retry_count += 1
                j.last_error_code = None
                j.last_error_message = None
                j.updated_at = datetime.now()
                self._notify_progress(j)
                return True
        return False

    def reorder_jobs(self, ordered_ids: List[str]) -> None:
        """Réorganise la file selon la liste ordonnée d'identifiants."""
        id_map = {j.job_id: j for j in self.jobs}
        new_list = []
        for j_id in ordered_ids:
            if j_id in id_map:
                new_list.append(id_map[j_id])
        # Ajouter les éventuels manquants
        for j in self.jobs:
            if j not in new_list:
                new_list.append(j)
        self.jobs = new_list

    def process_job(self, job: PublishingJob) -> PublishingJob:
        """
        Exécute la publication pour un job donné.
        """
        publisher = self.publishers.get(job.platform)
        if not publisher:
            job.status = PublishStatus.FAILED
            job.last_error_code = "PLATFORM_NOT_SUPPORTED"
            job.last_error_message = f"Aucun publisher disponible pour la plateforme : {job.platform}"
            job.updated_at = datetime.now()
            self._notify_progress(job)
            return job

        # Récupération sécurisée des credentials
        credentials = None
        if job.account_id:
            credentials = self.account_manager.get_account_credentials(job.account_id)

        self._notify_progress(job)
        res_job = publisher.publish(job, credentials=credentials)
        self._notify_progress(res_job)
        self._append_to_history(res_job)
        return res_job

    def process_all(self) -> List[PublishingJob]:
        """Traite tous les jobs en état READY dans l'ordre de la file."""
        processed = []
        for job in list(self.jobs):
            if job.status == PublishStatus.READY:
                self.process_job(job)
                processed.append(job)
        return processed

    def _append_to_history(self, job: PublishingJob) -> None:
        """Enregistre le résultat dans l'historique publishing_history.json."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            history = []
            if self.history_file.exists():
                try:
                    history = json.loads(self.history_file.read_text(encoding="utf-8"))
                except Exception:
                    history = []

            # Ajout ou mise à jour de l'entrée
            history = [h for h in history if h.get("job_id") != job.job_id]
            history.append(json.loads(job.model_dump_json()))
            self.history_file.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def get_history(self) -> List[Dict[str, Any]]:
        """Lit l'historique complet des publications."""
        if self.history_file.exists():
            try:
                return json.loads(self.history_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []
