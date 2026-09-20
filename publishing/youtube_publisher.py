"""
VideoCutPub - Official YouTube Data API v3 Publisher (Étape 10)
Handles resumable video uploads, metadata injection, OAuth2 token refresh,
thumbnail setting, quota monitoring, and unverified project privacy enforcement.
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import requests

from publishing.publishing_models import (
    PublishingJob,
    PublishPlatform,
    PublishStatus,
    PrivacyLevel,
    AccountCredentials,
)
from publishing.publisher_base import BasePublisher

YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
YOUTUBE_THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class YouTubePublisher(BasePublisher):
    """
    Publisher officiel YouTube Data API v3.
    """

    platform = PublishPlatform.YOUTUBE

    def __init__(self, timeout_sec: int = 60):
        self.timeout_sec = timeout_sec

    def refresh_access_token(
        self,
        credentials: AccountCredentials,
        session: Optional[requests.Session] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Rafraîchit l'access_token expiré via l'endpoint Google OAuth2.
        """
        if not credentials.refresh_token or not credentials.client_id or not credentials.client_secret:
            return False, None, "Credentials OAuth2 incomplètes pour le rafraîchissement (refresh_token manquant)."

        s = session or requests.Session()
        payload = {
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "refresh_token": credentials.refresh_token,
            "grant_type": "refresh_token"
        }

        try:
            resp = s.post(YOUTUBE_TOKEN_URL, data=payload, timeout=self.timeout_sec)
            if resp.status_code == 200:
                data = resp.json()
                new_token = data.get("access_token")
                return True, new_token, None
            else:
                return False, None, f"Échec refresh OAuth Google ({resp.status_code}): {resp.text}"
        except Exception as e:
            return False, None, f"Erreur réseau lors du refresh OAuth: {str(e)}"

    def build_metadata_body(
        self,
        job: PublishingJob,
        enforce_unverified_private: bool = True
    ) -> Dict[str, Any]:
        """
        Construit le payload JSON conforme à la documentation YouTube Data API v3.
        Respecte la restriction des projets non-vérifiés : upload privé obligatoire.
        """
        # Troncature propre aux limites YouTube (titre <= 100 caractères, description <= 5000)
        clean_title = job.title.strip()[:100]
        clean_desc = job.description[:5000]

        # Nettoyage des tags (sans dièse #)
        tags = [t.lstrip("#") for t in job.hashtags if t.strip()]

        # Détermination du niveau de confidentialité
        if enforce_unverified_private:
            privacy_val = "private"
        else:
            privacy_val = job.privacy.value if job.privacy else "private"

        status_dict: Dict[str, Any] = {
            "privacyStatus": privacy_val,
            "selfDeclaredMadeForKids": False
        }

        if job.scheduled_at and privacy_val == "private":
            status_dict["publishAt"] = job.scheduled_at.isoformat() + "Z"

        return {
            "snippet": {
                "title": clean_title,
                "description": clean_desc,
                "tags": tags[:500],
                "categoryId": "22"  # People & Blogs par défaut
            },
            "status": status_dict
        }

    def initiate_resumable_upload(
        self,
        job: PublishingJob,
        access_token: str,
        enforce_unverified_private: bool = True,
        session: Optional[requests.Session] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Initialise une session d'upload résumable auprès de YouTube.
        Retourne l'URL de téléversement binaire (Location Header).
        """
        s = session or requests.Session()
        body = self.build_metadata_body(job, enforce_unverified_private)
        v_size = Path(job.source_video).stat().st_size

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(v_size)
        }

        try:
            resp = s.post(YOUTUBE_UPLOAD_URL, headers=headers, json=body, timeout=self.timeout_sec)
            if resp.status_code == 200 and "Location" in resp.headers:
                return True, resp.headers["Location"], None
            elif resp.status_code == 403:
                err_data = resp.json().get("error", {})
                return False, None, f"QUOTA_EXCEEDED: {err_data.get('message', resp.text)}"
            else:
                return False, None, f"Erreur init upload YouTube ({resp.status_code}): {resp.text}"
        except Exception as e:
            return False, None, f"Exception init upload: {str(e)}"

    def upload_video_file(
        self,
        upload_url: str,
        video_path: str,
        session: Optional[requests.Session] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Transmet le fichier vidéo binaire vers l'URL d'upload résumable.
        Retourne (success, video_id, error_message).
        """
        s = session or requests.Session()
        v_file = Path(video_path)
        v_size = v_file.stat().st_size

        headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(v_size)
        }

        try:
            with open(v_file, "rb") as f:
                resp = s.put(upload_url, headers=headers, data=f, timeout=self.timeout_sec * 2)

            if resp.status_code in (200, 201):
                data = resp.json()
                video_id = data.get("id")
                return True, video_id, None
            else:
                return False, None, f"Échec upload flux binaire ({resp.status_code}): {resp.text}"
        except Exception as e:
            return False, None, f"Exception upload binaire: {str(e)}"

    def upload_thumbnail(
        self,
        video_id: str,
        thumb_path: str,
        access_token: str,
        session: Optional[requests.Session] = None
    ) -> bool:
        """Téléverse la miniature personnalisée vers la vidéo YouTube."""
        p = Path(thumb_path)
        if not p.is_file():
            return False

        s = session or requests.Session()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "image/jpeg"
        }
        params = {"videoId": video_id}

        try:
            with open(p, "rb") as f:
                resp = s.post(YOUTUBE_THUMBNAIL_URL, headers=headers, params=params, data=f, timeout=self.timeout_sec)
            return resp.status_code in (200, 201)
        except Exception:
            return False

    def publish(
        self,
        job: PublishingJob,
        credentials: Optional[AccountCredentials] = None
    ) -> PublishingJob:
        """
        Exécute la séquence complète de publication via l'API YouTube Data v3.
        """
        valid, err = self.validate_job(job)
        if not valid:
            job.status = PublishStatus.FAILED
            job.last_error_message = err
            job.updated_at = datetime.now()
            return job

        if not credentials or not credentials.access_token:
            job.status = PublishStatus.FAILED
            job.last_error_code = "AUTH_MISSING"
            job.last_error_message = "Credentials ou token d'accès manquant pour YouTube."
            job.updated_at = datetime.now()
            return job

        token = credentials.access_token

        # 1. Étape UPLOADING
        job.status = PublishStatus.UPLOADING
        job.updated_at = datetime.now()

        # Initialisation Resumable Upload
        ok_init, upload_url, err_init = self.initiate_resumable_upload(job, token)
        if not ok_init and "401" in str(err_init):
            # Tentative de refresh token
            ok_ref, new_token, err_ref = self.refresh_access_token(credentials)
            if ok_ref and new_token:
                token = new_token
                credentials.access_token = new_token
                ok_init, upload_url, err_init = self.initiate_resumable_upload(job, token)

        if not ok_init or not upload_url:
            job.status = PublishStatus.FAILED
            job.last_error_code = "INIT_FAILED"
            job.last_error_message = err_init
            job.updated_at = datetime.now()
            return job

        job.upload_session_id = upload_url

        # Téléversement binaire de la vidéo
        ok_up, video_id, err_up = self.upload_video_file(upload_url, job.source_video)
        if not ok_up or not video_id:
            job.status = PublishStatus.FAILED
            job.last_error_code = "UPLOAD_FAILED"
            job.last_error_message = err_up
            job.updated_at = datetime.now()
            return job

        job.remote_id = video_id
        job.platform_post_id = video_id

        # 2. Miniature optionnelle
        if job.thumbnail and Path(job.thumbnail).is_file():
            self.upload_thumbnail(video_id, job.thumbnail, token)

        # 3. Étape PROCESSING / PUBLISHED
        job.status = PublishStatus.PROCESSING
        job.updated_at = datetime.now()

        # Vérification immédiate du statut
        stat = self.check_status(job, credentials)
        job.status = stat
        job.updated_at = datetime.now()
        return job

    def check_status(
        self,
        job: PublishingJob,
        credentials: Optional[AccountCredentials] = None
    ) -> PublishStatus:
        """
        Interroge l'état d'encodage et de traitement de la vidéo sur YouTube.
        """
        if not job.remote_id or not credentials or not credentials.access_token:
            return job.status

        headers = {"Authorization": f"Bearer {credentials.access_token}"}
        params = {"part": "status,processingDetails", "id": job.remote_id}

        try:
            resp = requests.get(YOUTUBE_VIDEOS_URL, headers=headers, params=params, timeout=self.timeout_sec)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if not items:
                    return job.status

                item = items[0]
                upload_status = item.get("status", {}).get("uploadStatus")

                if upload_status == "processed":
                    return PublishStatus.PUBLISHED
                elif upload_status == "uploaded":
                    return PublishStatus.PROCESSING
                elif upload_status in ("failed", "rejected"):
                    job.last_error_message = f"Rejet YouTube: {upload_status}"
                    return PublishStatus.FAILED
        except Exception:
            pass

        return job.status
