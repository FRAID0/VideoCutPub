"""
VideoCutPub - Social Pack Exporter Engine (Étape 9)
Assembles and standardizes complete, self-contained publishing packs for each segment:
video.mp4, video_subtitled.mp4, subtitles.srt, subtitles.ass, thumbnail.jpg,
post_content.txt, and pack_metadata.json.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field

from ffmpeg.ffmpeg_manager import FFmpegManager, FFmpegExecutionError
from core.video_analyzer import VideoAnalyzer
from ai.metadata_generator import SocialMetadata, MetadataGenerator


class SegmentPack(BaseModel):
    """Contenu d'un pack de publication autonome pour un segment vidéo."""
    segment_index: int = Field(..., description="Numéro d'ordre du segment (1-based)")
    pack_dir: str = Field(..., description="Dossier absolu du pack (ex: social_pack/Segment 01/)")
    video_file: Optional[str] = Field(None, description="Vidéo principale (9:16 ou originale)")
    subtitled_video_file: Optional[str] = Field(None, description="Vidéo avec sous-titres incrustés")
    srt_file: Optional[str] = Field(None, description="Fichier sous-titres brut (.srt)")
    ass_file: Optional[str] = Field(None, description="Fichier sous-titres stylisé (.ass)")
    thumbnail_file: Optional[str] = Field(None, description="Miniature JPEG HD (.jpg)")
    post_content_file: Optional[str] = Field(None, description="Fiche texte prête à publier (post_content.txt)")
    metadata_json_file: Optional[str] = Field(None, description="Fiche technique JSON (pack_metadata.json)")
    has_subtitles: bool = False
    duration_seconds: float = 0.0
    width: int = 0
    height: int = 0
    success: bool = True
    error_message: Optional[str] = None


class PackSummary(BaseModel):
    """Synthèse globale des packs créés pour une vidéo traitée."""
    source_file: str
    output_dir: str
    total_packs: int = 0
    packs: List[SegmentPack] = []
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    summary_json_path: Optional[str] = None


class SocialPackager:
    """
    Gestionnaire d'assemblage et de packaging autonome des extraits vidéo pour les réseaux sociaux.
    """

    def __init__(
        self,
        ffmpeg_manager: Optional[FFmpegManager] = None,
        analyzer: Optional[VideoAnalyzer] = None
    ):
        self.ffmpeg_manager = ffmpeg_manager or FFmpegManager()
        self.analyzer = analyzer or VideoAnalyzer(self.ffmpeg_manager)
        self.metadata_generator = MetadataGenerator()

    def extract_thumbnail(
        self,
        video_path: str,
        output_path: str,
        timestamp_sec: Optional[float] = None
    ) -> str:
        """
        Extrait une miniature JPEG haute définition à un timestamp donné.
        Si aucun timestamp n'est spécifié, capture automatiquement l'image à 25% de la durée.
        """
        v_path = Path(video_path)
        if not v_path.is_file():
            raise FileNotFoundError(f"Fichier vidéo introuvable : {video_path}")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # Calcul automatique du timestamp à 25% si non renseigné
        if timestamp_sec is None or timestamp_sec <= 0.0:
            try:
                meta = self.analyzer.analyze(str(v_path))
                timestamp_sec = max(0.5, meta.duration_seconds * 0.25)
            except Exception:
                timestamp_sec = 1.0

        ts_str = f"{timestamp_sec:.2f}"
        cmd = [
            "-y",
            "-ss", ts_str,
            "-i", str(v_path.resolve()),
            "-vframes", "1",
            "-q:v", "2",
            str(out.resolve())
        ]

        self.ffmpeg_manager.run_ffmpeg(cmd)
        return str(out.resolve())

    def create_segment_pack(
        self,
        segment_index: int,
        output_base_dir: str,
        video_path: str,
        subtitled_video_path: Optional[str] = None,
        srt_path: Optional[str] = None,
        ass_path: Optional[str] = None,
        metadata: Optional[SocialMetadata] = None,
        copy_files: bool = True,
        source_video: Optional[str] = None
    ) -> SegmentPack:
        """
        Crée le dossier autonome 'Segment XX/' et y standardise tous les livrables.
        Génère un manifeste unique pack_metadata.json servant de source de vérité.
        """
        seg_folder_name = f"Segment {segment_index:02d}"
        pack_dir = Path(output_base_dir) / "social_pack" / seg_folder_name
        pack_dir.mkdir(parents=True, exist_ok=True)

        pack = SegmentPack(
            segment_index=segment_index,
            pack_dir=str(pack_dir.resolve()),
            success=True
        )

        try:
            # 1. Vidéo principale (video.mp4)
            v_src = Path(video_path)
            if v_src.is_file():
                v_dest = pack_dir / "video.mp4"
                if copy_files and v_src.resolve() != v_dest.resolve():
                    shutil.copy2(v_src, v_dest)
                pack.video_file = str(v_dest.resolve())

                # Analyse des caractéristiques
                v_meta = self.analyzer.analyze(str(v_dest))
                pack.duration_seconds = v_meta.duration_seconds
                pack.width = v_meta.width
                pack.height = v_meta.height

            # 2. Vidéo sous-titrée (video_subtitled.mp4)
            if subtitled_video_path and Path(subtitled_video_path).is_file():
                sub_src = Path(subtitled_video_path)
                sub_dest = pack_dir / "video_subtitled.mp4"
                if copy_files and sub_src.resolve() != sub_dest.resolve():
                    shutil.copy2(sub_src, sub_dest)
                pack.subtitled_video_file = str(sub_dest.resolve())
                pack.has_subtitles = True

            # 3. Fichier sous-titres brut (.srt)
            if srt_path and Path(srt_path).is_file():
                srt_src = Path(srt_path)
                srt_dest = pack_dir / "subtitles.srt"
                if copy_files and srt_src.resolve() != srt_dest.resolve():
                    shutil.copy2(srt_src, srt_dest)
                pack.srt_file = str(srt_dest.resolve())

            # 4. Fichier sous-titres stylisé (.ass)
            if ass_path and Path(ass_path).is_file():
                ass_src = Path(ass_path)
                ass_dest = pack_dir / "subtitles.ass"
                if copy_files and ass_src.resolve() != ass_dest.resolve():
                    shutil.copy2(ass_src, ass_dest)
                pack.ass_file = str(ass_dest.resolve())

            # 5. Miniature HD (thumbnail.jpg)
            target_thumb_vid = pack.subtitled_video_file or pack.video_file
            if target_thumb_vid and Path(target_thumb_vid).is_file():
                thumb_dest = pack_dir / "thumbnail.jpg"
                try:
                    self.extract_thumbnail(target_thumb_vid, str(thumb_dest))
                    pack.thumbnail_file = str(thumb_dest.resolve())
                except Exception:
                    pass

            # 6. Fiche texte (post_content.txt)
            if metadata:
                txt_dest = pack_dir / "post_content.txt"
                self.metadata_generator.export_post_txt(metadata, str(txt_dest))
                pack.post_content_file = str(txt_dest.resolve())

            # 7. Fiche technique et manifeste unique du pack (pack_metadata.json)
            formats_dict = {
                "original": str(Path(video_path).resolve()) if video_path else None,
                "vertical_9x16": "video.mp4" if (pack.width > 0 and pack.height / pack.width > 1.3) else None,
                "square_1x1": "video.mp4" if (pack.width > 0 and pack.height == pack.width) else None,
                "standard": "video.mp4"
            }

            pack_meta_dict = {
                "source_video": source_video or video_path,
                "segment": segment_index,
                "segment_index": segment_index,
                "created_at": datetime.now().isoformat(),
                "duration_seconds": pack.duration_seconds,
                "width": pack.width,
                "height": pack.height,
                "has_subtitles": pack.has_subtitles,
                "formats": formats_dict,
                "subtitles": {
                    "srt": "subtitles.srt" if pack.srt_file else None,
                    "ass": "subtitles.ass" if pack.ass_file else None,
                    "burned_in": "video_subtitled.mp4" if pack.subtitled_video_file else None,
                },
                "metadata": {
                    "title": metadata.title if metadata else f"Segment {segment_index}",
                    "hooks": metadata.hooks if metadata else [],
                    "description": metadata.description if metadata else "",
                    "hashtags": metadata.hashtags if metadata else [],
                    "detected_topic": metadata.detected_topic if metadata else "Général",
                    "keywords": metadata.keywords if metadata else []
                } if metadata else None,
                "thumbnail": "thumbnail.jpg" if pack.thumbnail_file else None,
                "publishing": {
                    "youtube": "ready",
                    "tiktok": "ready",
                    "manual": "ready"
                },
                "files": {
                    "video": "video.mp4" if pack.video_file else None,
                    "video_subtitled": "video_subtitled.mp4" if pack.subtitled_video_file else None,
                    "subtitles_srt": "subtitles.srt" if pack.srt_file else None,
                    "subtitles_ass": "subtitles.ass" if pack.ass_file else None,
                    "thumbnail": "thumbnail.jpg" if pack.thumbnail_file else None,
                    "post_content": "post_content.txt" if pack.post_content_file else None,
                }
            }

            meta_dest = pack_dir / "pack_metadata.json"
            meta_dest.write_text(json.dumps(pack_meta_dict, indent=2, ensure_ascii=False), encoding="utf-8")
            pack.metadata_json_file = str(meta_dest.resolve())

            return pack

        except Exception as e:
            pack.success = False
            pack.error_message = str(e)
            return pack

    def package_job_assets(
        self,
        source_file: str,
        output_dir: str,
        segments_data: List[Dict[str, Any]]
    ) -> PackSummary:
        """
        Assemble l'ensemble des packs pour tous les segments d'un traitement et produit pack_summary.json.
        """
        out_base = Path(output_dir)
        summary = PackSummary(
            source_file=source_file,
            output_dir=str(out_base.resolve()),
            total_packs=0,
            packs=[]
        )

        for seg_info in segments_data:
            idx = seg_info.get("segment_index", 1)
            video_p = seg_info.get("video_path")
            sub_p = seg_info.get("subtitled_video_path")
            srt_p = seg_info.get("srt_path")
            ass_p = seg_info.get("ass_path")
            ai_meta = seg_info.get("metadata")

            if video_p and Path(video_p).is_file():
                pack = self.create_segment_pack(
                    segment_index=idx,
                    output_base_dir=str(out_base),
                    video_path=video_p,
                    subtitled_video_path=sub_p,
                    srt_path=srt_p,
                    ass_path=ass_p,
                    metadata=ai_meta,
                    source_video=source_file
                )
                summary.packs.append(pack)

        summary.total_packs = len(summary.packs)

        # Création de pack_summary.json à la racine du dossier social_pack/
        summary_file = out_base / "social_pack" / "pack_summary.json"
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        summary.summary_json_path = str(summary_file.resolve())

        return summary
