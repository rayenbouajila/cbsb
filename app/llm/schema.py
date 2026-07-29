"""
app/llm/schema.py

Schema Pydantic v2 pour valider la sortie JSON de Claude avant tout
enregistrement en base. Tolerant par construction (tous les champs sont
optionnels) puisqu'une facture reelle n'a jamais tous les champs renseignes.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LLMInvoiceFields(BaseModel):
    numero_facture: Optional[str] = None
    date_facture: Optional[date] = None
    date_echeance: Optional[date] = None
    fournisseur: Optional[str] = None
    adresse_fournisseur: Optional[str] = None
    matricule_fiscal_fournisseur: Optional[str] = None
    client: Optional[str] = None
    devise: Optional[str] = None
    montant_ht: Optional[float] = None
    taux_tva: Optional[float] = None
    montant_tva: Optional[float] = None
    timbre_fiscal: Optional[float] = None
    montant_ttc: Optional[float] = None
    mode_paiement: Optional[str] = None
    reference_facture: Optional[str] = None
    autres_champs: dict[str, str] = Field(default_factory=dict)

    @field_validator("date_facture", "date_echeance", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value):
        # Claude peut renvoyer "" au lieu de null dans de rares cas ;
        # Pydantic v2 leve sinon une erreur de parsing de date.
        if value in ("", None):
            return None
        return value

    @field_validator(
        "montant_ht", "taux_tva", "montant_tva", "timbre_fiscal", "montant_ttc", mode="before"
    )
    @classmethod
    def _blank_number_to_none(cls, value):
        if value in ("", None):
            return None
        return value
