"""
VideoCutPub - Subtitle Burn-In Engine (FFmpeg libass)
Renders styled ASS or SRT subtitles permanently into MP4 videos with
safe-zone positioning, Windows path escaping, audio preservation, and batch orchestration.
"""

import os
from pathlib import Path
from typing import Optional, List, Union
from pydantic import BaseModel, Field

from ffmpeg.ffmpeg_manager import FFmpegManager, FFmpegExecutionError
from core.video_analyzer import VideoAnalyzer, VideoMetadata


class BurnJob(BaseModel):
    """Définition d'un travail d'incrustation de sous-titres."""
    video_path: str = Field(..., description="Chemin vers le fichier vidéo source (.mp4)")
    subtitle_path: str = Field(..., description="Chemin vers le fichier sous-titres (.ass ou .srt)")
    output_dir: Optional[str] = Field(None, description="Dossier de destination (défaut: rendered/ à côté de la vidéo)")
    output_filename: Optional[str] = Field(None, description="Nom du fichier de sortie (défaut: <stem>_subtitled.mp4)")
    fonts_dir: Optional[str] = Field(None, description="Répertoire de polices personnalisées additionnelles")
    video_codec: str = Field("libx264", description="Codec vidéo d'encodage")
    preset: str = Field("veryfast", description="Preset d'encodage H.264")
    crf: int = Field(22, description="Qualité d'encodage (CRF)")


class BurnResult(BaseModel):
    """Résultat d'une opération d'incrustation de sous-titres."""
    source_video: str
    subtitle_file: str
    output_video: str
    width: int = 0
    height: int = 0
    duration_seconds: float = 0.0
    has_audio: bool = False
    success: bool = True
    error_message: Optional[str] = None


def escape_ffmpeg_filter_path(path_str: Union[str, Path]) -> str:
    """
    Échappe un chemin de fichier pour les filtres FFmpeg (ass / subtitles) sous Windows et Unix.
    - Convertit les backslashes '\\' en slashes '/'
    - Échappe les deux-points ':' en '\\:' (car ':' est le séparateur d'options FFmpeg)
    - Échappe les guillemets simples '\''
    """
    resolved = Path(path_str).resolve()
    posix_str = resolved.as_posix()
    escaped_colons = posix_str.replace(":", r"\:")
    escaped_quotes = escaped_colons.replace("'", r"\'")
    return escaped_quotes


class SubtitleRenderer:
    """
    Moteur d'incrustation de sous-titres dans les flux vidéo via FFmpeg libass.
    Traitement non-destructif : la vidéo source reste intacte.
    """

    def __init__(
        self,
        ffmpeg_manager: Optional[FFmpegManager] = None,
        analyzer: Optional[VideoAnalyzer] = None
    ):
        self.ffmpeg_manager = ffmpeg_manager or FFmpegManager()
        self.analyzer = analyzer or VideoAnalyzer(self.ffmpeg_manager)

    def burn(self, job: BurnJob) -> BurnResult:
        """
        Exécute l'incrustation des sous-titres pour une vidéo donnée.
        Ne modifie jamais le fichier source.
        """
        video = Path(job.video_path)
        sub = Path(job.subtitle_path)

        if not video.is_file():
            return BurnResult(
                source_video=str(video.resolve()) if video.exists() else job.video_path,
                subtitle_file=str(sub.resolve()) if sub.exists() else job.subtitle_path,
                output_video="",
                success=False,
                error_message=f"Vidéo source introuvable : {job.video_path}"
            )

        if not sub.is_file():
            return BurnResult(
                source_video=str(video.resolve()),
                subtitle_file=str(sub.resolve()) if sub.exists() else job.subtitle_path,
                output_video="",
                success=False,
                error_message=f"Fichier de sous-titres introuvable : {job.subtitle_path}"
            )

        # 1. Analyse des propriétés sources (résolution, durée, audio)
        meta = self.analyzer.analyze(str(video))

        # 2. Dossier de sortie non-destructif (ex: rendered/Video_subtitled.mp4)
        target_dir = Path(job.output_dir) if job.output_dir else video.parent / "rendered"
        target_dir.mkdir(parents=True, exist_ok=True)

        target_name = job.output_filename or f"{video.stem}_subtitled{video.suffix}"
        out_file = target_dir / target_name

        # 3. Construction du filtre FFmpeg (ass ou subtitles)
        escaped_sub_path = escape_ffmpeg_filter_path(sub)
        
        # Filtre ass ou subtitles
        if sub.suffix.lower() == ".ass":
            filter_cmd = f"ass=filename='{escaped_sub_path}'"
        else:
            filter_cmd = f"subtitles=filename='{escaped_sub_path}'"

        if job.fonts_dir and os.path.isdir(job.fonts_dir):
            escaped_fonts_dir = escape_ffmpeg_filter_path(job.fonts_dir)
            filter_cmd += f":fontsdir='{escaped_fonts_dir}'"

        # 4. Construction des arguments FFmpeg
        args = [
            "-y",
            "-i", str(video),
            "-vf", filter_cmd,
            "-c:v", job.video_codec,
            "-preset", job.preset,
            "-crf", str(job.crf),
        ]

        if meta.has_audio:
            # Re-encodage AAC sécurisé pour compatibilité universelle
            args.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            args.append("-an")

        args.append(str(out_file))

        # 5. Exécution FFmpeg
        try:
            self.ffmpeg_manager.run_ffmpeg(args)

            # Vérification des propriétés de la vidéo générée
            out_meta = self.analyzer.analyze(str(out_file))

            return BurnResult(
                source_video=str(video.resolve()),
                subtitle_file=str(sub.resolve()),
                output_video=str(out_file.resolve()),
                width=out_meta.width,
                height=out_meta.height,
                duration_seconds=out_meta.duration_seconds,
                has_audio=out_meta.has_audio,
                success=True
            )

        except Exception as e:
            return BurnResult(
                source_video=str(video.resolve()),
                subtitle_file=str(sub.resolve()),
                output_video=str(out_file.resolve()),
                width=meta.width,
                height=meta.height,
                duration_seconds=meta.duration_seconds,
                has_audio=meta.has_audio,
                success=False,
                error_message=str(e)
            )

    def batch_burn(self, jobs: List[BurnJob]) -> List[BurnResult]:
        """
        Orchestre une suite de rendus d'incrustation indépendants.
        Chaque rendu est isolé : l'échec de l'un n'interrompt pas les autres.
        """
        results: List[BurnResult] = []
        for job in jobs:
            res = self.burn(job)
            results.append(res)
        return results
