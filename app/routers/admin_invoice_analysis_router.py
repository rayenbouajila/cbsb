"""
app/routers/admin_invoice_analysis_router.py

Nouvelles routes admin pour le module d'analyse intelligente des factures.
Aucune route existante n'est modifiee ; ce routeur est enregistre en plus
des routeurs deja presents (voir 05_main_py_integration.md).

Routes :
    POST /admin/invoices/analyze      - lance l'analyse (OCR + LLM) pour une liste de factures
    POST /admin/invoices/reanalyze     - force la re-analyse d'UNE facture
    GET  /admin/invoices/extracted      - liste des factures analysees (pour le tableau "Factures analysees")
    PUT  /admin/invoices/{id}            - correction manuelle des champs extraits

(L'export Excel reste dans export_router.py, deja fonctionnel - non duplique ici.)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import auth_utils, models, schemas_extraction as ext_schemas
from ..crud import invoice_extraction_crud
from ..database import get_db
from ..services.invoice_analysis_service import analyze_invoice
from ..services.validation_service import validate_totals

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["invoice-analysis"])


def _invoice_or_404(invoice_id: int, db: Session) -> models.Invoice:
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    return invoice


def _row_to_out(row: models.InvoiceExtractedData) -> ext_schemas.ExtractedInvoiceOut:
    invoice = row.invoice
    owner = invoice.owner if invoice else None
    return ext_schemas.ExtractedInvoiceOut(
        id=row.id,
        invoice_id=row.invoice_id,
        filename=invoice.filename if invoice else None,
        client_name=owner.full_name if owner else None,
        company_name=owner.company_name if owner else None,
        numero_facture=row.numero_facture,
        fournisseur=row.fournisseur,
        date_facture=row.date_facture.isoformat() if row.date_facture else None,
        devise=row.devise,
        montant_ht=float(row.montant_ht) if row.montant_ht is not None else None,
        taux_tva=float(row.taux_tva) if row.taux_tva is not None else None,
        montant_tva=float(row.montant_tva) if row.montant_tva is not None else None,
        timbre_fiscal=float(row.timbre_fiscal) if row.timbre_fiscal is not None else None,
        montant_ttc=float(row.montant_ttc) if row.montant_ttc is not None else None,
        extraction_status=row.extraction_status.value if hasattr(row.extraction_status, "value") else row.extraction_status,
        extraction_confidence=float(row.extraction_confidence) if row.extraction_confidence is not None else None,
        extraction_engine=row.extraction_engine,
        extraction_error=row.extraction_error,
        validation_status=row.validation_status,
        validation_message=row.validation_message,
        manually_edited=row.manually_edited,
        extracted_fields=row.extracted_fields or [],
        updated_at=row.updated_at,
    )


@router.post("/invoices/analyze", response_model=ext_schemas.AnalyzeResponse)
def admin_analyze_invoices(
    payload: ext_schemas.AnalyzeRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    """Lance le pipeline OCR + LLM pour chaque facture de la liste. Par
    defaut, saute les factures deja analysees avec succes (status='success')
    pour eviter de re-consommer des appels LLM inutilement ; `force=true`
    force la re-analyse de toutes les factures listees."""
    if not payload.invoice_ids:
        raise HTTPException(status_code=400, detail="Aucune facture selectionnee.")

    results: List[ext_schemas.AnalyzeResultItem] = []

    for invoice_id in payload.invoice_ids:
        invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
        if not invoice:
            results.append(ext_schemas.AnalyzeResultItem(invoice_id=invoice_id, status="failed", message="Facture introuvable"))
            continue

        existing = invoice_extraction_crud.get_by_invoice_id(db, invoice_id)
        if existing and existing.extraction_status == models.ExtractionStatusEnum.success and not payload.force:
            results.append(ext_schemas.AnalyzeResultItem(invoice_id=invoice_id, status="skipped", message="Deja analysee avec succes"))
            continue

        try:
            row = analyze_invoice(invoice, db)
            status_value = row.extraction_status.value if hasattr(row.extraction_status, "value") else row.extraction_status
            results.append(ext_schemas.AnalyzeResultItem(invoice_id=invoice_id, status=status_value, message=row.extraction_error))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Echec analyse invoice_id=%s", invoice_id)
            db.rollback()
            results.append(ext_schemas.AnalyzeResultItem(invoice_id=invoice_id, status="failed", message=str(exc)))

    return ext_schemas.AnalyzeResponse(results=results)


@router.post("/invoices/reanalyze", response_model=ext_schemas.AnalyzeResultItem)
def admin_reanalyze_invoice(
    payload: ext_schemas.ReanalyzeRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    """Force la re-analyse d'UNE facture (bouton 'Reanalyser' du dashboard),
    quel que soit son statut actuel."""
    invoice = _invoice_or_404(payload.invoice_id, db)
    try:
        row = analyze_invoice(invoice, db)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Echec reanalyse invoice_id=%s", payload.invoice_id)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Echec de la reanalyse : {exc}")

    status_value = row.extraction_status.value if hasattr(row.extraction_status, "value") else row.extraction_status
    return ext_schemas.AnalyzeResultItem(invoice_id=payload.invoice_id, status=status_value, message=row.extraction_error)


@router.get("/invoices/extracted", response_model=List[ext_schemas.ExtractedInvoiceOut])
def admin_list_extracted_invoices(
    client_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="pending|processing|success|failed|manual_review"),
    validation_status: Optional[str] = Query(None, description="ok|mismatch|unknown"),
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    rows = invoice_extraction_crud.list_extracted(
        db, client_id=client_id, status=status, validation_status=validation_status
    )
    return [_row_to_out(row) for row in rows]


@router.put("/invoices/{invoice_id}", response_model=ext_schemas.ExtractedInvoiceOut)
def admin_update_extracted_invoice(
    invoice_id: int,
    payload: ext_schemas.ExtractedInvoiceUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    """Correction manuelle des champs extraits par l'admin (bouton
    'Modifier les champs'). Ne touche PAS a extracted_fields (la liste JSON
    brute issue du moteur d'extraction) - uniquement aux colonnes fixes,
    pour garder une trace de ce que le moteur a vraiment detecte vs. ce que
    l'admin a corrige. Recalcule la validation apres modification."""
    _invoice_or_404(invoice_id, db)
    row = invoice_extraction_crud.get_by_invoice_id(db, invoice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Aucune extraction existante pour cette facture. Lancez d'abord une analyse.")

    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        if field_name == "date_facture" and value is not None:
            from datetime import date as date_cls
            value = date_cls.fromisoformat(value)
        setattr(row, field_name, value)

    row.manually_edited = True

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
    return _row_to_out(row)
