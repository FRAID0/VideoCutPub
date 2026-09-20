"""
VideoCutPub - Social Media Aspect Ratio Models and Filter Graphs
Defines aspect ratio specifications (16:9, 9:16, 1:1) and FFmpeg video filter builders.
"""

from enum import Enum
from typing import Tuple, Optional
from pydantic import BaseModel, Field


class SocialAspectRatio(str, Enum):
    RATIO_16_9 = "16:9"   # Format Horizontal standard (YouTube, Web)
    RATIO_9_16 = "9:16"   # Format Vertical standard (TikTok, Shorts, Reels)
    RATIO_1_1 = "1:1"     # Format Carré standard (Instagram, LinkedIn)


class TransformMode(str, Enum):
    CENTER_CROP = "center_crop"                # Recadrage centré plein écran
    BLURRED_BACKGROUND = "blurred_background"  # Image complète sur fond flouté
    FIT_PAD = "fit_pad"                        # Bandes noires (letterbox / pillarbox)


class TransformConfig(BaseModel):
    """Configuration d'une transformation de format vidéo pour les réseaux sociaux."""
    aspect_ratio: SocialAspectRatio = SocialAspectRatio.RATIO_9_16
    mode: TransformMode = TransformMode.BLURRED_BACKGROUND
    target_width: int = Field(1080, description="Largeur cible en pixels")
    target_height: int = Field(1920, description="Hauteur cible en pixels")
    video_codec: str = Field("libx264", description="Codec vidéo")
    audio_codec: str = Field("aac", description="Codec audio")
    crf: int = Field(22, description="Facteur de qualité visuelle (CRF 18-28)")
    preset: str = Field("veryfast", description="Preset d'encodage H.264")
    blur_strength: int = Field(25, description="Intensité du flou pour l'arrière-plan")


def get_default_dimensions(aspect_ratio: SocialAspectRatio) -> Tuple[int, int]:
    """Retourne les dimensions standards en pixels pour un ratio donné."""
    if aspect_ratio == SocialAspectRatio.RATIO_9_16:
        return 1080, 1920
    elif aspect_ratio == SocialAspectRatio.RATIO_1_1:
        return 1080, 1080
    elif aspect_ratio == SocialAspectRatio.RATIO_16_9:
        return 1920, 1080
    return 1080, 1920


def build_filter_graph(config: TransformConfig) -> str:
    """
    Génère la chaîne de filtres FFmpeg (-vf ou -filter_complex) correspondant
    à la configuration de transformation demandée.
    """
    w = config.target_width
    h = config.target_height

    if config.mode == TransformMode.CENTER_CROP:
        # Échelle pour couvrir tout le cadre + découpe centrée
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"

    elif config.mode == TransformMode.BLURRED_BACKGROUND:
        # 1. Fond : mise à l'échelle pour couvrir, crop aux dimensions cibles, application du flou
        # 2. Premier plan : mise à l'échelle pour s'inscrire entièrement dans le cadre
        # 3. Superposition centrée
        blur = config.blur_strength
        return (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"boxblur={blur}:5[bg];"
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )

    elif config.mode == TransformMode.FIT_PAD:
        # Mise à l'échelle proportionnelle avec bandes noires
        return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"

    return f"scale={w}:{h}"
