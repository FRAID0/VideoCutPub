"""
VideoCutPub - Video Transformation Engine (Media Transform)
Handles non-destructive aspect ratio adaptation (16:9, 9:16, 1:1) with Center Crop and Blurred Background modes.
"""

from pathlib import Path
from typing import Optional, Union, List
from pydantic import BaseModel, Field

from ffmpeg.ffmpeg_manager import FFmpegManager, FFmpegExecutionError
from core.video_analyzer import VideoAnalyzer
from social.aspect_ratio import (
    SocialAspectRatio, TransformMode, TransformConfig,
    get_default_dimensions, build_filter_graph
)


class TransformResult(BaseModel):
    """Résultat d'une opération de transformation de format social."""
    source_path: str
    output_path: str
    aspect_ratio: SocialAspectRatio
    mode: TransformMode
    width: int
    height: int
    duration_seconds: float
    success: bool
    error_message: Optional[str] = None


class VideoTransformer:
    """Moteur de transformation de formats vidéo vers les standards réseaux sociaux."""

    def __init__(self, ffmpeg_manager: Optional[FFmpegManager] = None, analyzer: Optional[VideoAnalyzer] = None):
        self.ffmpeg_manager = ffmpeg_manager or FFmpegManager()
        self.analyzer = analyzer or VideoAnalyzer(self.ffmpeg_manager)

    def transform(
        self,
        source_path: str,
        output_dir: str,
        config: Optional[TransformConfig] = None,
        output_filename: Optional[str] = None,
    ) -> TransformResult:
        """
        Transforme une vidéo vers le format d'aspect ratio social configuré.
        Traitement 100% non destructif : l'original reste intact.
        """
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(f"Vidéo source introuvable : {source_path}")

        cfg = config or TransformConfig()
        
        # Résolution par défaut selon le ratio si non spécifiée
        if cfg.target_width <= 0 or cfg.target_height <= 0:
            cfg.target_width, cfg.target_height = get_default_dimensions(cfg.aspect_ratio)

        # 1. Analyse des propriétés sources
        meta = self.analyzer.analyze(str(source))

        # 2. Organisation de l'arborescence dédiée (ex: output_dir / "social" / "9x16")
        ratio_folder = cfg.aspect_ratio.value.replace(":", "x")
        target_dir = Path(output_dir) / "social" / ratio_folder
        target_dir.mkdir(parents=True, exist_ok=True)

        target_name = output_filename or source.name
        out_file = target_dir / target_name

        # 3. Construction de la commande FFmpeg
        filter_str = build_filter_graph(cfg)

        args = ["-y", "-i", str(source)]

        if cfg.mode == TransformMode.BLURRED_BACKGROUND:
            args.extend(["-filter_complex", filter_str])
        else:
            args.extend(["-vf", filter_str])

        args.extend([
            "-c:v", cfg.video_codec,
            "-preset", cfg.preset,
            "-crf", str(cfg.crf),
        ])

        if meta.has_audio:
            args.extend(["-c:a", cfg.audio_codec, "-b:a", "128k"])
        else:
            args.append("-an")

        args.append(str(out_file))

        try:
            self.ffmpeg_manager.run_ffmpeg(args)
            
            # Vérification des métadonnées du fichier généré
            out_meta = self.analyzer.analyze(str(out_file))

            return TransformResult(
                source_path=str(source.resolve()),
                output_path=str(out_file.resolve()),
                aspect_ratio=cfg.aspect_ratio,
                mode=cfg.mode,
                width=out_meta.width,
                height=out_meta.height,
                duration_seconds=out_meta.duration_seconds,
                success=True
            )
        except Exception as e:
            return TransformResult(
                source_path=str(source.resolve()),
                output_path=str(out_file.resolve()),
                aspect_ratio=cfg.aspect_ratio,
                mode=cfg.mode,
                width=cfg.target_width,
                height=cfg.target_height,
                duration_seconds=0.0,
                success=False,
                error_message=str(e)
            )

    def batch_transform(
        self,
        source_paths: List[str],
        output_dir: str,
        configs: List[TransformConfig],
    ) -> List[TransformResult]:
        """Exécute une série de transformations sur une liste de segments/vidéos."""
        results: List[TransformResult] = []
        for src in source_paths:
            for cfg in configs:
                res = self.transform(source_path=src, output_dir=output_dir, config=cfg)
                results.append(res)
        return results
