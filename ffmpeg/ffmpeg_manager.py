"""
VideoCutPub - FFmpeg Executable Manager
Detects, locates, and manages FFmpeg and FFprobe binary execution.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple, Optional, List


class FFmpegNotFoundError(Exception):
    """Exception levée lorsque FFmpeg ou FFprobe est introuvable sur le système."""
    pass


class FFmpegExecutionError(Exception):
    """Exception levée lorsqu'une commande FFmpeg échoue."""
    def __init__(self, command: List[str], returncode: int, stdout: str, stderr: str):
        super().__init__(f"FFmpeg command failed with return code {returncode}.\nStderr: {stderr}")
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FFmpegManager:
    """
    Gestionnaire de localisation et d'exécution des binaires FFmpeg et FFprobe.
    """

    def __init__(self, custom_ffmpeg_path: Optional[str] = None, custom_ffprobe_path: Optional[str] = None):
        self.ffmpeg_path = custom_ffmpeg_path or self._find_binary("ffmpeg")
        self.ffprobe_path = custom_ffprobe_path or self._find_binary("ffprobe")

    @classmethod
    def _find_binary(cls, binary_name: str) -> str:
        """
        Recherche le binaire (ffmpeg ou ffprobe) sur le PATH système,
        dans le sous-dossier du projet ou via imageio_ffmpeg.
        """
        exec_name = f"{binary_name}.exe" if sys.platform == "win32" else binary_name

        # 1. Recherche sur le PATH système
        found_path = shutil.which(binary_name) or shutil.which(exec_name)
        if found_path and os.path.isfile(found_path):
            return found_path

        # 2. Recherche dans les sous-dossiers locaux du projet
        project_root = Path(__file__).resolve().parent.parent
        possible_local_paths = [
            project_root / "assets" / "ffmpeg" / "bin" / exec_name,
            project_root / "ffmpeg" / "bin" / exec_name,
            project_root / exec_name,
        ]
        for p in possible_local_paths:
            if p.is_file():
                return str(p)

        # 3. Recherche via imageio_ffmpeg ou static_ffmpeg
        try:
            import static_ffmpeg
            static_ffmpeg.add_paths()
            found_path = shutil.which(binary_name) or shutil.which(exec_name)
            if found_path and os.path.isfile(found_path):
                return found_path
        except Exception:
            pass

        if binary_name == "ffmpeg":
            try:
                import imageio_ffmpeg
                path = imageio_ffmpeg.get_ffmpeg_exe()
                if path and os.path.isfile(path):
                    return path
            except ImportError:
                pass

        raise FFmpegNotFoundError(
            f"Le binaire '{binary_name}' n'a pas été trouvé sur le système.\n"
            f"Veuillez installer FFmpeg et l'ajouter au PATH système, ou le placer dans assets/ffmpeg/bin/."
        )

    def is_available(self) -> bool:
        """Vérifie si FFmpeg et FFprobe sont tous deux accessibles."""
        try:
            return bool(self.ffmpeg_path and self.ffprobe_path and 
                        os.path.isfile(self.ffmpeg_path) and os.path.isfile(self.ffprobe_path))
        except Exception:
            return False

    def run_ffmpeg(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Exécute une commande FFmpeg avec les arguments fournis."""
        cmd = [self.ffmpeg_path] + args
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if check and result.returncode != 0:
                raise FFmpegExecutionError(cmd, result.returncode, result.stdout, result.stderr)
            return result
        except FileNotFoundError:
            raise FFmpegNotFoundError(f"Binaire FFmpeg introuvable au chemin : {self.ffmpeg_path}")

    def run_ffprobe(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Exécute une commande FFprobe avec les arguments fournis."""
        cmd = [self.ffprobe_path] + args
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if check and result.returncode != 0:
                raise FFmpegExecutionError(cmd, result.returncode, result.stdout, result.stderr)
            return result
        except FileNotFoundError:
            raise FFmpegNotFoundError(f"Binaire FFprobe introuvable au chemin : {self.ffprobe_path}")
