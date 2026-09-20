"""
VideoCutPub - Comprehensive Test Suite for Subtitles Engine (Étape 7)
Tests SubtitleStyle, ASSGenerator, SafeZones, Word Timestamps, Font Fallback,
Windows Path Escaping, and Real FFmpeg Subtitle Burn-In.
"""

import os
import shutil
import tempfile
from pathlib import Path
import pytest

from ai.transcription import TranscriptSegment, TranscriptWord
from ffmpeg.ffmpeg_manager import FFmpegManager
from core.video_analyzer import VideoAnalyzer
from subtitles.safe_zone import (
    SafeZoneConfig,
    SafeZonePreset,
    get_safe_zone,
)
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


@pytest.fixture(scope="module")
def ffmpeg_mgr():
    return FFmpegManager()


@pytest.fixture(scope="module")
def analyzer(ffmpeg_mgr):
    return VideoAnalyzer(ffmpeg_mgr)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="videocutpub_sub_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def create_synthetic_video(ffmpeg_mgr: FFmpegManager, out_path: Path, duration: int = 1, width: int = 640, height: int = 360, with_audio: bool = True):
    """Génère une vraie vidéo MP4 synthétique légère pour les tests d'incrustation."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if with_audio:
        cmd = [
            "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=30",
            "-f", "lavfi", "-i", f"aevalsrc=0:d={duration}:s=44100",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k",
            str(out_path)
        ]
    else:
        cmd = [
            "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-an",
            str(out_path)
        ]
    ffmpeg_mgr.run_ffmpeg(cmd)


# ==========================================
# 1. Modèles, Styles et Presets
# ==========================================

def test_subtitle_style_model():
    """Vérifie la création et la sérialisation du modèle SubtitleStyle."""
    style = SubtitleStyle(
        font_name="Arial",
        font_size=28,
        primary_color="#FFFFFF",
        outline_width=2.5,
        uppercase=True
    )
    assert style.font_name == "Arial"
    assert style.font_size == 28
    assert style.uppercase is True
    assert style.alignment == 2


def test_style_presets_naming_and_properties():
    """Vérifie tous les presets sans noms marketing (TIKTOK_HIGH_CONTRAST, SHORTS_CLEAN, etc.)."""
    presets = [
        SubtitlePresetName.TIKTOK_HIGH_CONTRAST,
        SubtitlePresetName.SHORTS_CLEAN,
        SubtitlePresetName.BOXED_HIGH_CONTRAST,
        SubtitlePresetName.MINIMAL
    ]
    for p in presets:
        st = get_preset_style(p, 1080, 1920)
        assert st.font_size > 0
        assert st.outline_width >= 0
        assert st.margin_v > 0
        assert st.safe_zone is not None

    # TIKTOK_HIGH_CONTRAST utilise le texte jaune et uppercase
    tiktok_st = get_preset_style(SubtitlePresetName.TIKTOK_HIGH_CONTRAST, 1080, 1920)
    assert tiktok_st.primary_color == "#FFFF00"
    assert tiktok_st.uppercase is True

    # BOXED_HIGH_CONTRAST utilise border_style=3 (bandeau opaque)
    boxed_st = get_preset_style(SubtitlePresetName.BOXED_HIGH_CONTRAST, 1080, 1920)
    assert boxed_st.border_style == 3


def test_color_conversion_hex_to_ass():
    """Vérifie la conversion correcte des couleurs Hex vers le format ASS &HAABBGGRR."""
    # Blanc opaque #FFFFFF -> &H00FFFFFF
    assert hex_to_ass_color("#FFFFFF") == "&H00FFFFFF"
    # Noir opaque #000000 -> &H00000000
    assert hex_to_ass_color("#000000") == "&H00000000"
    # Jaune #FFFF00 (R=FF, G=FF, B=00) -> &H0000FFFF (BB=00, GG=FF, RR=FF)
    assert hex_to_ass_color("#FFFF00") == "&H0000FFFF"
    # Rouge #FF0000 (R=FF, G=00, B=00) -> &H000000FF (BB=00, GG=00, RR=FF)
    assert hex_to_ass_color("#FF0000") == "&H000000FF"
    # Bleu #0000FF (R=00, G=00, B=FF) -> &H00FF0000 (BB=FF, GG=00, RR=00)
    assert hex_to_ass_color("#0000FF") == "&H00FF0000"
    # Avec canal Alpha 80 (50% transparent)
    assert hex_to_ass_color("#80FFFFFF") == "&H80FFFFFF"


# ==========================================
# 2. Safe Zones et Résolutions
# ==========================================

def test_safe_zone_configs_and_anchors():
    """Vérifie la configuration des Safe Zones et les ancrages par défaut."""
    sz = get_safe_zone(SafeZonePreset.TIKTOK, 1080, 1920)
    assert sz.bottom >= 350
    assert sz.right >= 120
    assert sz.horizontal_anchor == "center"
    assert sz.vertical_anchor == "bottom"


def test_safe_zone_multi_resolutions():
    """Vérifie l'adaptation des Safe Zones pour 9:16, 1:1, 16:9 et 720x1280."""
    # 9:16 (1080x1920)
    sz_9_16 = get_safe_zone(SafeZonePreset.GENERIC_9_16, 1080, 1920)
    assert sz_9_16.bottom == 350

    # 9:16 réduit (720x1280) proportionnel
    sz_720 = get_safe_zone(SafeZonePreset.GENERIC_9_16, 720, 1280)
    expected_bottom = int(round(350 * (1280 / 1920)))
    assert sz_720.bottom == expected_bottom

    # 1:1 (1080x1080)
    sz_1_1 = get_safe_zone(SafeZonePreset.GENERIC_1_1, 1080, 1080)
    assert sz_1_1.bottom == 120

    # 16:9 (1920x1080)
    sz_16_9 = get_safe_zone(SafeZonePreset.GENERIC_16_9, 1920, 1080)
    assert sz_16_9.bottom == 90


# ==========================================
# 3. Génération ASS et Timestamps
# ==========================================

def test_timestamps_ass_format():
    """Vérifie le format des timestamps ASS : H:MM:SS.cc."""
    assert seconds_to_ass_timestamp(0.0) == "0:00:00.00"
    assert seconds_to_ass_timestamp(1.25) == "0:00:01.25"
    assert seconds_to_ass_timestamp(65.5) == "0:01:05.50"
    assert seconds_to_ass_timestamp(3661.12) == "1:01:01.12"


def test_ass_generation_from_segments(temp_dir):
    """Vérifie la génération complète d'un fichier .ass avec Script Info, Styles et Dialogue."""
    segments = [
        TranscriptSegment(
            index=1,
            start_sec=0.0,
            end_sec=2.5,
            start_srt="00:00:00,000",
            end_srt="00:00:02,500",
            text="Bonjour et bienvenue",
            confidence=0.95
        ),
        TranscriptSegment(
            index=2,
            start_sec=2.5,
            end_sec=5.0,
            start_srt="00:00:02,500",
            end_srt="00:00:05,000",
            text="dans cette nouvelle vidéo.",
            confidence=0.92
        )
    ]

    gen = ASSGenerator(width=1080, height=1920)
    ass_file = temp_dir / "test.ass"
    out_path = gen.export_to_file(segments, ass_file)

    assert Path(out_path).is_file()
    content = Path(out_path).read_text(encoding="utf-8")

    assert "[Script Info]" in content
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content
    assert "Dialogue: 0,0:00:00.00,0:00:02.50,Default,,0,0,0,,BONJOUR ET BIENVENUE" in content or "Bonjour" in content


def test_ass_generation_from_srt(temp_dir):
    """Vérifie le parsing d'un fichier .srt existant et son export en .ass."""
    srt_file = temp_dir / "sample.srt"
    srt_file.write_text(
        "1\n00:00:01,000 --> 00:00:03,500\nPremier sous-titre\n\n2\n00:00:04,200 --> 00:00:06,800\nDeuxième ligne\n",
        encoding="utf-8"
    )

    gen = ASSGenerator(style=get_preset_style(SubtitlePresetName.SHORTS_CLEAN, 1920, 1080), width=1920, height=1080)
    ass_file = temp_dir / "from_srt.ass"
    gen.export_to_file(srt_file, ass_file)

    assert ass_file.is_file()
    content = ass_file.read_text(encoding="utf-8")
    assert "Premier sous-titre" in content
    assert "Deuxième ligne" in content
    assert "0:00:01.00" in content


def test_word_timestamps_preservation_and_karaoke(temp_dir):
    """Vérifie la rétention des horodatages par mot et la génération des balises karaoke."""
    words = [
        TranscriptWord(word="Voici", start=0.0, end=0.4, probability=0.99),
        TranscriptWord(word="le", start=0.4, end=0.6, probability=0.98),
        TranscriptWord(word="résultat", start=0.6, end=1.2, probability=0.95),
    ]
    seg = TranscriptSegment(
        index=1,
        start_sec=0.0,
        end_sec=1.2,
        start_srt="00:00:00,000",
        end_srt="00:00:01,200",
        text="Voici le résultat",
        confidence=0.98,
        words=words
    )

    style = SubtitleStyle(highlight_current_word=True)
    gen = ASSGenerator(style=style, width=1080, height=1920)
    ass_content = gen.generate_ass_content([seg])

    assert "{\\k40}Voici" in ass_content
    assert "{\\k20}le" in ass_content
    assert "{\\k60}résultat" in ass_content


# ==========================================
# 4. Polices & Repli Sécurisé (Fallback)
# ==========================================

def test_font_availability_and_fallback():
    """Vérifie que les polices inconnues utilisent un repli sécurisé 'Arial'."""
    is_avail, resolved = check_font_availability("PoliceTotalementInexistante12345")
    assert is_avail is False
    assert resolved == "Arial"

    is_avail_arial, resolved_arial = check_font_availability("Arial")
    assert is_avail_arial is True
    assert resolved_arial == "Arial"


# ==========================================
# 5. Échappement Chemins Windows & Accents
# ==========================================

def test_windows_path_escaping():
    """Vérifie l'échappement rigoureux pour les filtres FFmpeg avec espaces, colons et accents."""
    win_path = r"C:\Video\Mon dossier spécial\Vidéo été 2026.ass"
    escaped = escape_ffmpeg_filter_path(win_path)

    # Ne doit pas contenir de backslashes non échappés
    assert "\\" not in escaped or r"\:" in escaped
    # Le deux-points du lecteur C: doit être échappé C\:
    assert r"\:" in escaped
    # Les accents et espaces doivent être préservés
    assert "spécial" in escaped
    assert "été" in escaped


# ==========================================
# 6. Incrustation Réelle (Burn-In Execution)
# ==========================================

def test_subtitle_burn_in_real_video(ffmpeg_mgr, analyzer, temp_dir):
    """
    Test d'intégration complet : incrustation de sous-titres ASS dans une vidéo réelle.
    Vérifie la conservation de la durée, de la résolution et de la piste audio.
    """
    video_path = temp_dir / "source.mp4"
    create_synthetic_video(ffmpeg_mgr, video_path, duration=2, width=640, height=360, with_audio=True)

    initial_mtime = video_path.stat().st_mtime
    initial_size = video_path.stat().st_size

    # Création du fichier ASS
    ass_path = temp_dir / "subtitles.ass"
    segments = [
        TranscriptSegment(
            index=1,
            start_sec=0.0,
            end_sec=1.5,
            start_srt="00:00:00,000",
            end_srt="00:00:01,500",
            text="Test Sous-titre Incrusté",
            confidence=0.99
        )
    ]
    gen = ASSGenerator(width=640, height=360)
    gen.export_to_file(segments, ass_path)

    renderer = SubtitleRenderer(ffmpeg_mgr, analyzer)
    job = BurnJob(
        video_path=str(video_path),
        subtitle_path=str(ass_path),
        output_dir=str(temp_dir / "rendered")
    )

    result = renderer.burn(job)

    # 1. Succès du rendu
    assert result.success is True
    assert Path(result.output_video).is_file()

    # 2. Dimensions et durée conservées
    assert result.width == 640
    assert result.height == 360
    assert result.duration_seconds >= 1.9

    # 3. Audio conservé
    assert result.has_audio is True

    # 4. Vidéo source originale intacte (non-destructif)
    assert video_path.stat().st_size == initial_size
    assert video_path.stat().st_mtime == initial_mtime


def test_subtitle_burn_in_silent_video(ffmpeg_mgr, analyzer, temp_dir):
    """Vérifie qu'une vidéo sans piste audio est incrustée correctement sans erreur (-an)."""
    silent_path = temp_dir / "silent.mp4"
    create_synthetic_video(ffmpeg_mgr, silent_path, duration=1, width=320, height=180, with_audio=False)

    ass_path = temp_dir / "sub_silent.ass"
    gen = ASSGenerator(width=320, height=180)
    gen.export_to_file([
        TranscriptSegment(
            index=1, start_sec=0.0, end_sec=0.8,
            start_srt="00:00:00,000", end_srt="00:00:00,800",
            text="Silence", confidence=1.0
        )
    ], ass_path)

    renderer = SubtitleRenderer(ffmpeg_mgr, analyzer)
    job = BurnJob(video_path=str(silent_path), subtitle_path=str(ass_path))
    result = renderer.burn(job)

    assert result.success is True
    assert result.has_audio is False
    assert Path(result.output_video).is_file()


def test_batch_burn_orchestration(ffmpeg_mgr, analyzer, temp_dir):
    """Vérifie l'orchestration séquentielle d'une file de rendus batch_burn()."""
    v1 = temp_dir / "v1.mp4"
    v2 = temp_dir / "v2.mp4"
    create_synthetic_video(ffmpeg_mgr, v1, duration=1, width=320, height=180, with_audio=False)
    create_synthetic_video(ffmpeg_mgr, v2, duration=1, width=320, height=180, with_audio=False)

    ass_path = temp_dir / "batch.ass"
    gen = ASSGenerator(width=320, height=180)
    gen.export_to_file([
        TranscriptSegment(
            index=1, start_sec=0.0, end_sec=0.5,
            start_srt="00:00:00,000", end_srt="00:00:00,500",
            text="Batch", confidence=1.0
        )
    ], ass_path)

    jobs = [
        BurnJob(video_path=str(v1), subtitle_path=str(ass_path), output_dir=str(temp_dir / "rendered")),
        BurnJob(video_path=str(v2), subtitle_path=str(ass_path), output_dir=str(temp_dir / "rendered")),
        BurnJob(video_path=str(temp_dir / "inexistant.mp4"), subtitle_path=str(ass_path))  # Erreur isolée
    ]

    renderer = SubtitleRenderer(ffmpeg_mgr, analyzer)
    results = renderer.batch_burn(jobs)

    assert len(results) == 3
    assert results[0].success is True
    assert results[1].success is True
    assert results[2].success is False  # Fichier inexistant échoue proprement sans planter les autres
