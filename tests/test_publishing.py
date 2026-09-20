"""
VideoCutPub - Unit and Integration Tests for Social Publishing Engine (Étape 10)
Validates PublishingJob lifecycle, AccountManager security, Manual/Semi-Auto modes,
mocked YouTube Data API v3, mocked TikTok Content Posting API, and manifest ingestion.
Zero real network calls (all HTTP requests are mocked).
"""

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from publishing.publishing_models import (
    PublishPlatform,
    PublishStatus,
    PrivacyLevel,
    AccountMetadata,
    AccountCredentials,
    PublishingJob,
)
from publishing.account_manager import AccountManager
from publishing.publisher_base import BasePublisher
from publishing.manual_publisher import ManualPublisher, META_WEB_PORTAL
from publishing.youtube_publisher import YouTubePublisher, YOUTUBE_UPLOAD_URL, YOUTUBE_TOKEN_URL, YOUTUBE_VIDEOS_URL
from publishing.tiktok_publisher import (
    TikTokPublisher,
    TIKTOK_CREATOR_INFO_URL,
    TIKTOK_INIT_UPLOAD_URL,
    TIKTOK_STATUS_FETCH_URL
)
from publishing.publish_queue import PublishQueueManager


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="videocutpub_publish_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def dummy_video(temp_dir):
    v = temp_dir / "sample_video.mp4"
    v.write_bytes(b"dummy mp4 video bytes 1234567890" * 100)
    return str(v.resolve())


@pytest.fixture
def dummy_thumb(temp_dir):
    t = temp_dir / "sample_thumb.jpg"
    t.write_bytes(b"dummy jpeg bytes 1234567890")
    return str(t.resolve())


# ==========================================
# 1. Modèle PublishingJob & États
# ==========================================

def test_publishing_job_lifecycle(dummy_video, dummy_thumb):
    """Vérifie le modèle, ses valeurs par défaut et ses transitions d'état."""
    job = PublishingJob(
        platform=PublishPlatform.YOUTUBE,
        account_id="yt_test",
        source_video=dummy_video,
        title="Super Titre Vidéo",
        description="Description SEO avec appel à l'action.",
        hashtags=["#video", "#shorts"],
        thumbnail=dummy_thumb,
        privacy=PrivacyLevel.PRIVATE
    )

    assert job.status == PublishStatus.READY
    assert job.retry_count == 0
    assert job.requires_user_consent is False
    assert job.user_consented_at is None
    assert job.job_id is not None

    # Transition vers UPLOADING puis PUBLISHED
    job.status = PublishStatus.UPLOADING
    job.remote_id = "yt_vid_abc123"
    assert job.status == PublishStatus.UPLOADING

    job.status = PublishStatus.PUBLISHED
    job.platform_post_id = "yt_vid_abc123"
    assert job.status == PublishStatus.PUBLISHED


# ==========================================
# 2. AccountManager & Sécurité des Credentials
# ==========================================

def test_account_manager_separation_and_security(temp_dir):
    """
    Vérifie l'isolation des données sensibles :
    les secrets (client_secret, access_token, refresh_token) ne doivent JAMAIS
    apparaître en clair dans accounts.json.
    """
    am = AccountManager(base_dir=str(temp_dir / "creds"))

    # Ajout Compte A (YouTube)
    acc_a = AccountCredentials(
        account_id="yt_channel_a",
        platform=PublishPlatform.YOUTUBE,
        display_name="Chaîne YouTube Principale",
        client_id="client_id_secret_123",
        client_secret="SUPER_SECRET_CLIENT_KEY",
        access_token="ya29.ACCESS_TOKEN_XYZ",
        refresh_token="1//REFRESH_TOKEN_ABC",
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    meta_a = am.add_account(acc_a)
    assert meta_a.account_id == "yt_channel_a"

    # Ajout Compte B (TikTok)
    acc_b = AccountCredentials(
        account_id="tiktok_user_b",
        platform=PublishPlatform.TIKTOK,
        display_name="@MonCompteTikTok",
        client_id="tiktok_client_key",
        client_secret="TIKTOK_SECRET_999",
        access_token="act.TIKTOK_TOKEN_456",
        refresh_token="rft.TIKTOK_REFRESH_789"
    )
    am.add_account(acc_b)

    # Vérification du fichier accounts.json : AUCUN SECRET EN CLAIR
    json_path = temp_dir / "creds" / "accounts.json"
    assert json_path.is_file()
    raw_json = json_path.read_text(encoding="utf-8")

    assert "SUPER_SECRET_CLIENT_KEY" not in raw_json
    assert "ya29.ACCESS_TOKEN_XYZ" not in raw_json
    assert "1//REFRESH_TOKEN_ABC" not in raw_json
    assert "TIKTOK_SECRET_999" not in raw_json

    # Vérification de la reconstitution des secrets via get_account_credentials
    retrieved_a = am.get_account_credentials("yt_channel_a")
    assert retrieved_a is not None
    assert retrieved_a.client_secret == "SUPER_SECRET_CLIENT_KEY"
    assert retrieved_a.access_token == "ya29.ACCESS_TOKEN_XYZ"
    assert retrieved_a.refresh_token == "1//REFRESH_TOKEN_ABC"

    # Multi-comptes : filtrage par plateforme
    yt_accounts = am.list_accounts(platform=PublishPlatform.YOUTUBE)
    assert len(yt_accounts) == 1
    assert yt_accounts[0].account_id == "yt_channel_a"

    tt_accounts = am.list_accounts(platform=PublishPlatform.TIKTOK)
    assert len(tt_accounts) == 1
    assert tt_accounts[0].account_id == "tiktok_user_b"

    # Mise à jour des tokens
    am.update_tokens("yt_channel_a", access_token="ya29.NEW_ACCESS_TOKEN")
    updated_a = am.get_account_credentials("yt_channel_a")
    assert updated_a.access_token == "ya29.NEW_ACCESS_TOKEN"

    # Suppression
    assert am.remove_account("yt_channel_a") is True
    assert am.get_account_credentials("yt_channel_a") is None


def test_gitignore_protects_credentials():
    """Vérifie que le .gitignore racine contient bien les exclusions nécessaires."""
    gitignore = Path(".gitignore")
    assert gitignore.exists()
    content = gitignore.read_text(encoding="utf-8")
    assert ".credentials/" in content
    assert "tokens/" in content
    assert "client_secret*.json" in content


# ==========================================
# 3. Mode Manuel & Semi-Automatique
# ==========================================

def test_manual_publisher_formatting_and_execution(dummy_video, dummy_thumb):
    """Vérifie le formatage du presse-papier et la séquence semi-automatique."""
    publisher = ManualPublisher()
    job = PublishingJob(
        platform=PublishPlatform.MANUAL,
        source_video=dummy_video,
        title="Titre Virale",
        description="Description complète pour les réseaux sociaux.",
        hashtags=["#conseil", "#reels"],
        thumbnail=dummy_thumb
    )

    clip_text = publisher.format_clipboard_text(job)
    assert "TITRE :\nTitre Virale" in clip_text
    assert "HASHTAGS :\n#conseil #reels" in clip_text
    assert dummy_video in clip_text
    assert dummy_thumb in clip_text

    # Configuration dynamique du portail Meta
    publisher.set_meta_portal_url("https://business.facebook.com/latest/content_calendar")
    assert publisher.platform_urls[PublishPlatform.MANUAL] == "https://business.facebook.com/latest/content_calendar"

    # Exécution avec mocks des ouvertures système (navigateur et explorateur)
    with patch("webbrowser.open") as mock_browser, \
         patch.object(publisher, "copy_to_clipboard", return_value=True) as mock_clip, \
         patch.object(publisher, "open_local_file_or_dir", return_value=True) as mock_explorer:

        res = publisher.publish(job)
        assert res.status == PublishStatus.PUBLISHED
        assert mock_clip.called
        assert mock_browser.called
        assert mock_explorer.called


# ==========================================
# 4. YouTube Publisher (API Mockée)
# ==========================================

def test_youtube_publisher_mocked_upload(dummy_video, dummy_thumb):
    """Vérifie le cycle complet de téléversement YouTube Data v3 avec mocks."""
    publisher = YouTubePublisher()
    job = PublishingJob(
        platform=PublishPlatform.YOUTUBE,
        account_id="yt_user_1",
        source_video=dummy_video,
        title="Titre YouTube Vidéo",
        description="Description YouTube",
        hashtags=["#test", "#youtube"],
        thumbnail=dummy_thumb,
        privacy=PrivacyLevel.PRIVATE
    )

    creds = AccountCredentials(
        account_id="yt_user_1",
        platform=PublishPlatform.YOUTUBE,
        display_name="User YouTube",
        client_id="cid",
        client_secret="csec",
        access_token="mock_yt_access_token",
        refresh_token="mock_yt_refresh_token"
    )

    # 1. Mock de l'init resumable
    mock_init_resp = MagicMock()
    mock_init_resp.status_code = 200
    mock_init_resp.headers = {"Location": "https://upload.youtube.test/session_123"}

    # 2. Mock du transfert binaire
    mock_up_resp = MagicMock()
    mock_up_resp.status_code = 200
    mock_up_resp.json.return_value = {"id": "yt_video_id_999"}

    # 3. Mock thumbnail
    mock_thumb_resp = MagicMock()
    mock_thumb_resp.status_code = 200

    # 4. Mock status
    mock_stat_resp = MagicMock()
    mock_stat_resp.status_code = 200
    mock_stat_resp.json.return_value = {
        "items": [{"status": {"uploadStatus": "processed"}}]
    }

    with patch("requests.Session.post") as mock_post, \
         patch("requests.Session.put") as mock_put, \
         patch("requests.get") as mock_get:

        mock_post.side_effect = [mock_init_resp, mock_thumb_resp]
        mock_put.return_value = mock_up_resp
        mock_get.return_value = mock_stat_resp

        res = publisher.publish(job, credentials=creds)

        assert res.status == PublishStatus.PUBLISHED
        assert res.remote_id == "yt_video_id_999"
        assert res.upload_session_id == "https://upload.youtube.test/session_123"


def test_youtube_publisher_quota_error(dummy_video):
    """Vérifie la gestion correcte d'une erreur 403 quotaExceeded."""
    publisher = YouTubePublisher()
    job = PublishingJob(
        platform=PublishPlatform.YOUTUBE,
        source_video=dummy_video,
        title="Titre Quota"
    )
    creds = AccountCredentials(
        account_id="yt_q", platform=PublishPlatform.YOUTUBE,
        display_name="Q", access_token="token_q"
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.json.return_value = {"error": {"message": "The request cannot be completed because you have exceeded your quota."}}

    with patch("requests.Session.post", return_value=mock_resp):
        res = publisher.publish(job, credentials=creds)
        assert res.status == PublishStatus.FAILED
        assert res.last_error_code == "INIT_FAILED"
        assert "QUOTA_EXCEEDED" in res.last_error_message


# ==========================================
# 5. TikTok Publisher (API Mockée)
# ==========================================

def test_tiktok_publisher_enforces_consent(dummy_video):
    """Vérifie que TikTok refuse catégoriquement de publier sans consentement explicite."""
    publisher = TikTokPublisher()
    job = PublishingJob(
        platform=PublishPlatform.TIKTOK,
        source_video=dummy_video,
        title="TikTok Sans Consentement",
        requires_user_consent=True,
        user_consented_at=None  # Non consenti
    )
    creds = AccountCredentials(
        account_id="tt_noconsent", platform=PublishPlatform.TIKTOK,
        display_name="User", access_token="valid_token"
    )

    res = publisher.publish(job, credentials=creds)
    assert res.status == PublishStatus.FAILED
    assert res.last_error_code == "CONSENT_REQUIRED"


def test_tiktok_publisher_mocked_direct_post(dummy_video):
    """Vérifie la séquence complète TikTok (creator_info -> init -> upload -> status)."""
    publisher = TikTokPublisher()
    job = PublishingJob(
        platform=PublishPlatform.TIKTOK,
        source_video=dummy_video,
        title="Titre TikTok Officiel",
        requires_user_consent=True,
        user_consented_at=datetime.now()
    )
    creds = AccountCredentials(
        account_id="tt_ok", platform=PublishPlatform.TIKTOK,
        display_name="User", access_token="valid_token"
    )

    # 1. Mock creator_info
    mock_info = MagicMock()
    mock_info.status_code = 200
    mock_info.json.return_value = {
        "error": {"code": "ok"},
        "data": {"privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"]}
    }

    # 2. Mock init
    mock_init = MagicMock()
    mock_init.status_code = 200
    mock_init.json.return_value = {
        "error": {"code": "ok"},
        "data": {
            "publish_id": "v_pub_id_tiktok_12345",
            "upload_url": "https://upload.tiktokapis.test/chunk_upload"
        }
    }

    # 3. Mock put chunk
    mock_put = MagicMock()
    mock_put.status_code = 200

    # 4. Mock status fetch
    mock_status = MagicMock()
    mock_status.status_code = 200
    mock_status.json.return_value = {
        "error": {"code": "ok"},
        "data": {
            "status": "SUCCESS",
            "publicly_available_post_id": 987654321
        }
    }

    with patch("requests.Session.post") as mock_post_session, \
         patch("requests.Session.put", return_value=mock_put), \
         patch("requests.post", return_value=mock_status):

        mock_post_session.side_effect = [mock_info, mock_init]

        res = publisher.publish(job, credentials=creds)
        assert res.status == PublishStatus.PUBLISHED
        assert res.remote_id == "v_pub_id_tiktok_12345"
        assert res.platform_post_id == "987654321"


# ==========================================
# 6. PublishQueueManager & Ingestion de Manifeste
# ==========================================

def test_publish_queue_from_pack_manifest(dummy_video, dummy_thumb, temp_dir):
    """Vérifie la création d'un PublishingJob depuis un dossier Social Pack et son pack_metadata.json."""
    pack_dir = temp_dir / "social_pack" / "Segment 01"
    pack_dir.mkdir(parents=True, exist_ok=True)

    # Copie des fichiers de test dans le dossier du pack
    shutil.copy2(dummy_video, pack_dir / "video_subtitled.mp4")
    shutil.copy2(dummy_video, pack_dir / "video.mp4")
    shutil.copy2(dummy_thumb, pack_dir / "thumbnail.jpg")

    # Manifeste unique pack_metadata.json
    manifest_data = {
        "source_video": "source_originale.mp4",
        "segment": 1,
        "formats": {
            "original": str(dummy_video),
            "vertical_9x16": "video.mp4"
        },
        "subtitles": {
            "srt": "subtitles.srt",
            "ass": "subtitles.ass",
            "burned_in": "video_subtitled.mp4"
        },
        "metadata": {
            "title": "Titre Depuis Manifeste",
            "hooks": ["Accroche 1", "Accroche 2"],
            "description": "Description depuis manifeste Social Pack",
            "hashtags": ["#pack", "#viral"]
        },
        "thumbnail": "thumbnail.jpg",
        "publishing": {"youtube": "ready", "tiktok": "ready"}
    }
    (pack_dir / "pack_metadata.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    qm = PublishQueueManager(base_dir=str(temp_dir))
    job = qm.create_job_from_pack(str(pack_dir), platform=PublishPlatform.YOUTUBE)

    assert job.title == "Titre Depuis Manifeste"
    assert job.description == "Description depuis manifeste Social Pack"
    assert job.hashtags == ["#pack", "#viral"]
    # Préfère la vidéo avec sous-titres incrustés
    assert Path(job.source_video).name == "video_subtitled.mp4"
    assert Path(job.thumbnail).name == "thumbnail.jpg"

    # Gestion de la file d'attente
    qm.add_job(job)
    assert len(qm.jobs) == 1

    # Annulation
    assert qm.cancel_job(job.job_id) is True
    assert job.status == PublishStatus.CANCELLED

    # Réinitialisation / Retry
    job.status = PublishStatus.FAILED
    assert qm.retry_job(job.job_id) is True
    assert job.status == PublishStatus.READY
    assert job.retry_count == 1
