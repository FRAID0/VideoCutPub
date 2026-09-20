"""
VideoCutPub - Social Publishing Hub Dialog (Étape 10)
Interactive GUI for publishing or semi-automatically preparing social packs
across YouTube, TikTok, and Meta platforms.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QTextEdit, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox, QFrame
)

from publishing.publishing_models import PublishPlatform, PublishStatus, PrivacyLevel, PublishingJob
from publishing.publish_queue import PublishQueueManager
from publishing.account_manager import AccountManager


class PublishDialog(QDialog):
    """
    Fenêtre interactive de publication pour un Social Pack.
    Permet la validation préalable par l'utilisateur (aucun envoi aveugle).
    """

    job_published_signal = Signal(PublishingJob)

    def __init__(self, pack_dir: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Studio de Publication Réseaux Sociaux (Étape 10)")
        self.resize(780, 680)

        self.account_manager = AccountManager()
        self.queue_manager = PublishQueueManager(self.account_manager)
        self.current_pack_dir = pack_dir or ""
        self.current_job: Optional[PublishingJob] = None

        self._init_ui()
        if self.current_pack_dir:
            self._load_pack(self.current_pack_dir)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        # 1. Sélection du Social Pack
        pack_box = QGroupBox("1. Dossier Social Pack Source")
        pack_layout = QHBoxLayout(pack_box)

        self.entry_pack_dir = QLineEdit()
        self.entry_pack_dir.setPlaceholderText("Sélectionnez le dossier social_pack/Segment XX...")
        self.entry_pack_dir.setText(self.current_pack_dir)
        self.btn_browse_pack = QPushButton("Parcourir Pack...")
        self.btn_browse_pack.clicked.connect(self._on_browse_pack_clicked)

        pack_layout.addWidget(self.entry_pack_dir, stretch=4)
        pack_layout.addWidget(self.btn_browse_pack, stretch=1)
        main_layout.addWidget(pack_box)

        # 2. Configuration Plateforme & Compte
        config_box = QGroupBox("2. Destination & Mode")
        config_layout = QGridLayout(config_box)

        config_layout.addWidget(QLabel("Plateforme :"), 0, 0)
        self.combo_platform = QComboBox()
        self.combo_platform.addItems([
            "YouTube (Shorts / Vidéo)",
            "TikTok (Direct Post / FILE_UPLOAD)",
            "Meta & Autres (Mode Semi-Automatique / Presse-Papier)"
        ])
        self.combo_platform.currentIndexChanged.connect(self._on_platform_changed)
        config_layout.addWidget(self.combo_platform, 0, 1)

        config_layout.addWidget(QLabel("Mode de publication :"), 0, 2)
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Semi-Automatique (Presse-papier + Portail Web)", "API Officielle"])
        config_layout.addWidget(self.combo_mode, 0, 3)

        config_layout.addWidget(QLabel("Compte :"), 1, 0)
        self.combo_account = QComboBox()
        self._refresh_accounts()
        config_layout.addWidget(self.combo_account, 1, 1)

        config_layout.addWidget(QLabel("Confidentialité :"), 1, 2)
        self.combo_privacy = QComboBox()
        self.combo_privacy.addItems(["Privé (Recommandé / Projets en test)", "Non-répertorié", "Public"])
        config_layout.addWidget(self.combo_privacy, 1, 3)

        main_layout.addWidget(config_box)

        # 3. Prévisualisation & Modification du Contenu
        content_box = QGroupBox("3. Prévisualisation du Contenu Prêt à Publier")
        content_layout = QVBoxLayout(content_box)

        content_layout.addWidget(QLabel("Titre du post :"))
        self.entry_title = QLineEdit()
        content_layout.addWidget(self.entry_title)

        content_layout.addWidget(QLabel("Description & Appel à l'action :"))
        self.text_description = QTextEdit()
        self.text_description.setMaximumHeight(110)
        content_layout.addWidget(self.text_description)

        content_layout.addWidget(QLabel("Hashtags :"))
        self.entry_hashtags = QLineEdit()
        content_layout.addWidget(self.entry_hashtags)

        # Infos fichiers
        self.lbl_video_file = QLabel("Vidéo : Aucune")
        self.lbl_video_file.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self.lbl_thumb_file = QLabel("Miniature : Aucune")
        self.lbl_thumb_file.setStyleSheet("color: #a6adc8; font-size: 11px;")
        content_layout.addWidget(self.lbl_video_file)
        content_layout.addWidget(self.lbl_thumb_file)

        main_layout.addWidget(content_box)

        # 4. Consentement Explicite (TikTok)
        self.chk_consent = QCheckBox("✓ J'autorise expressément la publication de cette vidéo sur mon compte social (Consentement requis)")
        self.chk_consent.setStyleSheet("font-weight: bold; color: #fab387;")
        self.chk_consent.setChecked(False)
        self.chk_consent.setVisible(False)
        main_layout.addWidget(self.chk_consent)

        # 5. Barre d'action
        action_layout = QHBoxLayout()
        self.btn_publish = QPushButton("🚀 PRÉPARER & PUBLIER")
        self.btn_publish.setFixedHeight(45)
        self.btn_publish.setStyleSheet("font-weight: bold; font-size: 14px; background-color: #a6e3a1; color: #11111b;")
        self.btn_publish.clicked.connect(self._on_publish_clicked)

        self.btn_close = QPushButton("Fermer")
        self.btn_close.setFixedHeight(45)
        self.btn_close.clicked.connect(self.close)

        action_layout.addWidget(self.btn_publish, stretch=3)
        action_layout.addWidget(self.btn_close, stretch=1)
        main_layout.addLayout(action_layout)

    def _on_platform_changed(self, idx: int) -> None:
        """Adapte l'interface aux spécificités de la plateforme."""
        is_tiktok = (idx == 1)
        self.chk_consent.setVisible(is_tiktok)
        self._refresh_accounts()

    def _refresh_accounts(self) -> None:
        self.combo_account.clear()
        self.combo_account.addItem("Compte par défaut / Navigateur actif", None)

        idx = self.combo_platform.currentIndex()
        platform_map = {
            0: PublishPlatform.YOUTUBE,
            1: PublishPlatform.TIKTOK,
            2: PublishPlatform.MANUAL
        }
        target_platform = platform_map.get(idx, PublishPlatform.MANUAL)

        accounts = self.account_manager.list_accounts(platform=target_platform)
        for acc in accounts:
            self.combo_account.addItem(f"{acc.display_name} ({acc.account_id})", acc.account_id)

    def _on_browse_pack_clicked(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier Social Pack")
        if folder:
            self.entry_pack_dir.setText(folder)
            self._load_pack(folder)

    def _load_pack(self, pack_dir_str: str) -> None:
        p = Path(pack_dir_str)
        if not p.is_dir():
            return

        idx = self.combo_platform.currentIndex()
        plat = PublishPlatform.YOUTUBE if idx == 0 else (PublishPlatform.TIKTOK if idx == 1 else PublishPlatform.MANUAL)

        try:
            job = self.queue_manager.create_job_from_pack(str(p), platform=plat)
            self.current_job = job
            self.entry_title.setText(job.title)
            self.text_description.setPlainText(job.description)
            self.entry_hashtags.setText(" ".join(job.hashtags))
            self.lbl_video_file.setText(f"Vidéo : {Path(job.source_video).name}")
            if job.thumbnail:
                self.lbl_thumb_file.setText(f"Miniature : {Path(job.thumbnail).name}")
            else:
                self.lbl_thumb_file.setText("Miniature : Non disponible")
        except Exception as e:
            QMessageBox.warning(self, "Erreur Pack", f"Impossible de charger le pack :\n{str(e)}")

    def _on_publish_clicked(self) -> None:
        if not self.current_job:
            pack_p = self.entry_pack_dir.text().strip()
            if not pack_p:
                QMessageBox.warning(self, "Attention", "Veuillez d'abord sélectionner un dossier Social Pack valide.")
                return
            self._load_pack(pack_p)
            if not self.current_job:
                return

        idx = self.combo_platform.currentIndex()
        platform_map = {
            0: PublishPlatform.YOUTUBE,
            1: PublishPlatform.TIKTOK,
            2: PublishPlatform.MANUAL
        }
        target_platform = platform_map.get(idx, PublishPlatform.MANUAL)

        # Mode API vs Semi-Auto
        is_semi_auto = (self.combo_mode.currentIndex() == 0) or (target_platform == PublishPlatform.MANUAL)
        if is_semi_auto:
            target_platform = PublishPlatform.MANUAL

        # Vérification du consentement pour TikTok
        if target_platform == PublishPlatform.TIKTOK and not self.chk_consent.isChecked():
            QMessageBox.warning(
                self, "Consentement Requis",
                "Conformément aux règles TikTok, vous devez cocher la case de consentement explicite avant de publier."
            )
            return

        # Mise à jour des valeurs éditées par l'utilisateur
        self.current_job.platform = target_platform
        self.current_job.title = self.entry_title.text().strip()
        self.current_job.description = self.text_description.toPlainText().strip()
        self.current_job.hashtags = [h.strip() for h in self.entry_hashtags.text().split() if h.strip()]

        privacy_idx = self.combo_privacy.currentIndex()
        if privacy_idx == 0:
            self.current_job.privacy = PrivacyLevel.PRIVATE
        elif privacy_idx == 1:
            self.current_job.privacy = PrivacyLevel.UNLISTED
        else:
            self.current_job.privacy = PrivacyLevel.PUBLIC

        if target_platform == PublishPlatform.TIKTOK:
            self.current_job.requires_user_consent = True
            self.current_job.user_consented_at = datetime.now()

        selected_acc_id = self.combo_account.currentData()
        self.current_job.account_id = selected_acc_id or ""

        # Lancement de l'exécution
        res = self.queue_manager.process_job(self.current_job)
        self.job_published_signal.emit(res)

        if res.status == PublishStatus.PUBLISHED:
            QMessageBox.information(
                self, "Succès",
                f"Publication réussie / préparée !\nStatut : {res.status.value}\nPlateforme : {res.platform.value}"
            )
            self.accept()
        else:
            QMessageBox.critical(
                self, "Erreur de Publication",
                f"Échec ({res.status.value}) :\n{res.last_error_message or 'Erreur inconnue'}"
            )
