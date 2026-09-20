"""
VideoCutPub - Subtitle Styling and Preset Configurations
Provides customizable models for typography, colors, borders, shadows,
safe-zone positioning, and automated font fallback.
"""

import os
import re
from enum import Enum
from pathlib import Path
from typing import Optional, Union, Tuple, Dict
from pydantic import BaseModel, Field

from subtitles.safe_zone import SafeZoneConfig, SafeZonePreset, get_safe_zone


class SubtitlePresetName(str, Enum):
    TIKTOK_HIGH_CONTRAST = "tiktok_high_contrast"
    SHORTS_CLEAN = "shorts_clean"
    BOXED_HIGH_CONTRAST = "boxed_high_contrast"
    MINIMAL = "minimal"


def hex_to_ass_color(hex_color: str, default_alpha: int = 0) -> str:
    """
    Convertit une couleur Hex (#RRGGBB ou #AARRGGBB) vers le format ASS : &HAABBGGRR.
    En format ASS, l'ordre des canaux est Alpha, Bleu, Vert, Rouge (BGR)
    et Alpha 00 = 100% opaque, FF = 100% transparent.
    """
    clean_hex = hex_color.strip().lstrip("#").lstrip("&H").rstrip("&")
    
    alpha = default_alpha
    r, g, b = 255, 255, 255

    if len(clean_hex) == 6:  # RRGGBB
        r = int(clean_hex[0:2], 16)
        g = int(clean_hex[2:4], 16)
        b = int(clean_hex[4:6], 16)
    elif len(clean_hex) == 8:  # AARRGGBB
        alpha = int(clean_hex[0:2], 16)
        r = int(clean_hex[2:4], 16)
        g = int(clean_hex[4:6], 16)
        b = int(clean_hex[6:8], 16)
    elif len(clean_hex) == 3:  # RGB
        r = int(clean_hex[0] * 2, 16)
        g = int(clean_hex[1] * 2, 16)
        b = int(clean_hex[2] * 2, 16)

    # Format ASS : &H[AA][BB][GG][RR]
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def check_font_availability(font_name: str, fonts_dir: Optional[str] = None) -> Tuple[bool, str]:
    """
    Vérifie la disponibilité d'une police sur le système ou dans fonts_dir.
    Si la police n'est pas trouvée, renvoie (False, "Arial") comme repli sécurisé.
    """
    clean_name = font_name.strip().lower()
    fallback_font = "Arial"

    # 1. Vérification dans fonts_dir personnalisé si fourni
    if fonts_dir and os.path.isdir(fonts_dir):
        for f in os.listdir(fonts_dir):
            if clean_name in f.lower():
                return True, font_name

    # 2. Vérification dans les polices système Windows (C:\Windows\Fonts)
    windir = os.environ.get("WINDIR", "C:\\Windows")
    win_fonts = Path(windir) / "Fonts"
    if win_fonts.is_dir():
        # Remplacement des espaces par rien pour comparaison avec les noms de fichiers (ex: arialbd.ttf)
        clean_no_space = clean_name.replace(" ", "")
        for f in win_fonts.iterdir():
            f_name = f.name.lower()
            if clean_no_space in f_name or clean_name in f_name:
                return True, font_name

    # Polices courantes standard toujours reconnues par GDI / libass sous Windows
    standard_windows_fonts = {"arial", "calibri", "segoe ui", "tahoma", "verdana", "trebuchet ms", "times new roman", "courier new"}
    if clean_name in standard_windows_fonts:
        return True, font_name

    return False, fallback_font


class SubtitleStyle(BaseModel):
    """Configuration graphique complète d'un style de sous-titres pour l'incrustation."""
    font_name: str = Field("Arial", description="Nom de la police (ex: Arial, Impact, Trebuchet MS)")
    font_size: int = Field(26, description="Taille de police (adaptée à la résolution)")
    primary_color: str = Field("#FFFFFF", description="Couleur principale du texte")
    secondary_color: str = Field("#FFFF00", description="Couleur de surbrillance mot/karaoke")
    outline_color: str = Field("#000000", description="Couleur du contour")
    back_color: str = Field("#80000000", description="Couleur de l'ombre ou du bandeau d'arrière-plan")
    outline_width: float = Field(3.0, description="Épaisseur du contour")
    shadow_depth: float = Field(1.5, description="Décalage de l'ombre portée")
    border_style: int = Field(1, description="1 = Contour + Ombre, 3 = Bandeau rectangulaire opaque")
    alignment: int = Field(2, description="Alignement ASS (2 = bas-centré, 5 = haut-centré, 8 = milieu-centré)")
    margin_v: int = Field(380, description="Marge verticale en pixels")
    margin_l: int = Field(80, description="Marge gauche en pixels")
    margin_r: int = Field(120, description="Marge droite en pixels")
    uppercase: bool = Field(False, description="Force l'affichage de tout le texte en majuscules")
    safe_zone: Optional[SafeZoneConfig] = Field(None, description="Configuration de safe zone associée")
    highlight_current_word: bool = Field(False, description="Active la surbrillance mot par mot")

    def apply_safe_zone(self, safe_zone: SafeZoneConfig) -> "SubtitleStyle":
        """Met à jour les marges du style à partir d'une SafeZoneConfig."""
        self.safe_zone = safe_zone
        self.margin_l = safe_zone.left
        self.margin_r = safe_zone.right
        self.margin_v = safe_zone.bottom if safe_zone.vertical_anchor == "bottom" else safe_zone.top
        return self


def get_preset_style(
    preset: Union[SubtitlePresetName, str],
    target_width: int = 1080,
    target_height: int = 1920,
    fonts_dir: Optional[str] = None
) -> SubtitleStyle:
    """
    Construit une configuration SubtitleStyle prête à l'emploi selon le preset choisi
    et la résolution cible de la vidéo.
    """
    if isinstance(preset, str):
        try:
            preset_enum = SubtitlePresetName(preset.lower())
        except ValueError:
            preset_enum = SubtitlePresetName.TIKTOK_HIGH_CONTRAST
    else:
        preset_enum = preset

    # Ratio d'échelle par rapport à la référence 1080x1920
    scale_factor = min(target_width / 1080.0, target_height / 1920.0)
    # Éviter un facteur trop bas pour du 16:9 ou du 1:1
    if target_width > target_height:  # 16:9
        scale_factor = target_height / 1080.0
    elif target_width == target_height:  # 1:1
        scale_factor = target_height / 1080.0

    scale_factor = max(0.4, scale_factor)

    if preset_enum == SubtitlePresetName.TIKTOK_HIGH_CONTRAST:
        sz = get_safe_zone(SafeZonePreset.TIKTOK, target_width, target_height)
        font = "Trebuchet MS"
        is_avail, resolved_font = check_font_availability(font, fonts_dir)
        return SubtitleStyle(
            font_name=resolved_font,
            font_size=int(round(32 * scale_factor)),
            primary_color="#FFFF00",       # Jaune vif à fort impact visuel
            secondary_color="#FFFFFF",     # Blanc pour mot clé
            outline_color="#000000",
            back_color="#000000",
            outline_width=round(4.0 * scale_factor, 1),
            shadow_depth=round(2.0 * scale_factor, 1),
            border_style=1,
            alignment=2,                   # Bas centré
            margin_v=sz.bottom,
            margin_l=sz.left,
            margin_r=sz.right,
            uppercase=True,                # MAJUSCULES dynamiques
            safe_zone=sz,
            highlight_current_word=False
        )

    elif preset_enum == SubtitlePresetName.SHORTS_CLEAN:
        sz = get_safe_zone(SafeZonePreset.YOUTUBE_SHORTS, target_width, target_height)
        font = "Arial"
        is_avail, resolved_font = check_font_availability(font, fonts_dir)
        return SubtitleStyle(
            font_name=resolved_font,
            font_size=int(round(28 * scale_factor)),
            primary_color="#FFFFFF",       # Blanc pur
            secondary_color="#FFCC00",
            outline_color="#000000",
            back_color="#40000000",
            outline_width=round(3.0 * scale_factor, 1),
            shadow_depth=round(1.5 * scale_factor, 1),
            border_style=1,
            alignment=2,
            margin_v=sz.bottom,
            margin_l=sz.left,
            margin_r=sz.right,
            uppercase=False,
            safe_zone=sz,
            highlight_current_word=False
        )

    elif preset_enum == SubtitlePresetName.BOXED_HIGH_CONTRAST:
        sz = get_safe_zone(SafeZonePreset.GENERIC_9_16, target_width, target_height)
        font = "Arial"
        is_avail, resolved_font = check_font_availability(font, fonts_dir)
        return SubtitleStyle(
            font_name=resolved_font,
            font_size=int(round(26 * scale_factor)),
            primary_color="#FFFFFF",
            secondary_color="#00FFCC",
            outline_color="#000000",
            back_color="#CC000000",        # Bandeau noir semi-opaque (80% opacité)
            outline_width=round(1.5 * scale_factor, 1),
            shadow_depth=0.0,
            border_style=3,                # Bandeau d'arrière-plan opaque (box)
            alignment=2,
            margin_v=sz.bottom,
            margin_l=sz.left,
            margin_r=sz.right,
            uppercase=False,
            safe_zone=sz,
            highlight_current_word=False
        )

    elif preset_enum == SubtitlePresetName.MINIMAL:
        sz = get_safe_zone(SafeZonePreset.GENERIC_9_16, target_width, target_height)
        font = "Calibri"
        is_avail, resolved_font = check_font_availability(font, fonts_dir)
        return SubtitleStyle(
            font_name=resolved_font,
            font_size=int(round(24 * scale_factor)),
            primary_color="#F0F0F0",
            secondary_color="#FFFFFF",
            outline_color="#101010",
            back_color="#000000",
            outline_width=round(1.5 * scale_factor, 1),
            shadow_depth=round(1.0 * scale_factor, 1),
            border_style=1,
            alignment=2,
            margin_v=sz.bottom,
            margin_l=sz.left,
            margin_r=sz.right,
            uppercase=False,
            safe_zone=sz,
            highlight_current_word=False
        )

    # Fallback
    return SubtitleStyle()
