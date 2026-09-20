"""
VideoCutPub - URL Downloader Models
Pydantic data models for video metadata extraction, download progress, and results.
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class DownloadQuality(str, Enum):
    BEST = "best"
    RES_1080P = "1080p"
    RES_720P = "720p"
    AUDIO_ONLY = "audio_only"


class VideoFormatOption(str, Enum):
    MP4 = "mp4"
    MKV = "mkv"
    ORIGINAL = "original"


class VideoInfo(BaseModel):
    """Métadonnées extraites d'une URL avant téléchargement."""
    url: str
    extractor: str = Field("unknown", description="Nom de la plateforme (ex: youtube, tiktok, twitch)")
    title: str = Field(..., description="Titre original de la vidéo")
    uploader: Optional[str] = Field(None, description="Auteur ou chaîne de la vidéo")
    duration_seconds: float = Field(0.0, description="Durée totale en secondes")
    thumbnail_url: Optional[str] = Field(None, description="URL de la miniature")
    description: Optional[str] = Field(None, description="Description de la vidéo")
    available_resolutions: List[str] = Field(default_factory=list, description="Résolutions disponibles détectées")
    is_live: bool = Field(False, description="Vrai s'il s'agit d'un direct / live stream")
    has_drm: bool = Field(False, description="Vrai si un verrou DRM a été détecté")
    view_count: Optional[int] = Field(None, description="Nombre de vues")


class DownloadProgress(BaseModel):
    """Instantané de progression du téléchargement."""
    status: str = "downloading"  # starting, downloading, processing, finished, error, cancelled
    percent: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    speed_bytes_per_sec: Optional[float] = None
    eta_seconds: Optional[int] = None
    filename: str = ""


class DownloadResult(BaseModel):
    """Résultat d'une opération de téléchargement."""
    success: bool
    source_url: str
    local_file_path: str = ""
    title: str = ""
    duration_seconds: float = 0.0
    uploader: Optional[str] = None
    extractor: str = ""
    file_size_bytes: int = 0
    metadata_json_path: Optional[str] = None
    error_message: Optional[str] = None
