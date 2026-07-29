"""
app/crud/invoice_extraction_crud.py

Toutes les operations DB liees a `InvoiceExtractedData`, isolees du routeur
et du service d'analyse (pas de logique metier ici, uniquement des requetes).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .. import models


def get_by_invoice_id(db: Session, invoice_id: int) -> Optional[models.InvoiceExtractedData]:
    return (
        db.query(models.InvoiceExtractedData)
        .filter(models.InvoiceExtractedData.invoice_id == invoice_id)
        .first()
    )


def get_or_create(db: Session, invoice_id: int) -> models.InvoiceExtractedData:
    existing = get_by_invoice_id(db, invoice_id)
    if existing:
        return existing
    row = models.InvoiceExtractedData(invoice_id=invoice_id)
    db.add(row)
    db.flush()
    return row


def list_extracted(
    db: Session,
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    validation_status: Optional[str] = None,
):
    query = (
        db.query(models.InvoiceExtractedData)
        .join(models.Invoice, models.Invoice.id == models.InvoiceExtractedData.invoice_id)
    )
    if client_id:
        query = query.filter(models.Invoice.owner_id == client_id)
    if status:
        query = query.filter(models.InvoiceExtractedData.extraction_status == status)
    if validation_status:
        query = query.filter(models.InvoiceExtractedData.validation_status == validation_status)
    return query.order_by(models.InvoiceExtractedData.updated_at.desc()).all()
