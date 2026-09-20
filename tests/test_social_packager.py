"""
VideoCutPub - Unit and Integration Tests for Social Packager Engine (Étape 9)
Validates thumbnail extraction, segment packaging, standardized deliverables,
metadata JSON exports, and batch pack summary creation.
"""

import json
import shutil
import tempfile
from pathlib import Path
import pytest

from ffmpeg.ffmpeg_manager import FFmpegManager
from core.video_analyzer import VideoAnalyzer
from ai.metadata_generator import SocialMetadata
from publishing.social_packager import SocialPackager, SegmentPack, PackSummary


@pytest.fixture(scope="module")
def ffmpeg_mgr():
    mgr = FFmpegManager()
    if not mgr.is_available():
        pytest.skip("FFmpeg non disponible")
    return mgr


@pytest.fixture(scope="module")
def analyzer(ffmpeg_mgr):
    return VideoAnalyzer(ffmpeg_mgr)


@pytest.fixture(scope="module")
def packager(ffmpeg_mgr, analyzer):
    return SocialPackager(ffmpeg_mgr, analyzer)


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory, ffmpeg_mgr):
    """Génère une vidéo de test 360x640 de 3 secondes avec audio."""
    temp_dir = tmp_path_factory.mktemp("pack_media")
    video_path = temp_dir / "test_seg_01.mp4"
    args = [
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=360x640:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
        "-c:v", "libx264", "-c:a", "aac",
        str(video_path)
    ]
    ffmpeg_mgr.run_ffmpeg(args)
    return str(video_path)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="videocutpub_pack_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ==========================================
# 1. Extraction de Miniature (Thumbnail)
# ==========================================

def test_extract_thumbnail(packager, sample_video, temp_dir):
    """Vérifie l'extraction d'une miniature JPEG haute définition."""
    thumb_path = temp_dir / "thumb.jpg"
    res = packager.extract_thumbnail(sample_video, str(thumb_path), timestamp_sec=1.0)

    assert Path(res).is_file()
    assert Path(res).stat().st_size > 0
    assert thumb_path.exists()


def test_extract_thumbnail_auto_timestamp(packager, sample_video, temp_dir):
    """Vérifie que le calcul automatique à 25% fonctionne sans timestamp explicite."""
    thumb_path = temp_dir / "thumb_auto.jpg"
    res = packager.extract_thumbnail(sample_video, str(thumb_path))

    assert Path(res).is_file()
    assert Path(res).stat().st_size > 0


# ==========================================
# 2. Packaging d'un Segment Unique
# ==========================================

def test_create_segment_pack(packager, sample_video, temp_dir):
    """Vérifie la création complète du dossier autonome pour un segment."""
    # Création de fichiers auxiliaires factices
    srt_file = temp_dir / "test.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:02,000\nTest sous-titre\n", encoding="utf-8")

    ass_file = temp_dir / "test.ass"
    ass_file.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")

    fake_meta = SocialMetadata(
        title="Arrête tout !",
        hooks=["Accroche 1", "Accroche 2", "Accroche 3"],
        description="Description optimisée pour la vidéo.",
        hashtags=["#video", "#viral", "#tech"],
        detected_topic="Tech & Informatique",
        keywords=["video", "test"]
    )

    pack = packager.create_segment_pack(
        segment_index=1,
        output_base_dir=str(temp_dir),
        video_path=sample_video,
        subtitled_video_path=sample_video,
        srt_path=str(srt_file),
        ass_path=str(ass_file),
        metadata=fake_meta,
        copy_files=True
    )

    assert pack.success is True
    assert pack.segment_index == 1

    seg_dir = Path(pack.pack_dir)
    assert seg_dir.is_dir()
    assert (seg_dir / "video.mp4").is_file()
    assert (seg_dir / "video_subtitled.mp4").is_file()
    assert (seg_dir / "subtitles.srt").is_file()
    assert (seg_dir / "subtitles.ass").is_file()
    assert (seg_dir / "thumbnail.jpg").is_file()
    assert (seg_dir / "post_content.txt").is_file()
    assert (seg_dir / "pack_metadata.json").is_file()

    # Vérification du contenu de pack_metadata.json
    meta_json = json.loads((seg_dir / "pack_metadata.json").read_text(encoding="utf-8"))
    assert meta_json["segment_index"] == 1
    assert meta_json["files"]["video"] == "video.mp4"
    assert meta_json["files"]["thumbnail"] == "thumbnail.jpg"
    assert meta_json["metadata"]["title"] == "Arrête tout !"


# ==========================================
# 3. Packaging Global de Job & pack_summary.json
# ==========================================

def test_package_job_assets(packager, sample_video, temp_dir):
    """Vérifie l'assemblage complet de plusieurs segments et la synthèse pack_summary.json."""
    segments_data = [
        {
            "segment_index": 1,
            "video_path": sample_video,
            "subtitled_video_path": None,
            "srt_path": None,
            "ass_path": None,
            "metadata": None
        },
        {
            "segment_index": 2,
            "video_path": sample_video,
            "subtitled_video_path": None,
            "srt_path": None,
            "ass_path": None,
            "metadata": None
        }
    ]

    summary = packager.package_job_assets(
        source_file="source_longue.mp4",
        output_dir=str(temp_dir),
        segments_data=segments_data
    )

    assert summary.total_packs == 2
    assert len(summary.packs) == 2
    assert Path(summary.summary_json_path).is_file()

    summary_json = json.loads(Path(summary.summary_json_path).read_text(encoding="utf-8"))
    assert summary_json["total_packs"] == 2
    assert summary_json["source_file"] == "source_longue.mp4"


# ==========================================
# 4. Intégration End-to-End dans QueueManager
# ==========================================

def test_queue_manager_with_social_pack(ffmpeg_mgr, sample_video, temp_dir):
    """Vérifie l'intégration complète de bout en bout dans QueueManager avec packaging automatique."""
    from core.video_cutter import VideoCutter
    from core.queue_manager import QueueManager

    qm = QueueManager(VideoCutter(ffmpeg_mgr))
    out_dir = temp_dir / "queue_pack_out"

    job = qm.add_job(sample_video, str(out_dir), segment_duration=2)
    job.package_social = True
    job.transcribe = False

    results = qm.process_queue()
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].pack_summary_path is not None
    assert Path(results[0].pack_summary_path).is_file()

    summary_json = json.loads(Path(results[0].pack_summary_path).read_text(encoding="utf-8"))
    assert summary_json["total_packs"] >= 1

    # Vérifier l'existence du dossier de pack standardisé
    first_pack_dir = Path(results[0].output_dir) / "social_pack" / "Segment 01"
    assert first_pack_dir.is_dir()
    assert (first_pack_dir / "video.mp4").is_file()
    assert (first_pack_dir / "thumbnail.jpg").is_file()
    assert (first_pack_dir / "pack_metadata.json").is_file()

