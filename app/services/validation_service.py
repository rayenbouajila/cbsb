"""
app/services/validation_service.py

Regle de coherence comptable : HT + TVA + Timbre fiscal ~= TTC.
Tolerance fixee a 0.5% du TTC (minimum 0.05 en valeur absolue) pour
absorber les arrondis d'affichage sur la facture source.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

RELATIVE_TOLERANCE = Decimal("0.005")  # 0.5%
MIN_ABSOLUTE_TOLERANCE = Decimal("0.05")


@dataclass
class ValidationOutcome:
    status: str  # "ok" | "mismatch" | "unknown"
    message: Optional[str] = None


def _to_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def validate_totals(
    montant_ht,
    montant_tva,
    timbre_fiscal,
    montant_ttc,
) -> ValidationOutcome:
    """Verifie HT + TVA + Timbre ~= TTC. Les champs manquants sont traites
    comme 0 SAUF si montant_ht ou montant_ttc sont absents, auquel cas la
    verification n'a pas de sens ("unknown")."""
    ht = _to_decimal(montant_ht)
    ttc = _to_decimal(montant_ttc)

    if ht is None or ttc is None:
        return ValidationOutcome(
            status="unknown",
            message="Montant HT ou TTC manquant : vérification impossible.",
        )

    tva = _to_decimal(montant_tva) or Decimal("0")
    timbre = _to_decimal(timbre_fiscal) or Decimal("0")

    computed_ttc = ht + tva + timbre
    diff = abs(computed_ttc - ttc)
    tolerance = max(MIN_ABSOLUTE_TOLERANCE, ttc.copy_abs() * RELATIVE_TOLERANCE)

    if diff <= tolerance:
        return ValidationOutcome(status="ok")

    return ValidationOutcome(
        status="mismatch",
        message=(
            f"HT ({ht}) + TVA ({tva}) + Timbre ({timbre}) = {computed_ttc}, "
            f"ecart de {diff} avec le TTC declare ({ttc})."
        ),
    )
