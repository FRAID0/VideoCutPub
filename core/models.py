"""
VideoCutPub - Core Data Models
Pydantic data structures for video metadata, segment cuts, and processing results.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class CutMode(str, Enum):
    FAST = "fast_stream_copy"
    PRECISE = "precise_reencode"


class VideoMetadata(BaseModel):
    """Métadonnées extraites d'un fichier vidéo par FFprobe."""
    file_path: str
    duration_seconds: float = Field(..., description="Durée totale en secondes")
    width: int = Field(0, description="Largeur en pixels")
    height: int = Field(0, description="Hauteur en pixels")
    fps: float = Field(0.0, description="Images par seconde")
    video_codec: str = Field("unknown", description="Codec de la piste vidéo (ex: h264)")
    audio_codec: Optional[str] = Field(None, description="Codec audio (ex: aac), None si pas d'audio")
    container_format: str = Field("unknown", description="Format du conteneur (ex: mov,mp4,m4a,3gp,3g2,mj2)")
    file_size_bytes: int = Field(0, description="Taille du fichier sur le disque en octets")
    has_audio: bool = Field(False, description="Vrai si une piste audio est présente")


class SegmentCutInfo(BaseModel):
    """Informations de découpage pour un segment donné."""
    segment_index: int
    filename: str
    output_path: str
    requested_start: str = Field(..., description="Horodatage de début demandé (HH:MM:SS.mmm)")
    requested_end: str = Field(..., description="Horodatage de fin demandé (HH:MM:SS.mmm)")
    actual_start: str = Field(..., description="Horodatage de début réel obtenu (keyframe)")
    actual_end: str = Field(..., description="Horodatage de fin réel obtenu (keyframe)")
    duration_seconds: float = Field(..., description="Durée effective du segment")
    status: str = Field("completed", description="Statut du segment ('completed', 'failed')")
    error_message: Optional[str] = None


class CutResult(BaseModel):
    """Résultat global du traitement de découpage d'une vidéo."""
    source_file: str
    output_dir: str
    cut_mode: CutMode
    target_segment_duration_seconds: float
    total_segments: int
    metadata_json_path: str
    segments: List[SegmentCutInfo]
    success: bool
    error_message: Optional[str] = None
