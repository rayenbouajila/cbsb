"""
app/schemas_extraction.py

Schemas Pydantic v2 pour le module d'analyse intelligente des factures.
Fichier separe de `schemas.py` pour ne pas alourdir/risquer de casser les
schemas existants - a importer depuis les routeurs comme :

    from .. import schemas_extraction as ext_schemas

(ou fusionner son contenu dans schemas.py si tu preferes tout centraliser -
aucune dependance circulaire, ca fonctionne dans les deux cas)
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ExtractedFieldOut(BaseModel):
    key: str
    label: str
    value: object
    value_type: str


class ExtractedInvoiceOut(BaseModel):
    """Une ligne de la table 'Factures analysees' du dashboard admin."""
    model_config = ConfigDict(from_attributes=True)

    id: int  # id de InvoiceExtractedData
    invoice_id: int
    filename: Optional[str] = None
    client_name: Optional[str] = None
    company_name: Optional[str] = None

    numero_facture: Optional[str] = None
    fournisseur: Optional[str] = None
    date_facture: Optional[str] = None
    devise: Optional[str] = None
    montant_ht: Optional[float] = None
    taux_tva: Optional[float] = None
    montant_tva: Optional[float] = None
    timbre_fiscal: Optional[float] = None
    montant_ttc: Optional[float] = None

    extraction_status: str
    extraction_confidence: Optional[float] = None
    extraction_engine: Optional[str] = None
    extraction_error: Optional[str] = None

    validation_status: Optional[str] = None
    validation_message: Optional[str] = None
    manually_edited: bool = False

    extracted_fields: List[ExtractedFieldOut] = []

    updated_at: datetime


class AnalyzeRequest(BaseModel):
    invoice_ids: List[int]
    force: bool = False  # si True, relance meme les factures deja analysees avec succes


class ReanalyzeRequest(BaseModel):
    invoice_id: int


class AnalyzeResultItem(BaseModel):
    invoice_id: int
    status: str  # "success" | "failed" | "manual_review" | "skipped"
    message: Optional[str] = None


class AnalyzeResponse(BaseModel):
    results: List[AnalyzeResultItem]


class ExtractedInvoiceUpdate(BaseModel):
    """Body du PUT /admin/invoices/{id} - tous les champs optionnels,
    seuls ceux fournis sont mis a jour. `id` ici = invoice_id (le PDF), pas
    l'id de la ligne InvoiceExtractedData - plus intuitif cote frontend qui
    manipule deja des invoice_id partout ailleurs."""
    numero_facture: Optional[str] = None
    fournisseur: Optional[str] = None
    date_facture: Optional[str] = None
    devise: Optional[str] = None
    montant_ht: Optional[float] = None
    taux_tva: Optional[float] = None
    montant_tva: Optional[float] = None
    timbre_fiscal: Optional[float] = None
    montant_ttc: Optional[float] = None
