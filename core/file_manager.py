"""
VideoCutPub - File & Directory Isolation Manager
Manages clean output folder creation, filename sanitization, and metadata JSON serialization.
"""

import json
import re
from pathlib import Path
from typing import Union
from core.models import CutResult


class FileManager:
    """Gestionnaire d'organisation des dossiers et de nettoyage des noms."""

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Nettoie un nom de fichier/dossier en retirant les caractères interdits sous Windows.
        ('? : / \\ * " < > |')
        """
        # Supprime l'extension si présente
        stem = Path(filename).stem
        # Remplacer les caractères interdits par un tiret
        clean_stem = re.sub(r'[\\/:*?"<>|]', '-', stem)
        # Nettoyer les espaces multiples ou superflus
        clean_stem = re.sub(r'\s+', ' ', clean_stem).strip()
        return clean_stem or "video_segment"

    @staticmethod
    def prepare_output_directory(source_path: Union[str, Path], base_output_dir: Union[str, Path]) -> Path:
        """
        Crée le dossier dédié d'isolation pour la vidéo traitée sous le répertoire de sortie de base.
        Ex: base_output_dir / "Nom_Vidéo_Propre"
        """
        clean_name = FileManager.sanitize_filename(str(source_path))
        target_dir = Path(base_output_dir) / clean_name
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    @staticmethod
    def get_segment_filename(clean_base_name: str, index: int, extension: str = ".mp4") -> str:
        """Formate le nom du segment avec numérotation propre (ex: "Video 01.mp4")."""
        ext = extension if extension.startswith(".") else f".{extension}"
        return f"{clean_base_name} {index:02d}{ext}"

    @staticmethod
    def write_metadata_json(cut_result: CutResult, output_file_path: Union[str, Path]) -> str:
        """Sauvegarde les métadonnées de traitement au format JSON."""
        target_path = Path(output_file_path)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(cut_result.model_dump(), f, indent=2, ensure_ascii=False)
        return str(target_path.resolve())
