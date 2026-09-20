"""
Unit and Integration tests for VideoTransformer and Social Aspect Ratio Engine.
"""

import os
import pytest
from pathlib import Path

from ffmpeg.ffmpeg_manager import FFmpegManager
from core.video_analyzer import VideoAnalyzer
from core.video_transformer import VideoTransformer, TransformResult
from social.aspect_ratio import SocialAspectRatio, TransformMode, TransformConfig


@pytest.fixture(scope="module")
def ffmpeg_mgr():
    mgr = FFmpegManager()
    if not mgr.is_available():
        pytest.skip("FFmpeg/FFprobe non disponible")
    return mgr


@pytest.fixture(scope="module")
def sample_horizontal_video_with_audio(tmp_path_factory, ffmpeg_mgr):
    """Génère une vidéo 16:9 (640x360) de 4 secondes avec audio."""
    temp_dir = tmp_path_factory.mktemp("transform_media")
    video_path = temp_dir / "sample_16_9_audio.mp4"
    args = [
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=4:size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=4",
        "-c:v", "libx264", "-c:a", "aac",
        str(video_path)
    ]
    ffmpeg_mgr.run_ffmpeg(args)
    return str(video_path)


@pytest.fixture(scope="module")
def sample_horizontal_video_no_audio(tmp_path_factory, ffmpeg_mgr):
    """Génère une vidéo 16:9 (640x360) de 3 secondes sans audio."""
    temp_dir = tmp_path_factory.mktemp("transform_media_no_audio")
    video_path = temp_dir / "sample_16_9_no_audio.mp4"
    args = [
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=640x360:rate=30",
        "-an", "-c:v", "libx264",
        str(video_path)
    ]
    ffmpeg_mgr.run_ffmpeg(args)
    return str(video_path)


@pytest.fixture(scope="module")
def sample_vertical_video(tmp_path_factory, ffmpeg_mgr):
    """Génère une vidéo déjà en 9:16 (360x640) de 3 secondes."""
    temp_dir = tmp_path_factory.mktemp("transform_vertical")
    video_path = temp_dir / "sample_already_vertical.mp4"
    args = [
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=360x640:rate=30",
        "-an", "-c:v", "libx264",
        str(video_path)
    ]
    ffmpeg_mgr.run_ffmpeg(args)
    return str(video_path)


@pytest.fixture(scope="module")
def sample_video_accented_name(tmp_path_factory, ffmpeg_mgr):
    """Génère une vidéo avec espaces et accents."""
    temp_dir = tmp_path_factory.mktemp("transform_accented")
    video_path = temp_dir / "Épisode 01 - Découverte & Voyage (été 2026).mp4"
    args = [
        "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=640x360:rate=30",
        "-an", "-c:v", "libx264",
        str(video_path)
    ]
    ffmpeg_mgr.run_ffmpeg(args)
    return str(video_path)


def test_transform_16_9_to_9_16_center_crop(tmp_path, ffmpeg_mgr, sample_horizontal_video_with_audio):
    transformer = VideoTransformer(ffmpeg_mgr)
    out_dir = tmp_path / "output_crop"

    cfg = TransformConfig(
        aspect_ratio=SocialAspectRatio.RATIO_9_16,
        mode=TransformMode.CENTER_CROP,
        target_width=360,
        target_height=640
    )

    original_size = os.path.getsize(sample_horizontal_video_with_audio)

    res = transformer.transform(sample_horizontal_video_with_audio, str(out_dir), config=cfg)

    assert res.success is True
    assert res.width == 360
    assert res.height == 640
    assert "social" in res.output_path
    assert "9x16" in res.output_path
    assert os.path.isfile(res.output_path)

    # Vérification stricte : l'original n'a pas été altéré
    assert os.path.getsize(sample_horizontal_video_with_audio) == original_size


def test_transform_16_9_to_9_16_blurred_background(tmp_path, ffmpeg_mgr, sample_horizontal_video_with_audio):
    transformer = VideoTransformer(ffmpeg_mgr)
    out_dir = tmp_path / "output_blur"

    cfg = TransformConfig(
        aspect_ratio=SocialAspectRatio.RATIO_9_16,
        mode=TransformMode.BLURRED_BACKGROUND,
        target_width=360,
        target_height=640
    )

    res = transformer.transform(sample_horizontal_video_with_audio, str(out_dir), config=cfg)

    assert res.success is True
    assert res.width == 360
    assert res.height == 640
    assert Path(res.output_path).is_file()

    # Vérification présence audio
    analyzer = VideoAnalyzer(ffmpeg_mgr)
    meta = analyzer.analyze(res.output_path)
    assert meta.has_audio is True


def test_transform_16_9_to_1_1_square(tmp_path, ffmpeg_mgr, sample_horizontal_video_with_audio):
    transformer = VideoTransformer(ffmpeg_mgr)
    out_dir = tmp_path / "output_square"

    cfg = TransformConfig(
        aspect_ratio=SocialAspectRatio.RATIO_1_1,
        mode=TransformMode.CENTER_CROP,
        target_width=360,
        target_height=360
    )

    res = transformer.transform(sample_horizontal_video_with_audio, str(out_dir), config=cfg)

    assert res.success is True
    assert res.width == 360
    assert res.height == 360
    assert "1x1" in res.output_path


def test_transform_16_9_to_16_9_passthrough(tmp_path, ffmpeg_mgr, sample_horizontal_video_with_audio):
    transformer = VideoTransformer(ffmpeg_mgr)
    out_dir = tmp_path / "output_16_9"

    cfg = TransformConfig(
        aspect_ratio=SocialAspectRatio.RATIO_16_9,
        mode=TransformMode.CENTER_CROP,
        target_width=640,
        target_height=360
    )

    res = transformer.transform(sample_horizontal_video_with_audio, str(out_dir), config=cfg)

    assert res.success is True
    assert res.width == 640
    assert res.height == 360
    assert "16x9" in res.output_path


def test_transform_video_no_audio(tmp_path, ffmpeg_mgr, sample_horizontal_video_no_audio):
    transformer = VideoTransformer(ffmpeg_mgr)
    out_dir = tmp_path / "output_no_audio"

    cfg = TransformConfig(
        aspect_ratio=SocialAspectRatio.RATIO_9_16,
        mode=TransformMode.BLURRED_BACKGROUND,
        target_width=360,
        target_height=640
    )

    res = transformer.transform(sample_horizontal_video_no_audio, str(out_dir), config=cfg)

    assert res.success is True
    analyzer = VideoAnalyzer(ffmpeg_mgr)
    meta = analyzer.analyze(res.output_path)
    assert meta.has_audio is False


def test_transform_already_vertical_video(tmp_path, ffmpeg_mgr, sample_vertical_video):
    transformer = VideoTransformer(ffmpeg_mgr)
    out_dir = tmp_path / "output_vertical_input"

    cfg = TransformConfig(
        aspect_ratio=SocialAspectRatio.RATIO_9_16,
        mode=TransformMode.BLURRED_BACKGROUND,
        target_width=360,
        target_height=640
    )

    res = transformer.transform(sample_vertical_video, str(out_dir), config=cfg)

    assert res.success is True
    assert res.width == 360
    assert res.height == 640


def test_transform_accented_filename(tmp_path, ffmpeg_mgr, sample_video_accented_name):
    transformer = VideoTransformer(ffmpeg_mgr)
    out_dir = tmp_path / "output_accented"

    cfg = TransformConfig(
        aspect_ratio=SocialAspectRatio.RATIO_9_16,
        mode=TransformMode.CENTER_CROP,
        target_width=360,
        target_height=640
    )

    res = transformer.transform(sample_video_accented_name, str(out_dir), config=cfg)

    assert res.success is True
    assert Path(res.output_path).is_file()


def test_transform_non_existent_file(tmp_path, ffmpeg_mgr):
    transformer = VideoTransformer(ffmpeg_mgr)
    with pytest.raises(FileNotFoundError):
        transformer.transform("invalid_video_file.mp4", str(tmp_path))
