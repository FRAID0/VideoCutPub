"""
VideoCutPub - Base Publisher Abstract Interface (Étape 10)
Defines the standard contract for all social media publishers
(Manual/Semi-Auto, YouTube Data API, TikTok Content Posting API).
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple
from pathlib import Path

from publishing.publishing_models import PublishingJob, PublishPlatform, PublishStatus, AccountCredentials


class BasePublisher(ABC):
    """Classe abstraite de base pour tous les moteurs de publication."""

    platform: PublishPlatform

    def validate_job(self, job: PublishingJob) -> Tuple[bool, Optional[str]]:
        """
        Valide l'intégrité minimale requise pour un job avant publication.
        """
        if not job.source_video:
            return False, "Aucun fichier vidéo spécifié."

        video_path = Path(job.source_video)
        if not video_path.is_file():
            return False, f"Fichier vidéo introuvable : {job.source_video}"

        if not job.title or not job.title.strip():
            return False, "Le titre de la publication est obligatoire."

        if job.thumbnail:
            thumb_path = Path(job.thumbnail)
            if not thumb_path.is_file():
                return False, f"Fichier miniature introuvable : {job.thumbnail}"

        return True, None

    @abstractmethod
    def publish(
        self,
        job: PublishingJob,
        credentials: Optional[AccountCredentials] = None
    ) -> PublishingJob:
        """
        Exécute la publication ou prépare l'action semi-automatique.
        Met à jour les statuts et informations de traçabilité du PublishingJob.
        """
        pass

    @abstractmethod
    def check_status(
        self,
        job: PublishingJob,
        credentials: Optional[AccountCredentials] = None
    ) -> PublishStatus:
        """
        Vérifie l'état d'avancement distant auprès de la plateforme (pour traitement asynchrone).
        """
        pass
