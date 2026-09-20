"""
VideoCutPub - Subtitle Styling and Rendering Module
"""

from subtitles.safe_zone import SafeZoneConfig, SafeZonePreset, get_safe_zone
from subtitles.style import (
    SubtitleStyle,
    SubtitlePresetName,
    get_preset_style,
    hex_to_ass_color,
    check_font_availability,
)
from subtitles.ass_generator import (
    ASSGenerator,
    seconds_to_ass_timestamp,
    srt_timestamp_to_ass_timestamp,
    parse_srt_file,
)
from subtitles.renderer import (
    SubtitleRenderer,
    BurnJob,
    BurnResult,
    escape_ffmpeg_filter_path,
)

__all__ = [
    "SafeZoneConfig",
    "SafeZonePreset",
    "get_safe_zone",
    "SubtitleStyle",
    "SubtitlePresetName",
    "get_preset_style",
    "hex_to_ass_color",
    "check_font_availability",
    "ASSGenerator",
    "seconds_to_ass_timestamp",
    "srt_timestamp_to_ass_timestamp",
    "parse_srt_file",
    "SubtitleRenderer",
    "BurnJob",
    "BurnResult",
    "escape_ffmpeg_filter_path",
]
