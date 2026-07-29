"""
app/services/invoice_analysis_service.py

Orchestrateur du pipeline "analyse intelligente" declenche par l'admin :

    ouvrir le PDF
    si texte natif suffisant -> l'utiliser directement (PyMuPDF)
    sinon -> PaddleOCR
    -> extraction LLM (Claude) sur le texte obtenu
    -> validation HT + TVA + Timbre ~= TTC
    -> persistance dans InvoiceExtractedData

Ne contient aucune route HTTP ni aucune requete SQL directe (delegue au
module crud) - uniquement de la logique metier, pour rester testable et
reutilisable (ex: appelable depuis une tache de fond plus tard).
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from .. import models
from ..crud import invoice_extraction_crud
from ..llm.extractor import extract_with_llm
from ..ocr.paddle_ocr_engine import run_paddle_ocr
from ..ocr.text_layer import extract_text_layer
from .validation_service import validate_totals

logger = logging.getLogger(__name__)

# Meme repertoire de stockage que invoices_router.py (app/storage/invoices)
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "storage" / "invoices"


class InvoiceFileNotFoundError(Exception):
    pass


def _read_invoice_bytes(invoice: models.Invoice) -> bytes:
    file_path = UPLOAD_DIR / invoice.stored_filename
    if not file_path.exists():
        raise InvoiceFileNotFoundError(f"Fichier introuvable sur le serveur : {invoice.stored_filename}")
    return file_path.read_bytes()


def analyze_invoice(invoice: models.Invoice, db: Session) -> models.InvoiceExtractedData:
    """Execute le pipeline complet pour UNE facture et persiste le resultat.
    Cree la ligne InvoiceExtractedData si elle n'existe pas encore, sinon la
    met a jour (comportement "reanalyser" et "analyser" identique cote
    service - la distinction se fait au niveau du routeur, qui decide si on
    doit appeler cette fonction ou non selon l'etat courant)."""
    row = invoice_extraction_crud.get_or_create(db, invoice.id)
    row.extraction_status = models.ExtractionStatusEnum.processing
    db.flush()

    try:
        pdf_bytes = _read_invoice_bytes(invoice)
    except InvoiceFileNotFoundError as exc:
        row.extraction_status = models.ExtractionStatusEnum.failed
        row.extraction_error = str(exc)
        db.commit()
        return row

    text_layer = extract_text_layer(pdf_bytes)
    if text_layer.has_sufficient_text:
        source_text = text_layer.text
        text_source = "pdf_text_layer"
    else:
        logger.info("Invoice %s : pas de couche texte suffisante, bascule vers PaddleOCR", invoice.id)
        ocr_result = run_paddle_ocr(pdf_bytes)
        if ocr_result.error:
            row.extraction_status = models.ExtractionStatusEnum.failed
            row.extraction_error = f"OCR echoue : {ocr_result.error}"
            db.commit()
            return row
        source_text = ocr_result.text
        text_source = "paddleocr"

    extraction = extract_with_llm(source_text)

    row.numero_facture = extraction.get("numero_facture")
    row.date_facture = extraction.get("date_facture")
    row.fournisseur = extraction.get("fournisseur")
    row.montant_ht = extraction.get("montant_ht")
    row.taux_tva = extraction.get("taux_tva")
    row.montant_tva = extraction.get("montant_tva")
    row.montant_ttc = extraction.get("montant_ttc")
    row.devise = extraction.get("devise")
    row.timbre_fiscal = extraction.get("timbre_fiscal")

    row.extraction_status = extraction.status
    row.extraction_confidence = extraction.confidence
    row.extraction_engine = f"{text_source}+{extraction.engine}"
    row.raw_extracted_text = extraction.raw_text
    row.extraction_error = extraction.error
    row.extracted_fields = extraction.to_json()
    row.manually_edited = False

    validation = validate_totals(
        montant_ht=row.montant_ht,
        montant_tva=row.montant_tva,
        timbre_fiscal=row.timbre_fiscal,
        montant_ttc=row.montant_ttc,
    )
    row.validation_status = validation.status
    row.validation_message = validation.message

    db.commit()
    db.refresh(row)
    return row
