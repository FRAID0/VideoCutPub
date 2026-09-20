"""
VideoCutPub - URL Downloader Dialog (PySide6)
Interactive dialog for analyzing video URLs, selecting quality/format,
tracking download progress, and automatically adding to the QueueManager.
"""

from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QProgressBar, QGroupBox, QFormLayout, QMessageBox, QFrame
)

from core.download_models import (
    DownloadQuality,
    VideoFormatOption,
    VideoInfo,
    DownloadProgress,
    DownloadResult,
)
from core.downloader import VideoDownloader, format_bytes, format_speed


class AnalyzeWorker(QThread):
    """Worker QThread pour l'analyse sans blocage de l'URL."""
    success_signal = Signal(VideoInfo)
    error_signal = Signal(str)

    def __init__(self, downloader: VideoDownloader, url: str, parent=None):
        super().__init__(parent)
        self.downloader = downloader
        self.url = url

    def run(self):
        try:
            info = self.downloader.extract_info(self.url)
            self.success_signal.emit(info)
        except Exception as e:
            self.error_signal.emit(str(e))


class DownloadWorker(QThread):
    """Worker QThread pour le téléchargement sans blocage."""
    progress_signal = Signal(DownloadProgress)
    finished_signal = Signal(DownloadResult)

    def __init__(self, downloader: VideoDownloader, url: str, quality: DownloadQuality, format_opt: VideoFormatOption, parent=None):
        super().__init__(parent)
        self.downloader = downloader
        self.url = url
        self.quality = quality
        self.format_opt = format_opt
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        result = self.downloader.download(
            url=self.url,
            quality=self.quality,
            format_opt=self.format_opt,
            progress_callback=self.progress_signal.emit,
            cancel_check=lambda: self._is_cancelled,
        )
        self.finished_signal.emit(result)


class DownloadUrlDialog(QDialog):
    """Boîte de dialogue d'importation et téléchargement vidéo via URL."""

    video_downloaded_signal = Signal(str)  # Émet le chemin local du fichier téléchargé

    def __init__(self, downloader: VideoDownloader = None, parent=None):
        super().__init__(parent)
        self.downloader = downloader or VideoDownloader()
        self.analyze_worker = None
        self.download_worker = None
        self.current_video_info = None

        self.setWindowTitle("🔗 Importer une Vidéo depuis un Lien (YouTube, TikTok, Streaming...)")
        self.resize(650, 480)
        self.setModal(True)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Champ de saisie d'URL
        url_box = QGroupBox("Lien Vidéo")
        url_layout = QHBoxLayout(url_box)

        self.entry_url = QLineEdit()
        self.entry_url.setPlaceholderText("Collez ici un lien : https://www.youtube.com/watch?v=... ou TikTok, Twitch...")
        self.btn_analyze = QPushButton("🔍 Analyser")
        self.btn_analyze.setFixedHeight(34)
        self.btn_analyze.clicked.connect(self._on_analyze_clicked)

        url_layout.addWidget(self.entry_url)
        url_layout.addWidget(self.btn_analyze)
        layout.addWidget(url_box)

        # 2. Carte d'informations pré-téléchargement
        self.info_box = QGroupBox("Informations de la Vidéo")
        self.info_box.setVisible(False)
        info_layout = QFormLayout(self.info_box)

        self.lbl_title = QLabel("-")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet("font-weight: bold; color: #89b4fa;")
        info_layout.addRow("Titre :", self.lbl_title)

        self.lbl_platform = QLabel("-")
        info_layout.addRow("Plateforme :", self.lbl_platform)

        self.lbl_duration = QLabel("-")
        info_layout.addRow("Durée :", self.lbl_duration)

        self.lbl_uploader = QLabel("-")
        info_layout.addRow("Créateur :", self.lbl_uploader)

        # Options de qualité et format
        opts_layout = QHBoxLayout()
        self.combo_quality = QComboBox()
        self.combo_quality.addItems([
            "Meilleure qualité disponible",
            "1080p (Full HD)",
            "720p (HD)",
            "Audio seul"
        ])
        opts_layout.addWidget(QLabel("Qualité :"))
        opts_layout.addWidget(self.combo_quality)

        self.combo_format = QComboBox()
        self.combo_format.addItems(["MP4 (Recommandé)", "MKV", "Original"])
        opts_layout.addWidget(QLabel("Format :"))
        opts_layout.addWidget(self.combo_format)
        info_layout.addRow("Options :", opts_layout)

        layout.addWidget(self.info_box)

        # 3. Zone de Progression
        self.progress_box = QGroupBox("Progression du Téléchargement")
        self.progress_box.setVisible(False)
        prog_layout = QVBoxLayout(self.progress_box)

        self.lbl_progress_status = QLabel("Téléchargement en cours...")
        prog_layout.addWidget(self.lbl_progress_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        prog_layout.addWidget(self.progress_bar)

        self.lbl_speed_eta = QLabel("Vitesse : - | Restant : -")
        self.lbl_speed_eta.setStyleSheet("color: #a6adc8; font-size: 11px;")
        prog_layout.addWidget(self.lbl_speed_eta)

        layout.addWidget(self.progress_box)

        layout.addStretch()

        # 4. Boutons d'Action Inférieurs
        btn_bar = QHBoxLayout()
        self.btn_download = QPushButton("⬇️ TÉLÉCHARGER ET IMPORTER")
        self.btn_download.setObjectName("btn_start")
        self.btn_download.setFixedHeight(40)
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._on_download_clicked)

        self.btn_cancel = QPushButton("Fermer")
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        btn_bar.addWidget(self.btn_download)
        btn_bar.addWidget(self.btn_cancel)
        layout.addLayout(btn_bar)

    def _on_analyze_clicked(self):
        url = self.entry_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Attention", "Veuillez coller une URL valide.")
            return

        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText("Analyse...")
        self.entry_url.setEnabled(False)

        self.analyze_worker = AnalyzeWorker(self.downloader, url, self)
        self.analyze_worker.success_signal.connect(self._on_analyze_success)
        self.analyze_worker.error_signal.connect(self._on_analyze_error)
        self.analyze_worker.start()

    @Slot(VideoInfo)
    def _on_analyze_success(self, info: VideoInfo):
        self.current_video_info = info
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("🔍 Analyser")
        self.entry_url.setEnabled(True)

        self.lbl_title.setText(info.title)
        self.lbl_platform.setText(info.extractor.capitalize())

        mins = int(info.duration_seconds // 60)
        secs = int(info.duration_seconds % 60)
        self.lbl_duration.setText(f"{mins}m {secs}s ({info.duration_seconds:.1f}s)")
        self.lbl_uploader.setText(info.uploader or "Non spécifié")

        self.info_box.setVisible(True)
        self.btn_download.setEnabled(True)

    @Slot(str)
    def _on_analyze_error(self, err_msg: str):
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("🔍 Analyser")
        self.entry_url.setEnabled(True)
        QMessageBox.critical(self, "Erreur d'analyse", f"Impossible d'analyser le lien :\n{err_msg}")

    def _on_download_clicked(self):
        if not self.current_video_info:
            return

        # Détermination des options choisies
        quality_map = {
            "Meilleure qualité disponible": DownloadQuality.BEST,
            "1080p (Full HD)": DownloadQuality.RES_1080P,
            "720p (HD)": DownloadQuality.RES_720P,
            "Audio seul": DownloadQuality.AUDIO_ONLY,
        }
        format_map = {
            "MP4 (Recommandé)": VideoFormatOption.MP4,
            "MKV": VideoFormatOption.MKV,
            "Original": VideoFormatOption.ORIGINAL,
        }

        chosen_quality = quality_map.get(self.combo_quality.currentText(), DownloadQuality.BEST)
        chosen_format = format_map.get(self.combo_format.currentText(), VideoFormatOption.MP4)

        self.btn_download.setEnabled(False)
        self.btn_analyze.setEnabled(False)
        self.progress_box.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_cancel.setText("Annuler")

        self.download_worker = DownloadWorker(
            self.downloader,
            self.current_video_info.url,
            chosen_quality,
            chosen_format,
            self
        )
        self.download_worker.progress_signal.connect(self._on_download_progress)
        self.download_worker.finished_signal.connect(self._on_download_finished)
        self.download_worker.start()

    @Slot(DownloadProgress)
    def _on_download_progress(self, prog: DownloadProgress):
        self.progress_bar.setValue(int(prog.percent))
        dl_str = format_bytes(prog.downloaded_bytes)
        tot_str = format_bytes(prog.total_bytes) if prog.total_bytes else "?"
        speed_str = format_speed(prog.speed_bytes_per_sec)
        eta_str = f"{prog.eta_seconds}s" if prog.eta_seconds else "--"

        self.lbl_progress_status.setText(f"Téléchargement : {prog.percent}% ({dl_str} / {tot_str})")
        self.lbl_speed_eta.setText(f"Vitesse : {speed_str} | Temps restant : {eta_str}")

    @Slot(DownloadResult)
    def _on_download_finished(self, result: DownloadResult):
        self.btn_cancel.setText("Fermer")
        self.btn_download.setEnabled(True)
        self.btn_analyze.setEnabled(True)

        if result.success:
            self.progress_bar.setValue(100)
            self.lbl_progress_status.setText("✅ Téléchargement terminé avec succès !")
            # Émission du signal pour ajout direct à la file d'attente
            self.video_downloaded_signal.emit(result.local_file_path)
            QMessageBox.information(
                self,
                "Téléchargement Réussi",
                f"La vidéo a été téléchargée et ajoutée à la file d'attente :\n{Path(result.local_file_path).name}"
            )
            self.accept()
        else:
            QMessageBox.critical(self, "Erreur de Téléchargement", f"Le téléchargement a échoué :\n{result.error_message}")

    def _on_cancel_clicked(self):
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
            self.lbl_progress_status.setText("Annulation en cours...")
        else:
            self.reject()
