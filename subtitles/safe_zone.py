"""
VideoCutPub - Subtitle Safe Zones for Social Media
Calculates adaptive safe margins and alignments for TikTok, YouTube Shorts,
Instagram Reels, 1:1 square, and standard 16:9 resolutions.
"""

from enum import Enum
from typing import Union, Dict
from pydantic import BaseModel, Field


class SafeZonePreset(str, Enum):
    GENERIC_9_16 = "generic_9_16"
    TIKTOK = "tiktok"
    YOUTUBE_SHORTS = "youtube_shorts"
    INSTAGRAM_REELS = "instagram_reels"
    GENERIC_1_1 = "generic_1_1"
    GENERIC_16_9 = "generic_16_9"


class SafeZoneConfig(BaseModel):
    """
    Configuration dynamique des zones de sécurité (Safe Zones).
    Empêche les sous-titres d'être masqués par l'interface des applications mobiles.
    """
    top: int = Field(180, description="Marge supérieure en pixels")
    bottom: int = Field(360, description="Marge inférieure en pixels")
    left: int = Field(80, description="Marge gauche en pixels")
    right: int = Field(120, description="Marge droite en pixels (évite les boutons like/partage)")
    horizontal_anchor: str = Field("center", description="Ancrage horizontal: center, left, right")
    vertical_anchor: str = Field("bottom", description="Ancrage vertical: bottom, top, center")

    def scale_to_resolution(
        self,
        base_width: int,
        base_height: int,
        target_width: int,
        target_height: int
    ) -> "SafeZoneConfig":
        """Adapte proportionnellement les marges à une résolution cible différente."""
        if base_width <= 0 or base_height <= 0 or target_width <= 0 or target_height <= 0:
            return self

        scale_x = target_width / base_width
        scale_y = target_height / base_height

        return SafeZoneConfig(
            top=int(round(self.top * scale_y)),
            bottom=int(round(self.bottom * scale_y)),
            left=int(round(self.left * scale_x)),
            right=int(round(self.right * scale_x)),
            horizontal_anchor=self.horizontal_anchor,
            vertical_anchor=self.vertical_anchor
        )


# Références de base par plateforme (Canvas 1080x1920 pour 9:16, 1080x1080 pour 1:1, 1920x1080 pour 16:9)
PRESET_BASE_DIMENSIONS: Dict[SafeZonePreset, tuple[int, int]] = {
    SafeZonePreset.GENERIC_9_16: (1080, 1920),
    SafeZonePreset.TIKTOK: (1080, 1920),
    SafeZonePreset.YOUTUBE_SHORTS: (1080, 1920),
    SafeZonePreset.INSTAGRAM_REELS: (1080, 1920),
    SafeZonePreset.GENERIC_1_1: (1080, 1080),
    SafeZonePreset.GENERIC_16_9: (1920, 1080),
}

PRESET_DEFINITIONS: Dict[SafeZonePreset, SafeZoneConfig] = {
    SafeZonePreset.GENERIC_9_16: SafeZoneConfig(
        top=180, bottom=350, left=80, right=120, horizontal_anchor="center", vertical_anchor="bottom"
    ),
    SafeZonePreset.TIKTOK: SafeZoneConfig(
        top=220, bottom=380, left=80, right=140, horizontal_anchor="center", vertical_anchor="bottom"
    ),
    SafeZonePreset.YOUTUBE_SHORTS: SafeZoneConfig(
        top=180, bottom=320, left=80, right=120, horizontal_anchor="center", vertical_anchor="bottom"
    ),
    SafeZonePreset.INSTAGRAM_REELS: SafeZoneConfig(
        top=200, bottom=340, left=80, right=120, horizontal_anchor="center", vertical_anchor="bottom"
    ),
    SafeZonePreset.GENERIC_1_1: SafeZoneConfig(
        top=80, bottom=120, left=60, right=60, horizontal_anchor="center", vertical_anchor="bottom"
    ),
    SafeZonePreset.GENERIC_16_9: SafeZoneConfig(
        top=60, bottom=90, left=60, right=60, horizontal_anchor="center", vertical_anchor="bottom"
    ),
}


def get_safe_zone(
    preset: Union[SafeZonePreset, str] = SafeZonePreset.GENERIC_9_16,
    target_width: int = 1080,
    target_height: int = 1920
) -> SafeZoneConfig:
    """
    Récupère la SafeZoneConfig pour une plateforme donnée et l'adapte
    à la résolution vidéo cible (ex: 720x1280 ou 1080x1920).
    """
    if isinstance(preset, str):
        try:
            preset_enum = SafeZonePreset(preset.lower())
        except ValueError:
            preset_enum = SafeZonePreset.GENERIC_9_16
    else:
        preset_enum = preset

    base_config = PRESET_DEFINITIONS.get(preset_enum, PRESET_DEFINITIONS[SafeZonePreset.GENERIC_9_16])
    base_w, base_h = PRESET_BASE_DIMENSIONS.get(preset_enum, (1080, 1920))

    if target_width != base_w or target_height != base_h:
        return base_config.scale_to_resolution(base_w, base_h, target_width, target_height)

    return base_config
