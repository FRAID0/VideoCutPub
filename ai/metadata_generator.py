"""
VideoCutPub - AI Social Metadata Generator (Étape 8)
Extracts key concepts from transcripts to generate attention-grabbing hooks,
SEO descriptions, and targeted hashtags for TikTok, Shorts, and Reels.
Operates 100% offline via local NLP heuristics, with optional LLM connector.
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
from pydantic import BaseModel, Field

from ai.transcription import TranscriptSegment


class SocialMetadata(BaseModel):
    """Métadonnées sociales prêtes à la publication pour un extrait vidéo."""
    title: str = Field(..., description="Titre principal optimisé pour l'engagement")
    hooks: List[str] = Field(default_factory=list, description="3 propositions d'accroches pour les 3 premières secondes")
    description: str = Field(..., description="Description structurée avec résumé SEO et appel à l'action")
    hashtags: List[str] = Field(default_factory=list, description="Liste des hashtags ciblés (#tag)")
    keywords: List[str] = Field(default_factory=list, description="Mots-clés principaux extraits")
    call_to_action: str = Field("Abonne-toi pour ne rien manquer des prochains conseils !", description="Appel à l'action")
    detected_topic: str = Field("Général", description="Thématique principale détectée")


# Mots vides (stop words) pour le filtrage linguistique en français et anglais
FRENCH_STOP_WORDS: Set[str] = {
    "alors", "au", "aucuns", "aussi", "autre", "avant", "avec", "avoir", "bon", "car", "ce", "cela", "ces",
    "cet", "cette", "ceux", "chaque", "ci", "comme", "comment", "dans", "des", "du", "dedans", "dehors", "depuis",
    "devrait", "doit", "donc", "dos", "droite", "début", "elle", "elles", "en", "encore", "essai", "est", "et",
    "eu", "fait", "faites", "fois", "font", "hors", "ici", "il", "ils", "je", "juste", "la", "le", "les",
    "leur", "là", "ma", "maintenant", "mais", "mes", "mien", "moins", "mon", "mot", "même", "ni", "nommés",
    "notre", "nous", "nouveaux", "ou", "où", "par", "parce", "pas", "peut", "peu", "plupart", "pour", "pourquoi",
    "quand", "que", "quel", "quelle", "quelles", "quels", "qui", "sa", "sans", "ses", "seulement", "si", "sien",
    "son", "sont", "sous", "soyez", "sur", "ta", "tandis", "tellement", "tels", "tes", "ton", "tous", "tout",
    "trop", "très", "tu", "voici", "voie", "voient", "vont", "votre", "vous", "vu", "ça", "étaient", "état",
    "étions", "été", "être", "bien", "bienvenue", "faire", "dire", "vais", "cliq", "clique", "petit", "regarde",
    "vidéo", "aujourd", "hui", "aller", "allons", "voir"
}

TOPIC_KEYWORDS = {
    "Crypto & Finance": ["usdt", "crypto", "bitcoin", "argent", "deput", "dépôt", "retrait", "balance", "portefeuille", "wallet", "carte", "banque", "investir", "hitcup", "bitkap"],
    "Tech & Informatique": ["code", "python", "programme", "ordinateur", "logiciel", "web", "site", "application", "tutoriel", "linux", "windows", "bug", "serveur"],
    "Business & Entrepreneuriat": ["client", "vente", "marketing", "produit", "offre", "prix", "business", "succès", "stratégie", "croissance", "projet"],
    "Santé & Lifestyle": ["manger", "nutrition", "sport", "santé", "sommeil", "recette", "corps", "énergie", "bien-être", "routine"],
}


class MetadataGenerator:
    """
    Générateur de titres d'accroche, descriptions SEO et hashtags.
    Fonctionne 100% hors-ligne en mode heuristique/NLP, sans coût ni clé API.
    """

    def __init__(self):
        pass

    def _extract_keywords(self, text: str, top_n: int = 6) -> List[str]:
        """Extrait les mots les plus significatifs du texte."""
        clean = re.sub(r'[^\w\s]', ' ', text.lower())
        words = [w.strip() for w in clean.split() if len(w.strip()) > 3]
        filtered = [w for w in words if w not in FRENCH_STOP_WORDS]
        if not filtered:
            return ["astuce", "tutoriel", "conseil"]
        counts = Counter(filtered)
        return [word for word, _ in counts.most_common(top_n)]

    def _detect_topic(self, keywords: List[str], full_text: str) -> str:
        """Détecte la thématique dominante à partir des termes employés."""
        full_lower = full_text.lower()
        for topic, term_list in TOPIC_KEYWORDS.items():
            for term in term_list:
                if term in keywords or term in full_lower:
                    return topic
        return "Conseils & Tutoriels"

    def _generate_hooks(self, topic: str, keywords: List[str], first_sentence: str) -> List[str]:
        """Génère 3 propositions d'accroches adaptées aux formats courts TikTok/Shorts."""
        k1 = keywords[0].capitalize() if keywords else "Ça"
        k2 = keywords[1].capitalize() if len(keywords) > 1 else "Cette astuce"

        hooks = [
            f"Le secret pour réussir avec {k1} en 2026 !",
            f"Comment faire avec {k1} et {k2} facilement (Guide Rapide)",
            f"Ne faites JAMAIS cette erreur avec {k1}..."
        ]
        return hooks

    def _generate_hashtags(self, topic: str, keywords: List[str]) -> List[str]:
        """Génère une liste de hashtags équilibrés (populaires + mots-clés spécifiques + niche)."""
        tags = ["#shorts", "#reels", "#tiktok"]

        # Tags dérivés des mots-clés extraits en priorité
        for kw in keywords[:4]:
            tag_fmt = f"#{kw.lower()}"
            if tag_fmt not in tags:
                tags.append(tag_fmt)

        # Tags de thématique
        if topic == "Crypto & Finance":
            theme_tags = ["#crypto", "#finance", "#argent", "#usdt", "#investir"]
        elif topic == "Tech & Informatique":
            theme_tags = ["#tech", "#dev", "#tuto", "#informatique", "#programmation"]
        elif topic == "Business & Entrepreneuriat":
            theme_tags = ["#business", "#entreprendre", "#succes", "#marketing"]
        elif topic == "Santé & Lifestyle":
            theme_tags = ["#sante", "#nutrition", "#lifestyle", "#conseil"]
        else:
            theme_tags = ["#viral", "#pourtoi", "#fyp", "#conseil"]

        for t in theme_tags:
            if t not in tags:
                tags.append(t)

        return tags[:10]

    def generate_from_text(self, full_text: str) -> SocialMetadata:
        """Génère l'ensemble des métadonnées sociales à partir d'un texte brut."""
        clean_text = full_text.strip()
        if not clean_text:
            return SocialMetadata(
                title="Découvrez ce nouvel extrait vidéo !",
                hooks=[
                    "Regardez cet extrait vidéo !",
                    "Un moment clé à ne pas rater !",
                    "Découvrez ce conseil en vidéo !"
                ],
                description="Nouvel extrait vidéo à découvrir sans attendre !\n\nN'oubliez pas d'aimer la vidéo et de vous abonner.",
                hashtags=["#shorts", "#reels", "#tiktok", "#viral", "#video"],
                keywords=["video", "extrait"],
                detected_topic="Général"
            )

        # 1. Extraction et analyse
        keywords = self._extract_keywords(clean_text)
        topic = self._detect_topic(keywords, clean_text)

        # 2. Détection de la première phrase significative
        sentences = [s.strip() for s in re.split(r'[.!?\n]', clean_text) if len(s.strip()) > 10]
        first_sentence = sentences[0] if sentences else clean_text[:100]

        # 3. Formulations
        hooks = self._generate_hooks(topic, keywords, first_sentence)
        main_title = hooks[0]

        # 4. Description SEO
        kw_str = ", ".join(keywords[:4])
        cta = "Abonne-toi pour ne rien manquer des prochains conseils !"
        desc_lines = [
            f"Dans cet extrait vidéo, découvrez les points essentiels sur : {first_sentence}.",
            "",
            f"📌 Thématiques abordées : {topic} ({kw_str}).",
            "",
            "🔔 " + cta
        ]
        description = "\n".join(desc_lines)

        # 5. Hashtags
        hashtags = self._generate_hashtags(topic, keywords)

        return SocialMetadata(
            title=main_title,
            hooks=hooks,
            description=description,
            hashtags=hashtags,
            keywords=keywords,
            call_to_action=cta,
            detected_topic=topic
        )

    def generate_from_segments(self, segments: List[TranscriptSegment]) -> SocialMetadata:
        """Génère les métadonnées sociales à partir d'une liste de TranscriptSegment."""
        full_text = " ".join(seg.text for seg in segments)
        return self.generate_from_text(full_text)

    def export_post_txt(self, metadata: SocialMetadata, output_path: str) -> str:
        """
        Sauvegarde un fichier texte post_content.txt prêt au copier-coller
        (Titre + Description + Hashtags).
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        content = [
            "============================================================",
            "TITRE PRINCIPAL CONSEILLÉ :",
            metadata.title,
            "============================================================",
            "",
            "AUTRES IDÉES DE TITRES / HOOKS :",
            f"1. {metadata.hooks[0] if len(metadata.hooks) > 0 else ''}",
            f"2. {metadata.hooks[1] if len(metadata.hooks) > 1 else ''}",
            f"3. {metadata.hooks[2] if len(metadata.hooks) > 2 else ''}",
            "",
            "============================================================",
            "DESCRIPTION PRÊTE À COLLER :",
            "============================================================",
            metadata.description,
            "",
            "============================================================",
            "HASHTAGS :",
            "============================================================",
            " ".join(metadata.hashtags),
            ""
        ]

        out.write_text("\n".join(content), encoding="utf-8")
        return str(out.resolve())

    def export_json(self, metadata: SocialMetadata, output_path: str) -> str:
        """Sauvegarde les métadonnées au format JSON structuré."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
        return str(out.resolve())
