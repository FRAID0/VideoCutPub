"""
VideoCutPub - Publishing Data Models (Étape 10)
Standardized data structures for publishing jobs, platform credentials,
multi-account tracking, and upload statuses.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PublishPlatform(str, Enum):
    """Plateformes cibles de publication."""
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    MANUAL = "manual"


class PublishStatus(str, Enum):
    """États du cycle de vie d'un travail de publication."""
    READY = "ready"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PrivacyLevel(str, Enum):
    """Niveaux de visibilité génériques."""
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class AccountMetadata(BaseModel):
    """Métadonnées non-sensibles d'un compte (stockables sans risque dans accounts.json)."""
    account_id: str = Field(..., description="Identifiant unique interne du compte (ex: yt_channel_123)")
    platform: PublishPlatform = Field(..., description="Plateforme associée")
    display_name: str = Field(..., description="Nom d'affichage convivial (ex: @MaChainePro)")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    is_active: bool = True
    extra_info: Dict[str, Any] = Field(default_factory=dict, description="Informations publiques (avatar, channel_id, etc.)")


class AccountCredentials(BaseModel):
    """
    Informations d'authentification sensibles d'un compte.
    STOCKÉES EXCLUSIVEMENT DANS LE WINDOWS CREDENTIAL MANAGER / KEYRING (JAMAIS EN CLAIR).
    """
    account_id: str
    platform: PublishPlatform
    display_name: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expiry: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)


class PublishingJob(BaseModel):
    """
    Tâche de publication complète et traçable pour une plateforme.
    Supporte les modes Manuel, Semi-Automatique, et API.
    """
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: PublishPlatform
    account_id: str = ""
    source_video: str = Field(..., description="Chemin absolu vers la vidéo MP4 à publier")
    title: str = Field(..., description="Titre du post / de la vidéo")
    description: str = Field("", description="Description complète avec mise en page et CTA")
    hashtags: List[str] = Field(default_factory=list, description="Liste des hashtags")
    thumbnail: Optional[str] = Field(None, description="Chemin absolu vers la miniature JPEG HD")
    privacy: PrivacyLevel = PrivacyLevel.PRIVATE
    scheduled_at: Optional[datetime] = None

    # Suivi d'état
    status: PublishStatus = PublishStatus.READY
    remote_id: Optional[str] = Field(None, description="Identifiant unique retourné par la plateforme (video_id, publish_id)")
    platform_post_id: Optional[str] = Field(None, description="ID définitif du post une fois validé par la plateforme")
    upload_session_id: Optional[str] = Field(None, description="ID de session d'upload (resumable upload)")

    # Consentement & Conformité (obligatoire pour TikTok Content Posting API)
    requires_user_consent: bool = False
    user_consented_at: Optional[datetime] = None

    # Résilience & Erreurs
    retry_count: int = 0
    last_error_code: Optional[str] = None
    last_error_message: Optional[str] = None

    # Horodatage & Provenance
    pack_dir: Optional[str] = Field(None, description="Dossier du Social Pack d'origine")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Données techniques additionnelles")
