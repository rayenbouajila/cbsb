"""
app/ocr/text_layer.py

Detection automatique du type de PDF (texte natif vs. scanne/image) et
extraction du texte natif quand il est disponible, via PyMuPDF (fitz).

Interface volontairement minimale : une seule fonction publique,
`extract_text_layer`, qui ne leve jamais d'exception (elle catch tout et
retourne un resultat "vide" en cas d'echec, a charge de l'appelant de
basculer vers l'OCR).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Seuil heuristique : nombre moyen de caracteres "utiles" (alphanumeriques)
# par page en dessous duquel on considere que le PDF n'a pas de couche
# texte exploitable (donc probablement un scan/image). Ajustable si besoin.
MIN_ALNUM_CHARS_PER_PAGE = 25


@dataclass
class TextLayerResult:
    has_sufficient_text: bool
    text: str
    page_count: int
    alnum_char_count: int


def extract_text_layer(pdf_bytes: bytes) -> TextLayerResult:
    """Ouvre le PDF et tente d'en extraire le texte natif (couche texte).

    Ne fait AUCUN OCR ici - c'est uniquement la premiere etape du pipeline
    (cf. `services/invoice_analysis_service.py`) qui decide, a partir du
    resultat, s'il faut basculer vers PaddleOCR.
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Impossible d'ouvrir le PDF avec PyMuPDF: %s", exc)
        return TextLayerResult(has_sufficient_text=False, text="", page_count=0, alnum_char_count=0)

    try:
        page_count = doc.page_count
        chunks: list[str] = []
        for page in doc:
            chunks.append(page.get_text("text") or "")
        full_text = "\n".join(chunks)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Erreur lors de l'extraction du texte natif: %s", exc)
        return TextLayerResult(has_sufficient_text=False, text="", page_count=0, alnum_char_count=0)
    finally:
        doc.close()

    alnum_count = sum(1 for c in full_text if c.isalnum())
    threshold = MIN_ALNUM_CHARS_PER_PAGE * max(page_count, 1)
    has_sufficient_text = alnum_count >= threshold

    return TextLayerResult(
        has_sufficient_text=has_sufficient_text,
        text=full_text,
        page_count=page_count,
        alnum_char_count=alnum_count,
    )
