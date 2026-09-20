"""
VideoCutPub - Video Metadata Analyzer
Parses video container properties and stream info via FFprobe.
"""

import json
import os
from pathlib import Path
from typing import Optional, List
from ffmpeg.ffmpeg_manager import FFmpegManager, FFmpegExecutionError
from core.models import VideoMetadata


class VideoAnalysisError(Exception):
    """Exception levée en cas d'échec d'analyse de la vidéo."""
    pass


class VideoAnalyzer:
    """Analyseur de métadonnées vidéo s'appuyant sur FFprobe."""

    def __init__(self, ffmpeg_manager: Optional[FFmpegManager] = None):
        self.ffmpeg_manager = ffmpeg_manager or FFmpegManager()

    def analyze(self, file_path: str) -> VideoMetadata:
        """
        Extrait toutes les métadonnées techniques d'un fichier vidéo.
        Raises FileNotFoundError si le fichier n'existe pas.
        Raises VideoAnalysisError si l'analyse échoue.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Fichier vidéo introuvable : {file_path}")

        file_size_bytes = path.stat().st_size

        args = [
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path)
        ]

        try:
            result = self.ffmpeg_manager.run_ffprobe(args)
            data = json.loads(result.stdout)
        except (FFmpegExecutionError, json.JSONDecodeError) as e:
            raise VideoAnalysisError(f"Échec de l'analyse FFprobe pour '{file_path}': {e}")

        streams = data.get("streams", [])
        format_info = data.get("format", {})

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not video_stream:
            raise VideoAnalysisError(f"Aucune piste vidéo valide trouvée dans '{file_path}'")

        # Extraction de la durée
        duration_str = format_info.get("duration") or video_stream.get("duration")
        try:
            duration_seconds = float(duration_str)
        except (TypeError, ValueError):
            duration_seconds = 0.0

        # Width / Height
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))

        # FPS calculation
        fps = 0.0
        r_frame_rate = video_stream.get("r_frame_rate", "")
        if r_frame_rate and "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            try:
                if float(den) > 0:
                    fps = round(float(num) / float(den), 3)
            except ValueError:
                fps = 0.0

        video_codec = video_stream.get("codec_name", "unknown")
        audio_codec = audio_stream.get("codec_name") if audio_stream else None
        container_format = format_info.get("format_name", "unknown")
        has_audio = audio_stream is not None

        return VideoMetadata(
            file_path=str(path.resolve()),
            duration_seconds=duration_seconds,
            width=width,
            height=height,
            fps=fps,
            video_codec=video_codec,
            audio_codec=audio_codec,
            container_format=container_format,
            file_size_bytes=file_size_bytes,
            has_audio=has_audio,
        )

    def get_keyframes(self, file_path: str) -> List[float]:
        """
        Extrait la liste des timestamps (en secondes) de toutes les images clés (I-frames/keyframes)
        du fichier vidéo. Utile pour calculer les vraies limites de coupe en mode Fast.
        """
        args = [
            "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "frame=pkt_pts_time,key_frame",
            "-of", "csv=p=0",
            str(file_path)
        ]
        try:
            result = self.ffmpeg_manager.run_ffprobe(args)
            keyframes = []
            for line in result.stdout.strip().splitlines():
                parts = line.split(",")
                if len(parts) >= 2 and parts[1].strip() == "1":
                    try:
                        keyframes.append(float(parts[0]))
                    except ValueError:
                        pass
            return keyframes
        except Exception:
            return []
