"""
app/llm/extractor.py

Couche d'extraction robuste basee sur un LLM (Claude). Recoit du texte brut
(peu importe qu'il vienne de PyMuPDF ou de PaddleOCR), envoie un prompt,
recupere et valide un JSON normalise, puis le convertit dans le meme format
`ExtractionResult` / `ExtractedField` que le moteur regex existant
(`invoice_extraction.py`) - ce qui permet a `excel_export.py` et au reste du
code de fonctionner sans aucune modification, quel que soit le moteur ayant
produit les champs.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import ValidationError

from ..invoice_extraction import CANONICAL_LABELS, ExtractedField, ExtractionResult
from .client import DEFAULT_MODEL, call_claude
from .prompts import RETRY_SYSTEM_SUFFIX, SYSTEM_PROMPT, build_user_prompt
from .schema import LLMInvoiceFields

logger = logging.getLogger(__name__)

# Libelles d'affichage pour les champs geres par le LLM (complementaires a
# CANONICAL_LABELS de invoice_extraction.py, qui ne couvre pas tous les
# champs demandes dans le cahier des charges)
_LLM_FIELD_LABELS = {
    **CANONICAL_LABELS,
    "date_echeance": "Date d'échéance",
    "adresse_fournisseur": "Adresse fournisseur",
    "matricule_fiscal_fournisseur": "Matricule fiscal fournisseur",
    "client": "Client",
    "devise": "Devise",
    "timbre_fiscal": "Timbre fiscal",
    "mode_paiement": "Mode de paiement",
    "reference_facture": "Référence facture",
}

# Champs consideres "cles" pour le calcul du score de confiance (coherent
# avec la logique du moteur regex existant)
_KEY_FIELDS = ["numero_facture", "date_facture", "fournisseur", "montant_ht", "montant_ttc"]


def _strip_markdown_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def _parse_llm_json(raw_response: str) -> LLMInvoiceFields:
    cleaned = _strip_markdown_fences(raw_response)
    data = json.loads(cleaned)  # peut lever json.JSONDecodeError
    return LLMInvoiceFields.model_validate(data)  # peut lever ValidationError


def _fields_to_extraction_result(
    parsed: LLMInvoiceFields, raw_text: str, raw_llm_response: str
) -> ExtractionResult:
    result = ExtractionResult(engine=f"llm:{DEFAULT_MODEL}", raw_text=raw_text[:10000])

    def add(key: str, value, value_type: str):
        if value is None or value == "":
            return
        result.fields.append(ExtractedField(
            key=key,
            label=_LLM_FIELD_LABELS.get(key, key.replace("_", " ").title()),
            value=value,
            value_type=value_type,
        ))

    add("numero_facture", parsed.numero_facture, "text")
    add("date_facture", parsed.date_facture, "date")
    add("date_echeance", parsed.date_echeance, "date")
    add("fournisseur", parsed.fournisseur, "text")
    add("adresse_fournisseur", parsed.adresse_fournisseur, "text")
    add("matricule_fiscal_fournisseur", parsed.matricule_fiscal_fournisseur, "text")
    add("client", parsed.client, "text")
    add("devise", parsed.devise, "text")
    add("montant_ht", parsed.montant_ht, "number")
    add("taux_tva", parsed.taux_tva, "number")
    add("montant_tva", parsed.montant_tva, "number")
    add("timbre_fiscal", parsed.timbre_fiscal, "number")
    add("montant_ttc", parsed.montant_ttc, "number")
    add("mode_paiement", parsed.mode_paiement, "text")
    add("reference_facture", parsed.reference_facture, "text")

    for label, value in (parsed.autres_champs or {}).items():
        key = label.strip().lower().replace(" ", "_")[:40] or "champ"
        add(key, value, "text")

    found_keys = {f.key for f in result.fields}
    found_key_count = sum(1 for k in _KEY_FIELDS if k in found_keys)
    result.confidence = round((found_key_count / len(_KEY_FIELDS)) * 100, 2)

    if result.confidence >= 80:
        result.status = "success"
    elif result.confidence >= 40 or found_keys:
        result.status = "manual_review"
    else:
        result.status = "failed"
        result.error = "Le LLM n'a pas pu extraire suffisamment de champs cles."

    return result


def extract_with_llm(invoice_text: str) -> ExtractionResult:
    """Point d'entree principal du module LLM. Ne leve jamais d'exception :
    en cas d'echec definitif (API, JSON invalide meme apres retry), retourne
    un ExtractionResult avec status='failed' et error renseigne."""
    if not invoice_text or not invoice_text.strip():
        result = ExtractionResult(engine=f"llm:{DEFAULT_MODEL}")
        result.status = "failed"
        result.error = "Aucun texte a analyser (extraction texte/OCR vide)."
        return result

    user_prompt = build_user_prompt(invoice_text)
    last_error: Optional[str] = None

    for attempt in range(2):  # 1 essai + 1 retry en cas de JSON invalide
        system_prompt = SYSTEM_PROMPT if attempt == 0 else SYSTEM_PROMPT + RETRY_SYSTEM_SUFFIX
        try:
            raw_response = call_claude(system_prompt, user_prompt)
        except Exception as exc:  # noqa: BLE001 - erreurs reseau/API Anthropic
            logger.exception("Erreur d'appel a l'API Claude (tentative %s)", attempt + 1)
            last_error = f"Erreur API Claude : {exc}"
            continue

        try:
            parsed = _parse_llm_json(raw_response)
            return _fields_to_extraction_result(parsed, invoice_text, raw_response)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Reponse LLM invalide (tentative %s): %s", attempt + 1, exc)
            last_error = f"Reponse LLM non conforme au schema JSON attendu : {exc}"
            continue

    result = ExtractionResult(engine=f"llm:{DEFAULT_MODEL}", raw_text=invoice_text[:10000])
    result.status = "failed"
    result.error = last_error or "Echec inconnu de l'extraction LLM."
    return result
