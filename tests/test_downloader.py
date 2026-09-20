"""
VideoCutPub - Unit and Integration Tests for URL Downloader (yt-dlp)
Validates platform detection, metadata extraction, Windows filename sanitization,
progress reporting, error classification, and QueueManager integration.
"""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.download_models import (
    DownloadQuality,
    VideoFormatOption,
    VideoInfo,
    DownloadProgress,
    DownloadResult,
)
from core.downloader import (
    VideoDownloader,
    sanitize_filename,
    format_bytes,
    format_speed,
)
from core.queue_manager import QueueManager
from ffmpeg.ffmpeg_manager import FFmpegManager


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="videocutpub_dl_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def downloader(temp_dir):
    return VideoDownloader(default_download_dir=str(temp_dir))


# ==========================================
# 1. Nettoyage de Noms de Fichiers & Formatage
# ==========================================

def test_sanitize_filename_windows_rules():
    """Vérifie que tous les caractères interdits sous Windows sont neutralisés."""
    raw = 'Vidéo: Pourquoi & Comment ? <Part 1> "Super*Test" | [HQ] /\\ test.mp4'
    cleaned = sanitize_filename(raw)
    for forbidden in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        assert forbidden not in cleaned
    assert len(cleaned) <= 120
    assert cleaned.strip() == cleaned


def test_sanitize_filename_empty_or_whitespace():
    """Vérifie qu'un nom vide produit un nom de secours sécurisé."""
    cleaned = sanitize_filename("   ")
    assert cleaned.startswith("video_")


def test_format_bytes_and_speed():
    """Vérifie le formatage lisible des octets et de la vitesse de téléchargement."""
    assert format_bytes(500) == "500.0 o"
    assert format_bytes(1024 * 1024 * 15) == "15.0 Mo"
    assert format_bytes(1024 * 1024 * 1024 * 2) == "2.0 Go"
    assert format_bytes(None) == "Taille inconnue"

    assert format_speed(1024 * 1024 * 3.5) == "3.5 Mo/s"
    assert format_speed(0) == "0 Mo/s"


# ==========================================
# 2. Détection des Plateformes
# ==========================================

def test_check_url_supported_platforms(downloader):
    """Vérifie que les principales plateformes sont reconnues."""
    # YouTube
    is_sup, ext = downloader.check_url_supported("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_sup is True
    assert "youtube" in ext.lower()

    # TikTok
    is_sup, ext = downloader.check_url_supported("https://www.tiktok.com/@user/video/123456789")
    assert is_sup is True
    assert "tiktok" in ext.lower()

    # Twitch
    is_sup, ext = downloader.check_url_supported("https://www.twitch.tv/videos/123456789")
    assert is_sup is True
    assert "twitch" in ext.lower()

    # Vimeo
    is_sup, ext = downloader.check_url_supported("https://vimeo.com/123456789")
    assert is_sup is True
    assert "vimeo" in ext.lower()

    # URL vide
    is_sup, _ = downloader.check_url_supported("")
    assert is_sup is False


# ==========================================
# 3. Extraction de Métadonnées (Mockée)
# ==========================================

def test_extract_info_mocked(downloader):
    """Vérifie l'extraction des métadonnées (titre, durée, miniature, résolutions) sans appel réseau réel."""
    mock_dict = {
        'id': 'abc12345',
        'title': 'Comment maîtriser Python en 2026',
        'extractor': 'youtube',
        'duration': 600.0,
        'uploader': 'DevChannel',
        'thumbnail': 'https://example.com/thumb.jpg',
        'description': 'Une vidéo passionnante sur le dev moderne.',
        'is_live': False,
        'view_count': 15000,
        'formats': [
            {'height': 360},
            {'height': 720},
            {'height': 1080},
        ]
    }

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = mock_dict

        info = downloader.extract_info("https://www.youtube.com/watch?v=abc12345")

        assert info.title == "Comment maîtriser Python en 2026"
        assert info.duration_seconds == 600.0
        assert info.uploader == "DevChannel"
        assert "1080p" in info.available_resolutions
        assert "720p" in info.available_resolutions
        assert info.is_live is False


def test_extract_info_drm_error(downloader):
    """Vérifie qu'un contenu protégé par DRM génère une exception explicite."""
    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.side_effect = Exception("This video is DRM protected and cannot be downloaded.")

        with pytest.raises(PermissionError) as exc_info:
            downloader.extract_info("https://streaming.example.com/protected")
        assert "DRM" in str(exc_info.value)


def test_extract_info_private_error(downloader):
    """Vérifie qu'une vidéo privée produit un message d'erreur d'authentification."""
    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.side_effect = Exception("Private video. Sign in if you've been granted access.")

        with pytest.raises(PermissionError) as exc_info:
            downloader.extract_info("https://youtube.com/watch?v=private")
        assert "privée" in str(exc_info.value).lower()


# ==========================================
# 4. Téléchargement et Métadonnées JSON
# ==========================================

def test_download_mocked_success(downloader, temp_dir):
    """Vérifie le cycle complet de téléchargement et la création de download_metadata.json."""
    fake_video = temp_dir / "test_download.mp4"
    fake_video.write_bytes(b"fake video mp4 content")

    mock_info = {
        'id': 'vid123',
        'title': 'Vidéo Test',
        'uploader': 'Auteur Test',
        'duration': 120.0,
        'extractor': 'youtube',
    }

    progress_events = []

    def on_progress(p: DownloadProgress):
        progress_events.append(p)

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = mock_info
        instance.prepare_filename.return_value = str(fake_video)

        res = downloader.download(
            url="https://youtube.com/watch?v=vid123",
            quality=DownloadQuality.RES_1080P,
            format_opt=VideoFormatOption.MP4,
            output_dir=str(temp_dir),
            progress_callback=on_progress
        )

        assert res.success is True
        assert res.title == "Vidéo Test"
        assert res.duration_seconds == 120.0
        assert Path(res.local_file_path).is_file()

        # Vérification du fichier download_metadata.json
        meta_file = Path(res.metadata_json_path)
        assert meta_file.is_file()
        meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
        assert meta_data["source_url"] == "https://youtube.com/watch?v=vid123"
        assert meta_data["selected_quality"] == "1080p"
        assert meta_data["original_title"] == "Vidéo Test"


def test_download_cancellation(downloader, temp_dir):
    """Vérifie que l'annulation stoppe le téléchargement proprement."""
    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        
        # Simule l'appel du hook avec cancel_check = True
        def fake_extract_info(url, download):
            hook = MockYDL.call_args[0][0]['progress_hooks'][0]
            hook({'status': 'downloading', 'downloaded_bytes': 100, 'total_bytes': 1000})
            return {}

        instance.extract_info.side_effect = fake_extract_info

        res = downloader.download(
            url="https://youtube.com/watch?v=cancel_me",
            output_dir=str(temp_dir),
            cancel_check=lambda: True  # Annulation immédiate
        )

        assert res.success is False
        assert "annulé" in res.error_message.lower()


# ==========================================
# 5. Intégration avec QueueManager
# ==========================================

def test_downloader_integration_with_queue(downloader, temp_dir):
    """Vérifie qu'une vidéo téléchargée s'intègre parfaitement à QueueManager."""
    downloaded_video = temp_dir / "imported_stream.mp4"
    downloaded_video.write_bytes(b"stream mp4 bytes")

    qm = QueueManager()
    job = qm.add_job(
        source_path=str(downloaded_video),
        output_base_dir=str(temp_dir / "output"),
        segment_duration="30s"
    )

    assert job.source_path == str(downloaded_video.resolve())
    assert len(qm.jobs) == 1
    assert qm.jobs[0].status.value == "pending"
