"""
VideoCutPub - Unit and Integration Tests for AI Social Metadata Generator (Étape 8)
Validates keyword extraction, topic detection, viral hook formulation,
SEO description building, hashtag generation, and file exporting.
"""

import json
import shutil
import tempfile
from pathlib import Path
import pytest

from ai.transcription import TranscriptSegment
from ai.metadata_generator import MetadataGenerator, SocialMetadata


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="videocutpub_meta_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def generator():
    return MetadataGenerator()


# ==========================================
# 1. Extraction de Mots-Clés et Thématiques
# ==========================================

def test_extract_keywords(generator):
    """Vérifie que les mots vides sont filtrés et que les termes clés ressortent."""
    text = "Bienvenue dans cette vidéo, aujourd'hui on va faire un dépôt USDT avec l'application Bitkap et scanner le code."
    keywords = generator._extract_keywords(text, top_n=5)
    
    assert len(keywords) > 0
    # USDT, bitkap, dépôt ou scanner doivent être retenus
    assert any(k in ["usdt", "bitkap", "dépôt", "scanner", "application"] for k in keywords)
    # Les mots vides ne doivent pas être dans les mots-clés
    for stop_w in ["dans", "cette", "avec", "bienvenue"]:
        assert stop_w not in keywords


def test_detect_topic(generator):
    """Vérifie la détection thématique selon les concepts identifiés."""
    crypto_text = "Faire un dépôt en USDT avec la crypto et transférer des fonds vers son wallet."
    assert generator._detect_topic(["usdt", "crypto"], crypto_text) == "Crypto & Finance"

    tech_text = "Écrire du code Python propre avec des fonctions et corriger les bugs sur Linux."
    assert generator._detect_topic(["python", "code"], tech_text) == "Tech & Informatique"

    business_text = "Trouver des clients qualifiés et booster sa stratégie marketing et ses ventes."
    assert generator._detect_topic(["marketing", "clients"], business_text) == "Business & Entrepreneuriat"


# ==========================================
# 2. Hooks, Titres et Hashtags
# ==========================================

def test_generate_hooks_format(generator):
    """Vérifie qu'exactement 3 hooks distincts sont formulés."""
    hooks = generator._generate_hooks("Crypto & Finance", ["usdt", "transaction"], "Voici comment débuter.")
    assert len(hooks) == 3
    assert any("secret" in h.lower() for h in hooks)
    assert any("comment" in h.lower() for h in hooks)
    assert any("erreur" in h.lower() for h in hooks)


def test_generate_hashtags_format(generator):
    """Vérifie que tous les hashtags sont valides (commencent par #, sans espace)."""
    tags = generator._generate_hashtags("Crypto & Finance", ["usdt", "bitcoin", "bitkap"])
    assert len(tags) >= 5
    for tag in tags:
        assert tag.startswith("#")
        assert " " not in tag
        assert tag == tag.lower()


# ==========================================
# 3. Génération Globale et Export
# ==========================================

def test_generate_from_text(generator):
    """Vérifie la génération complète des métadonnées sociales."""
    text = (
        "Bienvenue dans cette vidéo ! On va voir comment faire une transaction et un dépôt rapide en USDT "
        "sur HitCup pour recharger votre balance sans faire d'erreur."
    )
    meta = generator.generate_from_text(text)

    assert isinstance(meta, SocialMetadata)
    assert len(meta.title) > 10
    assert len(meta.hooks) == 3
    assert len(meta.hashtags) >= 5
    assert len(meta.keywords) > 0
    assert "Abonne-toi" in meta.description
    assert meta.detected_topic == "Crypto & Finance"


def test_generate_from_segments(generator):
    """Vérifie la génération à partir d'une liste de TranscriptSegment de Faster-Whisper."""
    segments = [
        TranscriptSegment(
            index=1, start_sec=0.0, end_sec=3.0,
            start_srt="00:00:00,000", end_srt="00:00:03,000",
            text="Dans ce tutoriel python,", confidence=0.98
        ),
        TranscriptSegment(
            index=2, start_sec=3.0, end_sec=6.5,
            start_srt="00:00:03,000", end_srt="00:00:06,500",
            text="nous allons créer une application web complète.", confidence=0.95
        )
    ]
    meta = generator.generate_from_segments(segments)
    assert meta.detected_topic == "Tech & Informatique"
    assert any("python" in tag for tag in meta.hashtags)


def test_generate_from_empty_text(generator):
    """Vérifie la résilience en cas de vidéo silencieuse ou texte vide."""
    meta = generator.generate_from_text("   ")
    assert isinstance(meta, SocialMetadata)
    assert len(meta.title) > 0
    assert len(meta.hooks) == 3
    assert len(meta.hashtags) > 0


def test_export_post_txt_and_json(generator, temp_dir):
    """Vérifie que post_content.txt et metadata_ai.json sont créés avec un formatage impeccable."""
    text = "Comment réussir un dépôt USDT sur Bitkap sans perdre d'argent."
    meta = generator.generate_from_text(text)

    txt_path = temp_dir / "post_content.txt"
    json_path = temp_dir / "metadata_ai.json"

    out_txt = generator.export_post_txt(meta, str(txt_path))
    out_json = generator.export_json(meta, str(json_path))

    assert Path(out_txt).is_file()
    assert Path(out_json).is_file()

    # Vérification du fichier TXT
    txt_content = Path(out_txt).read_text(encoding="utf-8")
    assert "TITRE PRINCIPAL CONSEILLÉ" in txt_content
    assert "DESCRIPTION PRÊTE À COLLER" in txt_content
    assert "HASHTAGS" in txt_content
    assert "#" in txt_content

    # Vérification du fichier JSON
    json_data = json.loads(Path(out_json).read_text(encoding="utf-8"))
    assert json_data["title"] == meta.title
    assert len(json_data["hooks"]) == 3
    assert len(json_data["hashtags"]) == len(meta.hashtags)
