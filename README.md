# 🎬 VideoCutPub — Video Content Processing & Publishing Studio

**VideoCutPub** est une plateforme desktop Python d'automatisation, de découpage et de préparation de contenu vidéo (Shorts, Reels, TikTok, YouTube).

---

## 🚀 Fonctionnalités Clés

* **⚡ Double Moteur FFmpeg :**
  * **Mode Rapide (`-c copy`) :** Découpage ultra-rapide sans re-encodage avec traçabilité des *keyframes* (`requested_start/end` vs `actual_start/end`).
  * **Mode Précis (Re-encodage) :** Coupe exacte à la milliseconde près.
* **📁 Structuration Automatique :** Isolation de chaque vidéo découpée dans son propre dossier dédié avec numérotation propre et génération d'un fichier `metadata.json`.
* **⚙️ File d'Attente Batch (Queue Manager) :** Traitement en lot de 100+ vidéos avec gestion de reprise sur erreur.
* **🖥️ GUI PySide6 (Qt 6) :** Interface graphique réactive (Signals/Slots), multithreadée (`QThread`) et modernisée.
* **📦 Social Packaging :** Préparation des contenus prêts à publier (Shorts/Reels 9:16, sous-titres SRT, miniatures, métadonnées TXT).

---

## 📂 Architecture du Projet

```
VideoCutPub/
├── app/          # Interface Graphique PySide6
├── core/         # Analyseur vidéo, découpeur, gestionnaire de file & fichiers
├── ffmpeg/       # Wrappers & binaires FFmpeg
├── ai/           # Modules d'IA (Faster-Whisper, auto-tagging)
├── subtitles/    # Générateur SRT & sous-titrage
├── social/       # Conversion de formats (16:9 -> 9:16)
├── publishing/   # Connecteurs & Social Packaging (YouTube, TikTok, Meta)
├── config/       # Paramètres & profils
├── tests/        # Tests unitaires et d'intégration
├── docs/         # Documentation & archives V0 (docs/legacy/)
└── main.py       # Point d'entrée principal
```

---

## 🛠️ Installation & Lancement

1. **Cloner le dépôt :**
   ```bash
   git clone https://github.com/FRAID0/VideoCutPub.git
   cd VideoCutPub
   ```

2. **Lancer sous Windows :**
   Double-cliquer sur `launch.bat` (crée automatiquement l'environnement virtuel `venv` et installe les dépendances).

---

## 📄 Licence
Sous licence MIT.
