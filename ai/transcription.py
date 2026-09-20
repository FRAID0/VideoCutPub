"""
VideoCutPub - AI Transcription Engine (Faster-Whisper)
Handles high-performance local speech-to-text, timestamped segment generation,
graceful CPU/GPU fallback, and standard SRT export.
"""

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Callable, Dict, Any
from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    """Segment de transcription temporel structuré."""
    index: int = Field(..., description="Numéro d'ordre (1-based)")
    start_sec: float = Field(..., description="Début en secondes")
    end_sec: float = Field(..., description="Fin en secondes")
    start_srt: str = Field(..., description="Horodatage SRT début (HH:MM:SS,mmm)")
    end_srt: str = Field(..., description="Horodatage SRT fin (HH:MM:SS,mmm)")
    text: str = Field(..., description="Texte transcrit")
    confidence: float = Field(0.0, description="Score de confiance moyen (0-1)")
    words: Optional[List[Dict[str, Any]]] = None


class TranscriptionResult(BaseModel):
    """Résultat complet d'une transcription audio/vidéo."""
    source_file: str
    srt_file_path: Optional[str] = None
    language: str = "unknown"
    language_probability: float = 0.0
    duration_seconds: float = 0.0
    segments: List[TranscriptSegment] = []
    has_speech: bool = False
    success: bool = True
    error_message: Optional[str] = None


class TranscriptionConfig(BaseModel):
    """Configuration du moteur de transcription Faster-Whisper."""
    model_name: str = Field("base", description="Taille du modèle (tiny, base, small, medium, large-v3)")
    device: str = Field("auto", description="Périphérique d'exécution (auto, cpu, cuda)")
    compute_type: str = Field("auto", description="Type de calcul (auto, int8, float16, float32)")
    language: Optional[str] = Field(None, description="Code langue ISO (ex: 'fr', 'en') ou None pour détection automatique")
    beam_size: int = Field(5, description="Faisceau de recherche du décodeur")
    vad_filter: bool = Field(True, description="Active le filtre VAD pour ignorer les silences purs")


def seconds_to_srt_timestamp(seconds: float) -> str:
    """Convertit des secondes vers le format officiel SRT : HH:MM:SS,mmm."""
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    entire_secs = int(secs)
    millis = int(round((secs - entire_secs) * 1000))
    if millis >= 1000:
        entire_secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{entire_secs:02d},{millis:03d}"


def export_to_srt(segments: List[TranscriptSegment], output_path: str) -> str:
    """Écrit la liste des segments dans un fichier sous-titres .srt standard."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"{seg.index}\n")
            f.write(f"{seg.start_srt} --> {seg.end_srt}\n")
            f.write(f"{seg.text.strip()}\n\n")
    return str(out.resolve())


class TranscriptionEngine:
    """Moteur de transcription locale utilisant Faster-Whisper."""

    def __init__(self, default_config: Optional[TranscriptionConfig] = None):
        self.config = default_config or TranscriptionConfig()
        self._cached_model = None
        self._cached_model_key = None

    def _resolve_device_and_compute(self, requested_device: str, requested_compute: str) -> Tuple[str, str]:
        """Détermine le périphérique réel (CUDA ou CPU) avec repli sécurisé sur CPU."""
        device = requested_device.lower()
        compute = requested_compute.lower()

        # 1. Résolution du périphérique
        if device in ["cuda", "auto"]:
            try:
                import ctranslate2
                cuda_count = ctranslate2.get_cuda_device_count()
                if cuda_count > 0:
                    device = "cuda"
                else:
                    device = "cpu"
            except Exception:
                device = "cpu"
        else:
            device = "cpu"

        # 2. Résolution du compute_type
        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"

        return device, compute

    def load_model(self, model_name: str = "base", device: str = "auto", compute_type: str = "auto"):
        """Charge ou réutilise le modèle Faster-Whisper en cache."""
        actual_device, actual_compute = self._resolve_device_and_compute(device, compute_type)
        model_key = (model_name, actual_device, actual_compute)

        if self._cached_model is not None and self._cached_model_key == model_key:
            return self._cached_model

        from faster_whisper import WhisperModel

        try:
            model = WhisperModel(
                model_name,
                device=actual_device,
                compute_type=actual_compute,
            )
        except Exception as e:
            # Fallback direct vers CPU/int8 en cas d'erreur de bibliothèque CUDA/cuDNN
            if actual_device == "cuda":
                actual_device = "cpu"
                actual_compute = "int8"
                model = WhisperModel(
                    model_name,
                    device=actual_device,
                    compute_type=actual_compute,
                )
            else:
                raise e

        self._cached_model = model
        self._cached_model_key = (model_name, actual_device, actual_compute)
        return model

    def transcribe(
        self,
        media_path: str,
        output_dir: Optional[str] = None,
        config: Optional[TranscriptionConfig] = None,
        progress_callback: Optional[Callable[[int, float], None]] = None,
    ) -> TranscriptionResult:
        """
        Transcrit un fichier média (vidéo ou audio) et génère un fichier .srt associé.
        Si la vidéo n'a pas de voix ou pas de piste audio, renvoie un résultat propre sans planter.
        """
        path = Path(media_path)
        if not path.is_file():
            raise FileNotFoundError(f"Fichier média introuvable : {media_path}")

        cfg = config or self.config

        try:
            model = self.load_model(
                model_name=cfg.model_name,
                device=cfg.device,
                compute_type=cfg.compute_type
            )

            # Exécution de la transcription Faster-Whisper
            segments_iter, info = model.transcribe(
                str(path),
                language=cfg.language,
                beam_size=cfg.beam_size,
                vad_filter=cfg.vad_filter,
            )

            structured_segments: List[TranscriptSegment] = []
            for idx, seg in enumerate(segments_iter, start=1):
                clean_text = seg.text.strip()
                if clean_text:
                    st_srt = seconds_to_srt_timestamp(seg.start)
                    end_srt = seconds_to_srt_timestamp(seg.end)
                    structured_segments.append(TranscriptSegment(
                        index=idx,
                        start_sec=round(seg.start, 3),
                        end_sec=round(seg.end, 3),
                        start_srt=st_srt,
                        end_srt=end_srt,
                        text=clean_text,
                        confidence=round(getattr(seg, "avg_logprob", 0.0), 3)
                    ))
                    if progress_callback:
                        progress_callback(idx, seg.end)

            # Définition du fichier .srt de sortie
            target_folder = Path(output_dir) if output_dir else path.parent
            srt_filename = f"{path.stem}.srt"
            srt_path = target_folder / srt_filename

            if structured_segments:
                export_to_srt(structured_segments, str(srt_path))
                srt_path_str = str(srt_path.resolve())
            else:
                # Créer un fichier SRT vide si pas de parole
                export_to_srt([], str(srt_path))
                srt_path_str = str(srt_path.resolve())

            return TranscriptionResult(
                source_file=str(path.resolve()),
                srt_file_path=srt_path_str,
                language=info.language if hasattr(info, "language") else (cfg.language or "unknown"),
                language_probability=round(info.language_probability, 3) if hasattr(info, "language_probability") else 1.0,
                duration_seconds=round(info.duration, 2) if hasattr(info, "duration") else 0.0,
                segments=structured_segments,
                has_speech=len(structured_segments) > 0,
                success=True
            )

        except Exception as e:
            return TranscriptionResult(
                source_file=str(path.resolve()),
                srt_file_path=None,
                segments=[],
                has_speech=False,
                success=False,
                error_message=str(e)
            )
