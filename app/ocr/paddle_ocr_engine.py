"""
app/ocr/paddle_ocr_engine.py

OCR des PDF scannes (sans couche texte) via PaddleOCR. Chaque page est
rendue en image (PyMuPDF) puis passee a PaddleOCR ; le texte reconnu de
toutes les pages est concatene, dans l'ordre, pour etre ensuite envoye au
meme pipeline d'extraction LLM que le texte natif.

Le moteur PaddleOCR est instancie UNE SEULE FOIS au niveau module (variable
globale paresseuse) : son chargement est couteux (poids du modele), on ne
veut pas le refaire a chaque facture.

Dependances : paddleocr, paddlepaddle, pymupdf
    pip install paddlepaddle paddleocr pymupdf --break-system-packages
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Resolution de rendu des pages avant OCR. 200-300 DPI est un bon compromis
# vitesse/qualite pour des factures scannees standard.
RENDER_DPI = 250

_ocr_engine = None  # instance PaddleOCR, chargee a la demande (lazy)


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR  # import local : evite le cout au demarrage de l'app

        logger.info("Chargement du moteur PaddleOCR (premiere utilisation)...")
        _ocr_engine = PaddleOCR(use_angle_cls=True, lang="fr", show_log=False)
    return _ocr_engine


@dataclass
class OcrResult:
    text: str
    page_count: int
    error: Optional[str] = None


def run_paddle_ocr(pdf_bytes: bytes) -> OcrResult:
    """Rend chaque page du PDF en image puis extrait le texte via PaddleOCR.
    Ne leve jamais d'exception : retourne un OcrResult avec `error` renseigne
    en cas d'echec, texte vide."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Impossible d'ouvrir le PDF pour rendu OCR")
        return OcrResult(text="", page_count=0, error=f"Ouverture PDF impossible: {exc}")

    try:
        engine = _get_ocr_engine()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Impossible de charger PaddleOCR")
        doc.close()
        return OcrResult(text="", page_count=doc.page_count, error=f"Chargement PaddleOCR impossible: {exc}")

    page_texts: list[str] = []
    zoom = RENDER_DPI / 72  # PyMuPDF travaille en points (72 dpi de base)
    matrix = fitz.Matrix(zoom, zoom)

    try:
        for page_index in range(doc.page_count):
            page = doc[page_index]
            pix = page.get_pixmap(matrix=matrix)
            image_bytes = pix.tobytes("png")

            try:
                ocr_output = engine.ocr(image_bytes, cls=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Echec OCR sur la page %s: %s", page_index + 1, exc)
                continue

            lines = _flatten_paddle_output(ocr_output)
            page_texts.append("\n".join(lines))
    finally:
        doc.close()

    full_text = "\n\n".join(page_texts)
    return OcrResult(text=full_text, page_count=len(page_texts))


def _flatten_paddle_output(ocr_output) -> list[str]:
    """PaddleOCR retourne une structure imbriquee
    [[ [box, (text, score)], ... ]] (une liste par page/image). On aplati
    en une simple liste de lignes de texte, dans l'ordre de detection
    (top-to-bottom approximatif fourni par Paddle)."""
    lines: list[str] = []
    if not ocr_output:
        return lines
    for page_result in ocr_output:
        if not page_result:
            continue
        for detection in page_result:
            try:
                text = detection[1][0]
            except (IndexError, TypeError):
                continue
            if text:
                lines.append(text)
    return lines
