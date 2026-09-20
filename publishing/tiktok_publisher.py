"""
VideoCutPub - Official TikTok Content Posting API Publisher (Étape 10)
Follows official TikTok Content Posting API v2:
1. Queries creator_info/query for capabilities and allowed privacy levels.
2. Enforces explicit user consent.
3. Initiates FILE_UPLOAD via /v2/post/publish/video/init/.
4. Performs chunked binary upload.
5. Polls status asynchronously via /v2/post/publish/status/fetch/.
"""

import math
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
import requests

from publishing.publishing_models import (
    PublishingJob,
    PublishPlatform,
    PublishStatus,
    AccountCredentials,
)
from publishing.publisher_base import BasePublisher

TIKTOK_CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
TIKTOK_INIT_UPLOAD_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_FETCH_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


class TikTokPublisher(BasePublisher):
    """
    Publisher officiel TikTok Content Posting API.
    """

    platform = PublishPlatform.TIKTOK

    def __init__(self, chunk_size: int = 10 * 1024 * 1024, timeout_sec: int = 60):
        # Taille de bloc standard (10 Mo) respectant les directives TikTok (entre 5 et 64 Mo)
        self.chunk_size = chunk_size
        self.timeout_sec = timeout_sec

    def get_creator_info(
        self,
        access_token: str,
        session: Optional[requests.Session] = None
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Interroge les capacités du compte créateur (privacy_level_options, max_video_post_duration_sec, etc.)
        avant toute tentative de publication.
        """
        s = session or requests.Session()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8"
        }

        try:
            resp = s.post(TIKTOK_CREATOR_INFO_URL, headers=headers, json={}, timeout=self.timeout_sec)
            data = resp.json()
            if resp.status_code == 200 and data.get("error", {}).get("code") == "ok":
                return True, data.get("data", {}), None
            else:
                err_msg = data.get("error", {}).get("message", resp.text)
                return False, {}, f"Erreur creator_info ({resp.status_code}): {err_msg}"
        except Exception as e:
            return False, {}, f"Exception creator_info: {str(e)}"

    def init_video_upload(
        self,
        job: PublishingJob,
        access_token: str,
        allowed_privacy: Optional[List[str]] = None,
        as_draft: bool = False,
        session: Optional[requests.Session] = None
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Initialise la publication FILE_UPLOAD auprès de TikTok.
        """
        s = session or requests.Session()
        v_path = Path(job.source_video)
        total_bytes = v_path.stat().st_size
        total_chunk_count = max(1, math.ceil(total_bytes / self.chunk_size))

        # Détermination du privacy level selon options autorisées pour le créateur
        # Options TikTok: "PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"
        privacy_choice = "SELF_ONLY"  # Défaut sécurisé pour clients non audités
        if allowed_privacy and "PUBLIC_TO_EVERYONE" in allowed_privacy and not as_draft:
            if job.privacy.value == "public":
                privacy_choice = "PUBLIC_TO_EVERYONE"

        post_mode = "MEDIA_UPLOAD" if as_draft else "DIRECT_POST"

        body = {
            "post_info": {
                "title": (job.title + " " + " ".join(job.hashtags)).strip()[:150],
                "privacy_level": privacy_choice,
                "disable_duet": False,
                "disable_stitch": False,
                "disable_comment": False,
                "video_cover_timestamp_ms": 1000
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": total_bytes,
                "chunk_size": self.chunk_size,
                "total_chunk_count": total_chunk_count
            }
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8"
        }

        try:
            resp = s.post(TIKTOK_INIT_UPLOAD_URL, headers=headers, json=body, timeout=self.timeout_sec)
            data = resp.json()
            if resp.status_code == 200 and data.get("error", {}).get("code") == "ok":
                return True, data.get("data", {}), None
            else:
                err_msg = data.get("error", {}).get("message", resp.text)
                return False, {}, f"Erreur init publish TikTok ({resp.status_code}): {err_msg}"
        except Exception as e:
            return False, {}, f"Exception init publish TikTok: {str(e)}"

    def upload_chunks(
        self,
        upload_url: str,
        video_path: str,
        session: Optional[requests.Session] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Téléverse le fichier vidéo bloc par bloc vers l'upload_url TikTok.
        """
        s = session or requests.Session()
        v_path = Path(video_path)
        total_bytes = v_path.stat().st_size

        try:
            with open(v_path, "rb") as f:
                start_byte = 0
                while start_byte < total_bytes:
                    chunk = f.read(self.chunk_size)
                    chunk_len = len(chunk)
                    end_byte = start_byte + chunk_len - 1

                    headers = {
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes {start_byte}-{end_byte}/{total_bytes}",
                        "Content-Length": str(chunk_len)
                    }

                    resp = s.put(upload_url, headers=headers, data=chunk, timeout=self.timeout_sec * 2)
                    if resp.status_code not in (200, 201, 206, 308):
                        return False, f"Échec transmission bloc TikTok ({resp.status_code}): {resp.text}"

                    start_byte += chunk_len

            return True, None
        except Exception as e:
            return False, f"Exception transmission binaire TikTok: {str(e)}"

    def publish(
        self,
        job: PublishingJob,
        credentials: Optional[AccountCredentials] = None,
        as_draft: bool = False
    ) -> PublishingJob:
        """
        Exécute la publication Direct Post TikTok avec respect des politiques :
        1. Validation locale.
        2. Vérification des identifiants.
        3. Contrôle du consentement utilisateur.
        4. Requête creator_info/query.
        5. Init upload & chunked transfer.
        6. Suivi asynchrone du publish_id.
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
            job.last_error_message = "Credentials ou token d'accès manquant pour TikTok."
            job.updated_at = datetime.now()
            return job

        # Consentement utilisateur obligatoire
        if job.requires_user_consent and not job.user_consented_at:
            job.status = PublishStatus.FAILED
            job.last_error_code = "CONSENT_REQUIRED"
            job.last_error_message = "Consentement explicite de l'utilisateur requis avant publication sur TikTok."
            job.updated_at = datetime.now()
            return job

        token = credentials.access_token

        # 1. Interrogation du profil créateur
        ok_info, c_data, err_info = self.get_creator_info(token)
        allowed_privacy = c_data.get("privacy_level_options", ["SELF_ONLY"]) if ok_info else ["SELF_ONLY"]

        # 2. Init upload
        job.status = PublishStatus.UPLOADING
        job.updated_at = datetime.now()

        ok_init, init_data, err_init = self.init_video_upload(
            job, token, allowed_privacy=allowed_privacy, as_draft=as_draft
        )
        if not ok_init:
            job.status = PublishStatus.FAILED
            job.last_error_code = "INIT_FAILED"
            job.last_error_message = err_init
            job.updated_at = datetime.now()
            return job

        publish_id = init_data.get("publish_id")
        upload_url = init_data.get("upload_url")
        job.remote_id = publish_id
        job.upload_session_id = upload_url

        # 3. Téléversement binaire par blocs
        ok_up, err_up = self.upload_chunks(upload_url, job.source_video)
        if not ok_up:
            job.status = PublishStatus.FAILED
            job.last_error_code = "UPLOAD_FAILED"
            job.last_error_message = err_up
            job.updated_at = datetime.now()
            return job

        # 4. Étape PROCESSING
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
        Interroge /v2/post/publish/status/fetch/ pour connaître le statut asynchrone du post.
        """
        if not job.remote_id or not credentials or not credentials.access_token:
            return job.status

        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "Content-Type": "application/json; charset=UTF-8"
        }
        body = {"publish_id": job.remote_id}

        try:
            resp = requests.post(TIKTOK_STATUS_FETCH_URL, headers=headers, json=body, timeout=self.timeout_sec)
            data = resp.json()
            if resp.status_code == 200 and data.get("error", {}).get("code") == "ok":
                status_str = data.get("data", {}).get("status")
                # Statuts officiels TikTok:
                # "PROCESSING_DOWNLOAD", "PROCESSING_UPLOAD", "SUCCESS", "FAILED"
                if status_str == "SUCCESS":
                    post_id = data.get("data", {}).get("publicly_available_post_id")
                    if post_id:
                        job.platform_post_id = str(post_id)
                    return PublishStatus.PUBLISHED
                elif status_str in ("PROCESSING_DOWNLOAD", "PROCESSING_UPLOAD"):
                    return PublishStatus.PROCESSING
                elif status_str == "FAILED":
                    fail_reason = data.get("data", {}).get("fail_reason", "Raison inconnue")
                    job.last_error_message = f"Échec TikTok: {fail_reason}"
                    return PublishStatus.FAILED
        except Exception:
            pass

        return job.status
