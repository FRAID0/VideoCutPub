"""
VideoCutPub - Core Data Models
Pydantic data structures for video metadata, segment cuts, and processing results.
"""

from enum import Enum
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class CutMode(str, Enum):
    FAST = "fast_stream_copy"
    PRECISE = "precise_reencode"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    total_time_seconds: float = 0.0


class VideoJob(BaseModel):
    """Représente une tâche de traitement pour une vidéo dans la file d'attente."""
    job_id: str
    source_path: str
    output_base_dir: str
    segment_duration: Union[int, float, str]
    cut_mode: CutMode = CutMode.FAST
    status: JobStatus = JobStatus.PENDING
    progress_percent: float = 0.0
    error_message: Optional[str] = None
    result: Optional[CutResult] = None
    social_transform: Optional[dict] = None


class QueueProgress(BaseModel):
    """Instantané de progression globale de la file d'attente pour l'observateur / UI."""
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    cancelled_jobs: int = 0
    current_job_index: int = 0
    current_job_filename: str = ""
    overall_progress_percent: float = 0.0
    current_job_progress_percent: float = 0.0
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: float = 0.0

