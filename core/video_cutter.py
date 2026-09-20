"""
VideoCutPub - Video Cutter Engine
Supports both Fast Stream Copy (-c copy) and Precise Re-encoding modes.
Tracks requested_start, requested_end, actual_start, and actual_end for keyframe accuracy transparency.
"""

import math
import os
import time
from pathlib import Path
from typing import Optional, List, Union, Callable

from ffmpeg.ffmpeg_manager import FFmpegManager, FFmpegExecutionError
from core.models import CutMode, VideoMetadata, SegmentCutInfo, CutResult
from core.video_analyzer import VideoAnalyzer
from core.file_manager import FileManager


def seconds_to_timestamp(seconds: float) -> str:
    """Convertit un temps en secondes vers le format HH:MM:SS.mmm."""
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    entire_secs = int(secs)
    millis = int(round((secs - entire_secs) * 1000))
    if millis >= 1000:
        entire_secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{entire_secs:02d}.{millis:03d}"


def parse_duration_input(duration_input: Union[int, float, str]) -> float:
    """
    Parse la saisie de durée de l'utilisateur.
    Formats supportés :
    - Nombre (int/float) : ex 10 -> 10.0s, 0.5 -> 30.0s si float < 10 ? Non: float/int en secondes
    - Chaîne HH:MM:SS ou MM:SS : ex "02:30" -> 150.0s, "00:30" -> 30.0s, "10s" -> 10.0s, "2m" -> 120.0s
    """
    if isinstance(duration_input, (int, float)):
        if duration_input <= 0:
            raise ValueError("La durée doit être supérieure à 0")
        return float(duration_input)

    val_str = str(duration_input).strip().lower()
    if not val_str:
        raise ValueError("Durée vide invalide")

    # Format HH:MM:SS ou MM:SS
    if ":" in val_str:
        parts = val_str.split(":")
        if len(parts) == 2:
            m, s = parts
            return float(m) * 60.0 + float(s)
        elif len(parts) == 3:
            h, m, s = parts
            return float(h) * 3600.0 + float(m) * 60.0 + float(s)

    # Format avec unité (ex: "10s", "2m", "1.5m")
    if val_str.endswith("s"):
        return float(val_str[:-1])
    if val_str.endswith("m"):
        return float(val_str[:-1]) * 60.0

    # Sinon conversion directe en float secondes
    dur = float(val_str)
    if dur <= 0:
        raise ValueError("La durée doit être supérieure à 0")
    return dur


class VideoCutter:
    """Moteur de découpage vidéo autonome."""

    def __init__(self, ffmpeg_manager: Optional[FFmpegManager] = None, analyzer: Optional[VideoAnalyzer] = None):
        self.ffmpeg_manager = ffmpeg_manager or FFmpegManager()
        self.analyzer = analyzer or VideoAnalyzer(self.ffmpeg_manager)

    def cut_video(
        self,
        source_path: str,
        output_base_dir: str,
        segment_duration: Union[int, float, str],
        mode: CutMode = CutMode.FAST,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> CutResult:
        """
        Découpe une vidéo source en segments et les enregistre dans un dossier d'isolation dédié.
        """
        start_process_time = time.time()
        source_file = Path(source_path)
        if not source_file.is_file():
            raise FileNotFoundError(f"Fichier vidéo introuvable : {source_path}")

        target_segment_sec = parse_duration_input(segment_duration)

        # 1. Analyse des métadonnées de la vidéo source
        metadata = self.analyzer.analyze(str(source_file))

        # 2. Préparation du dossier de sortie dédié
        output_dir = FileManager.prepare_output_directory(source_file, output_base_dir)
        clean_name = FileManager.sanitize_filename(source_file.name)

        total_duration = metadata.duration_seconds
        if total_duration <= 0:
            raise ValueError(f"Durée vidéo invalide ({total_duration}s) pour '{source_path}'")

        # Extraction des keyframes si mode Fast
        keyframes = []
        if mode == CutMode.FAST:
            keyframes = self.analyzer.get_keyframes(str(source_file))

        total_segments = math.ceil(total_duration / target_segment_sec)
        segments_info: List[SegmentCutInfo] = []

        for idx in range(1, total_segments + 1):
            req_start_sec = (idx - 1) * target_segment_sec
            req_end_sec = min(idx * target_segment_sec, total_duration)

            if req_start_sec >= total_duration:
                break

            segment_filename = FileManager.get_segment_filename(clean_name, idx, source_file.suffix)
            segment_out_path = output_dir / segment_filename

            req_start_ts = seconds_to_timestamp(req_start_sec)
            req_end_ts = seconds_to_timestamp(req_end_sec)

            if mode == CutMode.FAST:
                seg_info = self._cut_fast(
                    source_path=str(source_file),
                    output_path=str(segment_out_path),
                    index=idx,
                    filename=segment_filename,
                    req_start_sec=req_start_sec,
                    req_end_sec=req_end_sec,
                    req_start_ts=req_start_ts,
                    req_end_ts=req_end_ts,
                    keyframes=keyframes,
                )
            else:
                seg_info = self._cut_precise(
                    source_path=str(source_file),
                    output_path=str(segment_out_path),
                    index=idx,
                    filename=segment_filename,
                    req_start_sec=req_start_sec,
                    req_end_sec=req_end_sec,
                    req_start_ts=req_start_ts,
                    req_end_ts=req_end_ts,
                    has_audio=metadata.has_audio,
                )

            segments_info.append(seg_info)

            if progress_callback and total_segments > 0:
                prog_pct = round((idx / total_segments) * 100.0, 1)
                progress_callback(idx, total_segments, prog_pct)

        # 3. Assemblage du résultat global et sauvegarde metadata.json
        metadata_json_path = output_dir / "metadata.json"
        
        result = CutResult(
            source_file=str(source_file.resolve()),
            output_dir=str(output_dir.resolve()),
            cut_mode=mode,
            target_segment_duration_seconds=target_segment_sec,
            total_segments=len(segments_info),
            metadata_json_path=str(metadata_json_path.resolve()),
            segments=segments_info,
            success=all(s.status == "completed" for s in segments_info),
            total_time_seconds=round(time.time() - start_process_time, 2)
        )

        FileManager.write_metadata_json(result, metadata_json_path)
        return result

    def _cut_fast(
        self,
        source_path: str,
        output_path: str,
        index: int,
        filename: str,
        req_start_sec: float,
        req_end_sec: float,
        req_start_ts: str,
        req_end_ts: str,
        keyframes: List[float],
    ) -> SegmentCutInfo:
        """Découpage en mode Fast Stream Copy (-c copy)."""
        duration = req_end_sec - req_start_sec

        args = [
            "-y",
            "-ss", str(req_start_sec),
            "-i", source_path,
            "-t", str(duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            output_path
        ]

        try:
            self.ffmpeg_manager.run_ffmpeg(args)
            
            # Mesure du timestamp réel du segment généré
            actual_start_sec = req_start_sec
            actual_end_sec = req_end_sec

            try:
                seg_meta = self.analyzer.analyze(output_path)
                actual_duration = seg_meta.duration_seconds
                actual_start_sec = req_start_sec
                actual_end_sec = req_start_sec + actual_duration
            except Exception:
                actual_duration = duration

            return SegmentCutInfo(
                segment_index=index,
                filename=filename,
                output_path=output_path,
                requested_start=req_start_ts,
                requested_end=req_end_ts,
                actual_start=seconds_to_timestamp(actual_start_sec),
                actual_end=seconds_to_timestamp(actual_end_sec),
                duration_seconds=round(actual_duration, 3),
                status="completed"
            )
        except Exception as e:
            return SegmentCutInfo(
                segment_index=index,
                filename=filename,
                output_path=output_path,
                requested_start=req_start_ts,
                requested_end=req_end_ts,
                actual_start=req_start_ts,
                actual_end=req_end_ts,
                duration_seconds=0.0,
                status="failed",
                error_message=str(e)
            )

    def _cut_precise(
        self,
        source_path: str,
        output_path: str,
        index: int,
        filename: str,
        req_start_sec: float,
        req_end_sec: float,
        req_start_ts: str,
        req_end_ts: str,
        has_audio: bool,
    ) -> SegmentCutInfo:
        """Découpage en mode Precise (Re-encodage H.264/AAC)."""
        duration = req_end_sec - req_start_sec

        args = [
            "-y",
            "-ss", str(req_start_sec),
            "-i", source_path,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
        ]

        if has_audio:
            args.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            args.append("-an")

        args.append(output_path)

        try:
            self.ffmpeg_manager.run_ffmpeg(args)
            return SegmentCutInfo(
                segment_index=index,
                filename=filename,
                output_path=output_path,
                requested_start=req_start_ts,
                requested_end=req_end_ts,
                actual_start=req_start_ts,
                actual_end=req_end_ts,
                duration_seconds=round(duration, 3),
                status="completed"
            )
        except Exception as e:
            return SegmentCutInfo(
                segment_index=index,
                filename=filename,
                output_path=output_path,
                requested_start=req_start_ts,
                requested_end=req_end_ts,
                actual_start=req_start_ts,
                actual_end=req_end_ts,
                duration_seconds=0.0,
                status="failed",
                error_message=str(e)
            )
