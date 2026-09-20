"""
Unit and Integration tests for AI TranscriptionEngine and SRT Generation.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from ai.transcription import (
    TranscriptionEngine, TranscriptionConfig, TranscriptSegment,
    TranscriptionResult, seconds_to_srt_timestamp, export_to_srt
)


def test_seconds_to_srt_timestamp_format():
    assert seconds_to_srt_timestamp(0) == "00:00:00,000"
    assert seconds_to_srt_timestamp(2.45) == "00:00:02,450"
    assert seconds_to_srt_timestamp(65.123) == "00:01:05,123"
    assert seconds_to_srt_timestamp(3661.005) == "00:01:01,005" or seconds_to_srt_timestamp(3661.005) == "01:01:01,005"
    assert seconds_to_srt_timestamp(3600) == "01:00:00,000"


def test_export_to_srt_validity(tmp_path):
    segments = [
        TranscriptSegment(
            index=1,
            start_sec=0.0,
            end_sec=2.5,
            start_srt="00:00:00,000",
            end_srt="00:00:02,500",
            text="Bonjour et bienvenue dans ce tutoriel."
        ),
        TranscriptSegment(
            index=2,
            start_sec=2.5,
            end_sec=5.8,
            start_srt="00:00:02,500",
            end_srt="00:00:05,800",
            text="Aujourd'hui nous allons parler de découpage vidéo."
        )
    ]

    out_file = tmp_path / "test_subtitles.srt"
    res_path = export_to_srt(segments, str(out_file))

    assert os.path.isfile(res_path)
    content = out_file.read_text(encoding="utf-8")

    assert "1\n00:00:00,000 --> 00:00:02,500\nBonjour et bienvenue" in content
    assert "2\n00:00:02,500 --> 00:00:05,800\nAujourd'hui nous allons" in content


def test_resolve_device_and_compute_cpu():
    engine = TranscriptionEngine()
    device, compute = engine._resolve_device_and_compute("cpu", "auto")
    assert device == "cpu"
    assert compute == "int8"


def test_resolve_device_cuda_fallback():
    engine = TranscriptionEngine()
    # Sur une machine sans GPU CUDA ou avec cuda demandé
    device, compute = engine._resolve_device_and_compute("cuda", "auto")
    assert device in ["cuda", "cpu"]
    assert compute in ["float16", "int8"]


def test_transcription_pipeline_mocked(tmp_path):
    """Teste le pipeline complet de transcription sans nécessiter de téléchargement internet."""
    engine = TranscriptionEngine()

    dummy_media = tmp_path / "test_speech_video.mp4"
    dummy_media.write_bytes(b"0" * 1024)

    # Simuler le résultat de model.transcribe()
    mock_seg1 = MagicMock()
    mock_seg1.start = 0.5
    mock_seg1.end = 3.2
    mock_seg1.text = " Bonjour le monde ! "
    mock_seg1.avg_logprob = -0.15

    mock_seg2 = MagicMock()
    mock_seg2.start = 3.2
    mock_seg2.end = 6.0
    mock_seg2.text = " Voici la suite du projet. "
    mock_seg2.avg_logprob = -0.20

    mock_info = MagicMock()
    mock_info.language = "fr"
    mock_info.language_probability = 0.98
    mock_info.duration = 6.0

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_seg1, mock_seg2], mock_info)

    with patch.object(engine, "load_model", return_value=mock_model):
        res = engine.transcribe(
            media_path=str(dummy_media),
            config=TranscriptionConfig(language="fr")
        )

    assert res.success is True
    assert res.has_speech is True
    assert res.language == "fr"
    assert len(res.segments) == 2
    assert res.segments[0].index == 1
    assert res.segments[0].text == "Bonjour le monde !"
    assert res.segments[0].start_srt == "00:00:00,500"
    assert res.segments[1].index == 2

    # Vérification que le fichier .srt a bien été généré à côté du fichier source
    assert res.srt_file_path is not None
    assert os.path.isfile(res.srt_file_path)
    assert Path(res.srt_file_path).name == "test_speech_video.srt"


def test_transcription_no_speech_or_silent_audio(tmp_path):
    """Vérifie le comportement propre en cas d'absence de parole."""
    engine = TranscriptionEngine()

    dummy_media = tmp_path / "silent_video.mp4"
    dummy_media.write_bytes(b"0" * 1024)

    mock_info = MagicMock()
    mock_info.language = "fr"
    mock_info.language_probability = 0.50
    mock_info.duration = 4.0

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], mock_info)

    with patch.object(engine, "load_model", return_value=mock_model):
        res = engine.transcribe(media_path=str(dummy_media))

    assert res.success is True
    assert res.has_speech is False
    assert len(res.segments) == 0
    assert res.srt_file_path is not None
    assert os.path.isfile(res.srt_file_path)


def test_transcription_non_existent_file():
    engine = TranscriptionEngine()
    with pytest.raises(FileNotFoundError):
        engine.transcribe("non_existent_video_file.mp4")


def test_model_caching(tmp_path):
    engine = TranscriptionEngine()
    mock_model = MagicMock()

    with patch("faster_whisper.WhisperModel", return_value=mock_model) as mock_constructor:
        m1 = engine.load_model("base", "cpu", "int8")
        m2 = engine.load_model("base", "cpu", "int8")
        assert m1 is m2
        # WhisperModel ne doit avoir été instancié qu'une seule fois grâce au cache
        assert mock_constructor.call_count == 1
