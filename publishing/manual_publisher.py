"""
VideoCutPub - Semi-Automatic & Manual Social Publisher (Étape 10)
Handles Mode 1 (Manual) and Mode 2 (Semi-Automatic):
Prepares clipboard content, opens platform portals, shows source deliverables,
without automated browser manipulation.
"""

import os
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from publishing.publishing_models import PublishingJob, PublishPlatform, PublishStatus, AccountCredentials
from publishing.publisher_base import BasePublisher

DEFAULT_PLATFORM_URLS = {
    PublishPlatform.YOUTUBE: "https://studio.youtube.com/",
    PublishPlatform.TIKTOK: "https://www.tiktok.com/creator-center/upload",
    PublishPlatform.MANUAL: "https://business.facebook.com/latest/home"
}

# Abstraction configurable pour Meta (ex-Creator Studio -> Meta Business Suite)
META_WEB_PORTAL = os.environ.get("META_WEB_PORTAL", "https://business.facebook.com/latest/home")


class ManualPublisher(BasePublisher):
    """
    Publisher semi-automatique : prépare les métadonnées, gère le presse-papier,
    et ouvre les portails officiels des plateformes.
    """

    platform = PublishPlatform.MANUAL

    def __init__(self, platform_urls: Optional[Dict[PublishPlatform, str]] = None):
        self.platform_urls = dict(DEFAULT_PLATFORM_URLS)
        if platform_urls:
            self.platform_urls.update(platform_urls)

    def set_meta_portal_url(self, url: str) -> None:
        """Permet de configurer dynamiquement l'URL du portail Meta."""
        self.platform_urls[PublishPlatform.MANUAL] = url

    def format_clipboard_text(self, job: PublishingJob) -> str:
        """
        Formate une fiche texte claire et complète prête à coller dans le formulaire du réseau social.
        """
        tags_line = " ".join(job.hashtags) if job.hashtags else ""
        content_parts = [
            f"TITRE :\n{job.title}\n",
            f"DESCRIPTION :\n{job.description}\n",
        ]
        if tags_line:
            content_parts.append(f"HASHTAGS :\n{tags_line}\n")

        content_parts.append(f"FICHIER VIDÉO :\n{job.source_video}")
        if job.thumbnail:
            content_parts.append(f"MINIATURE :\n{job.thumbnail}")

        return "\n".join(content_parts)

    def copy_to_clipboard(self, text: str) -> bool:
        """Copie le texte dans le presse-papier système (Windows ou cross-platform)."""
        try:
            from PySide6.QtGui import QGuiApplication, QClipboard
            app = QGuiApplication.instance()
            if app:
                clipboard = app.clipboard()
                clipboard.setText(text)
                return True
        except Exception:
            pass

        # Fallback sous Windows via ctypes
        if os.name == "nt":
            try:
                import subprocess
                p = subprocess.Popen(
                    ["powershell", "-Command", "Set-Clipboard", "-Value", text],
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                )
                p.wait(timeout=3)
                return True
            except Exception:
                pass
        return False

    def open_portal(self, platform: PublishPlatform) -> str:
        """Ouvre le portail officiel de publication dans le navigateur par défaut."""
        target_url = self.platform_urls.get(platform, META_WEB_PORTAL)
        webbrowser.open(target_url)
        return target_url

    def open_local_file_or_dir(self, path_str: str) -> bool:
        """Ouvre le fichier ou son dossier dans l'explorateur Windows."""
        p = Path(path_str)
        target = p if p.is_dir() else p.parent
        if target.exists():
            try:
                os.startfile(str(target.resolve()))
                return True
            except Exception:
                pass
        return False

    def publish(
        self,
        job: PublishingJob,
        credentials: Optional[AccountCredentials] = None
    ) -> PublishingJob:
        """
        Mode Semi-Automatique :
        1. Valide le job.
        2. Copie les métadonnées dans le presse-papier.
        3. Ouvre le dossier local.
        4. Ouvre le portail web officiel.
        5. Met à jour le statut en PUBLISHED (l'utilisateur valide la finalisation).
        """
        valid, err = self.validate_job(job)
        if not valid:
            job.status = PublishStatus.FAILED
            job.last_error_message = err
            job.updated_at = datetime.now()
            return job

        # Formatage et copie dans le presse-papier
        clip_text = self.format_clipboard_text(job)
        self.copy_to_clipboard(clip_text)

        # Ouverture de l'explorateur sur les livrables
        self.open_local_file_or_dir(job.source_video)

        # Ouverture de la plateforme web
        self.open_portal(job.platform)

        job.status = PublishStatus.PUBLISHED
        job.updated_at = datetime.now()
        return job

    def check_status(
        self,
        job: PublishingJob,
        credentials: Optional[AccountCredentials] = None
    ) -> PublishStatus:
        """En mode manuel/semi-automatique, l'état reste celui assigné."""
        return job.status
