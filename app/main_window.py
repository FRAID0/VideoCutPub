"""
VideoCutPub - PySide6 Main Application Window
Assembles controls, queue management, progress meters, and Qt Worker Thread integration.
Zero FFmpeg logic inside GUI widgets.
"""

import os
from pathlib import Path
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit, QComboBox, QRadioButton, QButtonGroup,
    QProgressBar, QFileDialog, QMessageBox, QFrame, QCheckBox
)

from app.styles.dark_theme import DARK_THEME_QSS
from app.widgets.queue_table import QueueTableWidget
from app.worker import QueueWorkerThread
from core.models import CutMode, QueueProgress, JobStatus, CutResult
from core.queue_manager import QueueManager, DuplicateJobError


class MainWindow(QMainWindow):
    """Fenêtre principale Desktop de VideoCutPub."""

    def __init__(self, queue_manager: QueueManager = None):
        super().__init__()
        self.queue_manager = queue_manager or QueueManager()
        self.worker_thread = None
        
        self.setWindowTitle("VideoCutPub - Studio de Découpage Vidéo")
        self.resize(1000, 700)
        self.setStyleSheet(DARK_THEME_QSS)

        self._init_ui()

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 1. En-tête & Barre d'action Fichiers
        top_bar = QHBoxLayout()
        self.btn_add_files = QPushButton("➕ Ajouter des Vidéos")
        self.btn_add_files.clicked.connect(self._on_add_files_clicked)
        
        self.btn_add_dir = QPushButton("📂 Ajouter un Dossier")
        self.btn_add_dir.clicked.connect(self._on_add_dir_clicked)

        self.btn_import_url = QPushButton("🔗 Importer depuis une URL")
        self.btn_import_url.clicked.connect(self._on_import_url_clicked)

        self.btn_clear_queue = QPushButton("🗑️ Vider la File")
        self.btn_clear_queue.clicked.connect(self._on_clear_queue_clicked)

        top_bar.addWidget(self.btn_add_files)
        top_bar.addWidget(self.btn_add_dir)
        top_bar.addWidget(self.btn_import_url)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_clear_queue)
        main_layout.addLayout(top_bar)

        # 2. Tableau de la file d'attente (Drag & Drop)
        self.queue_table = QueueTableWidget(self)
        self.queue_table.files_dropped_signal.connect(self._on_files_dropped)
        main_layout.addWidget(self.queue_table)

        self.setMinimumSize(850, 580)

        # 3. Panneau de Configuration Réactif (Grid Layout)
        config_box = QGroupBox("Configuration du Découpage")
        config_layout = QGridLayout(config_box)
        config_layout.setContentsMargins(12, 12, 12, 12)
        config_layout.setSpacing(10)

        # Ligne 0 : Durée et Mode
        config_layout.addWidget(QLabel("Durée par segment :"), 0, 0)
        self.combo_duration = QComboBox()
        self.combo_duration.setEditable(True)
        self.combo_duration.addItems(["10s", "30s", "1m", "2m", "5m", "10m", "00:02:30"])
        self.combo_duration.setCurrentText("2m")
        config_layout.addWidget(self.combo_duration, 0, 1)

        config_layout.addWidget(QLabel("Mode de découpe :"), 0, 2)
        mode_sub_layout = QHBoxLayout()
        self.radio_fast = QRadioButton("⚡ Rapide (-c copy)")
        self.radio_fast.setToolTip("Découpage ultra-rapide sans re-encodage (aligné sur les keyframes).")
        self.radio_fast.setChecked(True)
        
        self.radio_precise = QRadioButton("🎯 Précis (Réencodage H.264)")
        self.radio_precise.setToolTip("Découpage à précision temporelle élevée via réencodage.")

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_fast)
        self.mode_group.addButton(self.radio_precise)

        mode_sub_layout.addWidget(self.radio_fast)
        mode_sub_layout.addWidget(self.radio_precise)
        mode_sub_layout.addStretch()
        config_layout.addLayout(mode_sub_layout, 0, 3)

        # Ligne 1 : Format Réseaux Sociaux
        config_layout.addWidget(QLabel("Format Réseaux Sociaux :"), 1, 0)
        self.combo_social = QComboBox()
        self.combo_social.addItems([
            "Aucun (Ratio original)",
            "Vertical 9:16 - Fond Flouté (Shorts / Reels / TikTok)",
            "Vertical 9:16 - Recadrage Centré (Plein Écran)",
            "Carré 1:1 (Instagram / Post)"
        ])
        config_layout.addWidget(self.combo_social, 1, 1, 1, 3)

        # Ligne 2 : Sous-Titres & Transcription IA
        config_layout.addWidget(QLabel("Sous-Titres & IA :"), 2, 0)
        sub_layout = QHBoxLayout()
        self.chk_transcribe = QCheckBox("Générer .srt (Faster-Whisper)")
        self.chk_transcribe.setToolTip("Transcrit automatiquement l'audio en texte horodaté.")
        
        self.combo_whisper_model = QComboBox()
        self.combo_whisper_model.addItems(["base", "tiny", "small"])
        self.combo_whisper_model.setToolTip("Modèle Faster-Whisper (base = bon équilibre vitesse/précision).")

        self.chk_burn = QCheckBox("Incruster dans la vidéo (Burn-in)")
        self.chk_burn.setToolTip("Incruste les sous-titres stylisés de manière définitive dans la vidéo.")

        self.combo_style = QComboBox()
        self.combo_style.addItems([
            "TikTok Impact (Jaune / Safe Zone)",
            "Shorts / Reels Clean (Blanc)",
            "Bandeau Sombre Opaque",
            "Minimaliste"
        ])
        self.combo_style.setToolTip("Style visuel des sous-titres incrustés et positionnement dans la safe zone.")

        self.chk_metadata = QCheckBox("📝 Métadonnées IA (Hooks & Tags)")
        self.chk_metadata.setChecked(True)
        self.chk_metadata.setToolTip("Génère automatiquement 3 accroches virales, description SEO et hashtags.")
        self.chk_metadata.toggled.connect(lambda checked: self.chk_transcribe.setChecked(True) if checked else None)

        sub_layout.addWidget(self.chk_transcribe)
        sub_layout.addWidget(self.combo_whisper_model)
        sub_layout.addWidget(self.chk_burn)
        sub_layout.addWidget(self.combo_style)
        sub_layout.addWidget(self.chk_metadata)
        config_layout.addLayout(sub_layout, 2, 1, 1, 3)

        # Ligne 3 : Dossier de sortie
        config_layout.addWidget(QLabel("Dossier de sortie :"), 3, 0)
        self.entry_output_dir = QLineEdit()
        default_out = str((Path.cwd() / "output").resolve())
        self.entry_output_dir.setText(default_out)
        config_layout.addWidget(self.entry_output_dir, 3, 1, 1, 2)

        self.btn_browse_out = QPushButton("Parcourir...")
        self.btn_browse_out.clicked.connect(self._on_browse_output_clicked)
        config_layout.addWidget(self.btn_browse_out, 3, 3)

        main_layout.addWidget(config_box)

        # 4. Barres de Progression & Informations
        progress_box = QGroupBox("Progression des Traitements")
        progress_layout = QVBoxLayout(progress_box)

        self.lbl_status = QLabel("Prêt. Ajoutez des vidéos pour démarrer.")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #89b4fa;")
        progress_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        main_layout.addWidget(progress_box)

        # 5. Boutons de Contrôle Principal (Lancer / Annuler)
        action_bar = QHBoxLayout()
        self.btn_start = QPushButton("▶ LANCER LE TRAITEMENT")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setFixedHeight(40)
        self.btn_start.clicked.connect(self._on_start_clicked)

        self.btn_cancel = QPushButton("⏹ ANNULER")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        action_bar.addWidget(self.btn_start, stretch=3)
        action_bar.addWidget(self.btn_cancel, stretch=1)
        main_layout.addLayout(action_bar)

    # === Callbacks Événements UI ===

    def _on_add_files_clicked(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Sélectionner les vidéos", "",
            "Fichiers Vidéo (*.mp4 *.mov *.avi *.mkv);;Tous les fichiers (*)"
        )
        if files:
            self._add_paths_to_queue(files)

    def _on_add_dir_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier de vidéos")
        if directory:
            out_dir = self.entry_output_dir.text()
            dur = self.combo_duration.currentText()
            mode = CutMode.FAST if self.radio_fast.isChecked() else CutMode.PRECISE
            try:
                added = self.queue_manager.add_jobs_from_directory(directory, out_dir, dur, mode)
                self._update_queue_display()
                self.lbl_status.setText(f"{len(added)} vidéo(s) ajoutée(s) depuis le dossier.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", str(e))

    def _on_files_dropped(self, paths: list[str]) -> None:
        self._add_paths_to_queue(paths)

    def _add_paths_to_queue(self, paths: list[str]) -> None:
        out_dir = self.entry_output_dir.text()
        dur = self.combo_duration.currentText()
        mode = CutMode.FAST if self.radio_fast.isChecked() else CutMode.PRECISE
        
        added_count = 0
        for p in paths:
            path_obj = Path(p)
            if path_obj.is_dir():
                added = self.queue_manager.add_jobs_from_directory(str(path_obj), out_dir, dur, mode)
                added_count += len(added)
            elif path_obj.is_file():
                try:
                    self.queue_manager.add_job(str(path_obj), out_dir, dur, mode)
                    added_count += 1
                except DuplicateJobError:
                    pass

        self._update_queue_display()
        self.lbl_status.setText(f"{added_count} fichier(s) ajouté(s) à la file d'attente.")

    def _on_clear_queue_clicked(self) -> None:
        self.queue_manager.clear()
        self._update_queue_display()
        self.progress_bar.setValue(0)
        self.lbl_status.setText("File d'attente vidée.")

    def _on_browse_output_clicked(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "Dossier de sortie par défaut")
        if dir_path:
            self.entry_output_dir.setText(dir_path)

    def _on_start_clicked(self) -> None:
        if not self.queue_manager.jobs:
            QMessageBox.warning(self, "Attention", "La file d'attente est vide. Ajoutez des vidéos avant de lancer.")
            return

        # Mise à jour des configurations de chaque job selon les entrées actuelles
        out_dir = self.entry_output_dir.text()
        dur = self.combo_duration.currentText()
        mode = CutMode.FAST if self.radio_fast.isChecked() else CutMode.PRECISE

        social_choice = self.combo_social.currentText()
        social_cfg = None
        if "Fond Flouté" in social_choice:
            social_cfg = {"aspect_ratio": "9:16", "mode": "blurred_background", "target_width": 1080, "target_height": 1920}
        elif "Recadrage Centré" in social_choice:
            social_cfg = {"aspect_ratio": "9:16", "mode": "center_crop", "target_width": 1080, "target_height": 1920}
        elif "Carré 1:1" in social_choice:
            social_cfg = {"aspect_ratio": "1:1", "mode": "center_crop", "target_width": 1080, "target_height": 1080}

        style_choice = self.combo_style.currentText()
        preset_map = {
            "TikTok Impact (Jaune / Safe Zone)": "tiktok_high_contrast",
            "Shorts / Reels Clean (Blanc)": "shorts_clean",
            "Bandeau Sombre Opaque": "boxed_high_contrast",
            "Minimaliste": "minimal",
        }
        subtitle_preset = preset_map.get(style_choice, "tiktok_high_contrast")
        transcribe_enabled = self.chk_transcribe.isChecked()
        burn_enabled = self.chk_burn.isChecked()
        metadata_enabled = self.chk_metadata.isChecked()
        whisper_model = self.combo_whisper_model.currentText()

        for job in self.queue_manager.jobs:
            if job.status == JobStatus.PENDING:
                job.output_base_dir = str(Path(out_dir).resolve())
                job.segment_duration = dur
                job.cut_mode = mode
                job.social_transform = social_cfg
                job.transcribe = transcribe_enabled
                job.whisper_model = whisper_model
                job.burn_subtitles = burn_enabled
                job.subtitle_preset = subtitle_preset
                job.generate_metadata = metadata_enabled

        # UI State : désactiver boutons de configuration pendant le run
        self._set_controls_enabled(False)
        self._update_queue_display()

        # Instanciation et lancement du QThread Worker
        self.worker_thread = QueueWorkerThread(self.queue_manager, self)
        self.worker_thread.progress_signal.connect(self._on_worker_progress)
        self.worker_thread.finished_signal.connect(self._on_worker_finished)
        self.worker_thread.error_signal.connect(self._on_worker_error)
        self.worker_thread.start()

    def _on_cancel_clicked(self) -> None:
        if self.queue_manager:
            self.queue_manager.cancel()
            self.lbl_status.setText("Annulation demandée...")

    @Slot(QueueProgress)
    def _on_worker_progress(self, progress: QueueProgress) -> None:
        self.progress_bar.setValue(int(progress.overall_progress_percent))
        msg = f"Vidéo {progress.current_job_index}/{progress.total_jobs} : {progress.current_job_filename} | " \
              f"Global : {progress.overall_progress_percent}% | Écoulé : {progress.elapsed_seconds}s | Restant est. : {progress.estimated_remaining_seconds}s"
        self.lbl_status.setText(msg)
        self._update_queue_display()

    @Slot(list)
    def _on_worker_finished(self, results: list[CutResult]) -> None:
        self._set_controls_enabled(True)
        self.progress_bar.setValue(100)
        self._update_queue_display()
        
        comp = sum(1 for j in self.queue_manager.jobs if j.status == JobStatus.COMPLETED)
        fail = sum(1 for j in self.queue_manager.jobs if j.status == JobStatus.FAILED)
        
        msg = f"Traitement terminé ! Réussies : {comp}, Échecs : {fail}."
        self.lbl_status.setText(msg)
        QMessageBox.information(self, "Succès", f"{msg}\nRésultats dans : {self.entry_output_dir.text()}")

    @Slot(str)
    def _on_worker_error(self, err_msg: str) -> None:
        self._set_controls_enabled(True)
        self.lbl_status.setText(f"Erreur globale : {err_msg}")
        QMessageBox.critical(self, "Erreur Traitement", f"Une erreur imprévue est survenue : {err_msg}")

    def _on_import_url_clicked(self) -> None:
        from app.widgets.download_dialog import DownloadUrlDialog
        dlg = DownloadUrlDialog(parent=self)
        dlg.video_downloaded_signal.connect(self._on_video_downloaded)
        dlg.exec()

    @Slot(str)
    def _on_video_downloaded(self, file_path: str) -> None:
        out_dir = self.entry_output_dir.text()
        dur = self.combo_duration.currentText()
        mode = CutMode.FAST if self.radio_fast.isChecked() else CutMode.PRECISE
        try:
            self.queue_manager.add_job(file_path, out_dir, dur, mode)
            self._update_queue_display()
            self.lbl_status.setText(f"Vidéo importée depuis URL ajoutée : {Path(file_path).name}")
        except DuplicateJobError:
            pass

    def _update_queue_display(self) -> None:
        self.queue_table.update_jobs(self.queue_manager.jobs)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.btn_add_files.setEnabled(enabled)
        self.btn_add_dir.setEnabled(enabled)
        self.btn_import_url.setEnabled(enabled)
        self.btn_clear_queue.setEnabled(enabled)
        self.btn_start.setEnabled(enabled)
        self.btn_cancel.setEnabled(not enabled)
        self.combo_duration.setEnabled(enabled)
        self.combo_social.setEnabled(enabled)
        self.chk_transcribe.setEnabled(enabled)
        self.combo_whisper_model.setEnabled(enabled)
        self.chk_burn.setEnabled(enabled)
        self.combo_style.setEnabled(enabled)
        self.chk_metadata.setEnabled(enabled)
        self.radio_fast.setEnabled(enabled)
        self.radio_precise.setEnabled(enabled)
        self.entry_output_dir.setEnabled(enabled)
        self.btn_browse_out.setEnabled(enabled)


