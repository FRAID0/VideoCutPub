"""
VideoCutPub - Video URL Downloader Engine (yt-dlp)
Universal video downloader supporting YouTube, TikTok, Twitch, Vimeo,
and 1000+ streaming sites with pre-inspection, progress reporting, and queue integration.
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple

import yt_dlp
from yt_dlp.utils import DownloadCancelled, ExtractorError, UnsupportedError

from core.download_models import (
    DownloadQuality,
    VideoFormatOption,
    VideoInfo,
    DownloadProgress,
    DownloadResult,
)
from ffmpeg.ffmpeg_manager import FFmpegManager


def sanitize_filename(name: str) -> str:
    """
    Nettoie un nom de fichier pour le rendre 100% conforme aux règles Windows.
    Supprime les caractères interdits : < > : \" / \\ | ? * et limite la longueur.
    """
    # Remplacement des caractères interdits par un tiret bas ou un espace
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Suppression des espaces multiples et caractères de contrôle
    cleaned = re.sub(r'[\x00-\x1f\x7f]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip('. ')
    if not cleaned:
        cleaned = f"video_{int(time.time())}"
    # Tronquer pour éviter les dépassements de chemin Windows (MAX_PATH)
    return cleaned[:120]


def format_bytes(num_bytes: Optional[int]) -> str:
    """Convertit des octets en format lisible (ex: 24.5 Mo)."""
    if num_bytes is None or num_bytes <= 0:
        return "Taille inconnue"
    for unit in ['o', 'Ko', 'Mo', 'Go']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} To"


def format_speed(speed_bytes: Optional[float]) -> str:
    """Convertit une vitesse en octets/s en format lisible (ex: 3.2 Mo/s)."""
    if speed_bytes is None or speed_bytes <= 0:
        return "0 Mo/s"
    return f"{speed_bytes / (1024 * 1024):.1f} Mo/s"


class VideoDownloader:
    """
    Moteur de téléchargement vidéo multi-plateformes s'appuyant sur yt-dlp et FFmpeg.
    """

    def __init__(
        self,
        ffmpeg_manager: Optional[FFmpegManager] = None,
        default_download_dir: Optional[str] = None,
    ):
        self.ffmpeg_manager = ffmpeg_manager or FFmpegManager()
        self.download_dir = Path(default_download_dir) if default_download_dir else (Path.cwd() / "downloads")
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _get_ffmpeg_location(self) -> Optional[str]:
        """Retourne le répertoire de l'exécutable FFmpeg pour yt-dlp."""
        try:
            if self.ffmpeg_manager.is_available():
                return str(Path(self.ffmpeg_manager.ffmpeg_path).parent)
        except Exception:
            pass
        return None

    def check_url_supported(self, url: str) -> Tuple[bool, str]:
        """
        Vérifie si l'URL est techniquement prise en charge par un extracteur yt-dlp.
        Renvoie (is_supported, extractor_name).
        """
        if not url or not url.strip():
            return False, "URL vide"

        clean_url = url.strip()
        try:
            extractors = yt_dlp.extractor.gen_extractors()
            for ext in extractors:
                if ext.suitable(clean_url) and ext.IE_NAME != 'generic':
                    return True, ext.IE_NAME
            return True, "generic"
        except Exception as e:
            return False, str(e)

    def extract_info(self, url: str) -> VideoInfo:
        """
        Extrait les métadonnées de la vidéo (titre, durée, miniature, résolutions)
        SANS télécharger le fichier média.
        """
        clean_url = url.strip()
        ydl_opts: Dict[str, Any] = {
            'skip_download': True,
            'extract_flat': False,
            'quiet': True,
            'no_warnings': True,
        }

        ffmpeg_loc = self._get_ffmpeg_location()
        if ffmpeg_loc:
            ydl_opts['ffmpeg_location'] = ffmpeg_loc

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(clean_url, download=False)
                if not info_dict:
                    raise ValueError("Impossible d'extraire les informations de l'URL fournie.")

                # Traitement des playlists : prendre la première entrée
                if 'entries' in info_dict and info_dict['entries']:
                    info_dict = next(iter(info_dict['entries']))

                title = info_dict.get('title') or "Vidéo sans titre"
                extractor = info_dict.get('extractor_key') or info_dict.get('extractor') or "Inconnu"
                duration = float(info_dict.get('duration') or 0.0)
                uploader = info_dict.get('uploader') or info_dict.get('channel')
                thumbnail = info_dict.get('thumbnail')
                description = info_dict.get('description')
                is_live = bool(info_dict.get('is_live'))
                view_count = info_dict.get('view_count')

                # Détection des résolutions vidéo disponibles
                resolutions = set()
                formats = info_dict.get('formats') or []
                for f in formats:
                    h = f.get('height')
                    if h and isinstance(h, int) and h > 0:
                        resolutions.add(f"{h}p")

                sorted_res = sorted(
                    resolutions,
                    key=lambda x: int(x.replace('p', '')) if x.replace('p', '').isdigit() else 0,
                    reverse=True
                )

                return VideoInfo(
                    url=clean_url,
                    extractor=extractor,
                    title=title,
                    uploader=uploader,
                    duration_seconds=duration,
                    thumbnail_url=thumbnail,
                    description=description[:300] if description else None,
                    available_resolutions=sorted_res,
                    is_live=is_live,
                    has_drm=False,
                    view_count=view_count
                )

        except Exception as e:
            err_msg = str(e)
            if "DRM" in err_msg or "protected" in err_msg.lower():
                raise PermissionError("Cette vidéo utilise un verrou numérique (DRM) non pris en charge.")
            elif "Sign in" in err_msg or "Private video" in err_msg:
                raise PermissionError("Cette vidéo est privée ou requiert une authentification.")
            raise RuntimeError(f"Erreur d'analyse du lien : {err_msg}")

    def download(
        self,
        url: str,
        quality: DownloadQuality = DownloadQuality.BEST,
        format_opt: VideoFormatOption = VideoFormatOption.MP4,
        output_dir: Optional[str] = None,
        custom_filename: Optional[str] = None,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> DownloadResult:
        """
        Télécharge une vidéo depuis l'URL fournie avec la qualité et le format choisis.
        Sauvegarde un fichier download_metadata.json associé.
        """
        clean_url = url.strip()
        target_dir = Path(output_dir) if output_dir else self.download_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Configuration des sélecteurs de format selon la qualité demandée
        if quality == DownloadQuality.AUDIO_ONLY:
            format_selector = "bestaudio/best"
        elif quality == DownloadQuality.RES_1080P:
            format_selector = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
        elif quality == DownloadQuality.RES_720P:
            format_selector = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        else:  # BEST
            format_selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

        # Modèle de nom de fichier
        if custom_filename:
            safe_name = sanitize_filename(custom_filename)
            outtmpl = str(target_dir / f"{safe_name}.%(ext)s")
        else:
            outtmpl = str(target_dir / "%(title).100s [%(id)s].%(ext)s")

        # 2. Hook de suivi de progression
        def _progress_hook(d: Dict[str, Any]) -> None:
            if cancel_check and cancel_check():
                raise DownloadCancelled("Téléchargement annulé par l'utilisateur.")

            if not progress_callback:
                return

            status = d.get('status', 'downloading')
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes') or 0
            speed = d.get('speed')
            eta = d.get('eta')
            fn = Path(d.get('filename', '')).name

            percent = 0.0
            if total > 0:
                percent = round((downloaded / total) * 100.0, 1)

            prog = DownloadProgress(
                status=status,
                percent=min(100.0, percent),
                downloaded_bytes=downloaded,
                total_bytes=total if total > 0 else None,
                speed_bytes_per_sec=speed,
                eta_seconds=eta,
                filename=fn
            )
            progress_callback(prog)

        # 3. Options yt-dlp
        ydl_opts: Dict[str, Any] = {
            'format': format_selector,
            'outtmpl': outtmpl,
            'progress_hooks': [_progress_hook],
            'quiet': True,
            'no_warnings': True,
            'windowsfilenames': True,  # Assure des noms sécurisés sous Windows
        }

        # Forcer le conteneur MP4 si demandé
        if format_opt == VideoFormatOption.MP4:
            ydl_opts['merge_output_format'] = 'mp4'
        elif format_opt == VideoFormatOption.MKV:
            ydl_opts['merge_output_format'] = 'mkv'

        ffmpeg_loc = self._get_ffmpeg_location()
        if ffmpeg_loc:
            ydl_opts['ffmpeg_location'] = ffmpeg_loc

        # 4. Exécution du téléchargement
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(clean_url, download=True)
                if not info_dict:
                    raise ValueError("Échec de téléchargement : flux introuvable.")

                # Traitement de l'entrée sélectionnée
                if 'entries' in info_dict and info_dict['entries']:
                    info_dict = next(iter(info_dict['entries']))

                final_file_path = ydl.prepare_filename(info_dict)
                # Si merge_output_format a été appliqué, l'extension finale est mp4 ou mkv
                if format_opt == VideoFormatOption.MP4 and not final_file_path.endswith('.mp4'):
                    stem_path = Path(final_file_path).with_suffix('.mp4')
                    if stem_path.is_file():
                        final_file_path = str(stem_path)

                final_path_obj = Path(final_file_path)
                if not final_path_obj.is_file():
                    # Recherche dans le dossier cible au cas où le nom aurait été ajusté
                    candidates = list(target_dir.glob(f"*{final_path_obj.stem}*"))
                    if candidates:
                        final_path_obj = candidates[0]

                title = info_dict.get('title') or final_path_obj.stem
                uploader = info_dict.get('uploader') or info_dict.get('channel')
                duration = float(info_dict.get('duration') or 0.0)
                extractor = info_dict.get('extractor_key') or info_dict.get('extractor') or "Inconnu"
                file_size = final_path_obj.stat().st_size if final_path_obj.is_file() else 0

                # 5. Création de download_metadata.json
                meta_file = final_path_obj.parent / f"{final_path_obj.stem}_download_metadata.json"
                meta_data = {
                    "source_url": clean_url,
                    "extractor": extractor,
                    "original_title": title,
                    "uploader": uploader,
                    "duration": duration,
                    "selected_quality": quality.value,
                    "selected_format": format_opt.value,
                    "downloaded_at": datetime.now().isoformat(),
                    "local_file": str(final_path_obj.resolve()),
                    "file_size_bytes": file_size
                }
                meta_file.write_text(json.dumps(meta_data, indent=2, ensure_ascii=False), encoding="utf-8")

                return DownloadResult(
                    success=True,
                    source_url=clean_url,
                    local_file_path=str(final_path_obj.resolve()),
                    title=title,
                    duration_seconds=duration,
                    uploader=uploader,
                    extractor=extractor,
                    file_size_bytes=file_size,
                    metadata_json_path=str(meta_file.resolve())
                )

        except DownloadCancelled:
            return DownloadResult(
                success=False,
                source_url=clean_url,
                error_message="Téléchargement annulé par l'utilisateur."
            )
        except Exception as e:
            err_msg = str(e)
            return DownloadResult(
                success=False,
                source_url=clean_url,
                error_message=f"Erreur de téléchargement : {err_msg}"
            )
