"""
invoice_extraction.py

Extraction heuristique et DYNAMIQUE des donnees d'une facture PDF.

Contrairement a une extraction "a colonnes fixes" (numero, date, fournisseur...
toujours les 8 memes cases), ce module retourne une LISTE de champs
effectivement detectes dans le PDF. Deux factures peuvent produire des listes
completement differentes : l'une aura "Taux TVA", l'autre non ; l'une aura
un champ "Reference commande" que l'autre n'a pas. C'est voulu : chaque
facture "deduit" ses propres cases.

LIMITES CONNUES (a lire avant mise en production) :
Implementation texte + regex. Fonctionne sur des PDF texte (pas des scans).
Pour une extraction fiable en production, remplacer `extract_invoice_data()`
par un moteur specialise (Mindee API, Azure Form Recognizer, Google Document AI,
ou un appel LLM avec sortie JSON structuree) - l'interface de sortie
(liste de ExtractedField) reste la meme, donc rien d'autre ne change.
"""

import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import pdfplumber

# Libelles d'affichage fixes pour les champs "connus" (garde une coherence
# visuelle dans Excel meme si le texte source varie legerement d'un PDF a l'autre)
CANONICAL_LABELS = {
    "numero_facture": "N° Facture",
    "date_facture": "Date",
    "fournisseur": "Fournisseur",
    "categorie": "Catégorie",
    "montant_ht": "Montant HT",
    "taux_tva": "Taux TVA (%)",
    "montant_tva": "Montant TVA",
    "montant_ttc": "Montant TTC",
}

# Ordre de priorite d'affichage pour les champs connus (les champs "extra"
# detectes en plus viennent apres, dans l'ordre ou ils apparaissent au PDF)
CANONICAL_ORDER = list(CANONICAL_LABELS.keys())


@dataclass
class ExtractedField:
    key: str            # identifiant stable (slug) - "montant_ht", "reference_commande"...
    label: str           # libelle affiche dans Excel
    value: object          # str | Decimal | date
    value_type: str = "text"  # "text" | "number" | "date"


@dataclass
class ExtractionResult:
    fields: list[ExtractedField] = field(default_factory=list)
    status: str = "failed"          # success | failed | manual_review
    confidence: float = 0.0
    engine: str = "regex_v2_dynamic"
    raw_text: str = ""
    error: Optional[str] = None

    def get(self, key: str):
        return next((f.value for f in self.fields if f.key == key), None)

    def to_json(self) -> list[dict]:
        """Serialise pour stockage direct dans la colonne JSONB `extracted_fields`."""
        out = []
        for f in self.fields:
            value = f.value
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif isinstance(value, Decimal):
                value = float(value)
            out.append({"key": f.key, "label": f.label, "value": value, "value_type": f.value_type})
        return out


# ---------- Regex patterns pour les champs "connus" (FR, formats courants) ----------

RE_NUMERO = re.compile(
    r"(?:facture|invoice|n°|num[eé]ro)\s*[:n°]*\s*([A-Z0-9][A-Z0-9\-\/\._]{2,30})",
    re.IGNORECASE,
)
RE_DATE = re.compile(
    r"(?:date|du|le)\s*[:]?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
    re.IGNORECASE,
)
RE_MONTANT_HT = re.compile(
    r"(?:total\s*ht|montant\s*ht|sous[\s\-]?total)\s*[:]?\s*([\d\s]+[,\.]\d{2})\s*(?:€|dt|tnd|\$)?",
    re.IGNORECASE,
)
RE_MONTANT_TTC = re.compile(
    r"(?:total\s*ttc|montant\s*ttc|net\s*[aà]\s*payer|total\s*[aà]\s*payer|amount\s*due)\s*[:]?\s*([\d\s]+[,\.]\d{2})\s*(?:€|dt|tnd|\$)?",
    re.IGNORECASE,
)
RE_TVA_MONTANT = re.compile(
    r"(?:tva|t\.v\.a\.?|vat)\s*(?:\(?\d{1,2}[,\.]?\d{0,2}\s*%\)?)?\s*[:]?\s*([\d\s]+[,\.]\d{2})\s*(?:€|dt|tnd|\$)?",
    re.IGNORECASE,
)
RE_TAUX_TVA = re.compile(r"(?:tva|vat)\s*(?:\()?\s*(\d{1,2}(?:[,\.]\d{1,2})?)\s*%", re.IGNORECASE)
RE_FOURNISSEUR_LINE = re.compile(r"^([A-Z][A-Za-z0-9 &\-\.]{2,60})$")

# Detection generique "Label : valeur" pour capter des champs NON prevus
# a l'avance (ex: "Reference commande: PO-55123", "Mode de paiement: Virement")
RE_GENERIC_LABEL_VALUE = re.compile(
    r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 '\-]{2,40})\s*[:]\s*(.{1,80})$"
)

# Cles connues a ignorer dans le fallback generique (deja captees par les
# regex specifiques ci-dessus, pour eviter les doublons)
_KNOWN_LABEL_HINTS = ("facture", "date", "total ht", "total ttc", "tva", "vat", "montant")


def _slugify(label: str) -> str:
    slug = label.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")[:40] or "champ"


def _parse_decimal(raw: Optional[str]) -> Optional[Decimal]:
    if not raw:
        return None
    cleaned = raw.replace(" ", "").replace(",", ".")
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_date(raw: Optional[str]):
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _guess_fournisseur(lines: list[str]) -> Optional[str]:
    for line in lines[:8]:
        line = line.strip()
        if RE_FOURNISSEUR_LINE.match(line) and len(line.split()) <= 6:
            return line
    return None


def extract_invoice_data(pdf_bytes: bytes) -> ExtractionResult:
    """Point d'entree principal. Retourne une liste dynamique de champs
    detectes - propre a CE PDF. Ne leve jamais d'exception."""
    result = ExtractionResult()

    try:
        text_chunks = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text_chunks.append(page.extract_text() or "")
        full_text = "\n".join(text_chunks)
        result.raw_text = full_text[:10000]

        if not full_text.strip():
            result.error = "Aucun texte extractible (PDF probablement scanne / image)."
            result.status = "manual_review"
            return result

        lines = [l for l in full_text.splitlines() if l.strip()]
        found_keys: set[str] = set()
        consumed_lines: set[int] = set()

        def add_field(key: str, value, value_type: str, label: Optional[str] = None):
            if value is None or value == "":
                return
            result.fields.append(ExtractedField(
                key=key,
                label=label or CANONICAL_LABELS.get(key, key.replace("_", " ").title()),
                value=value,
                value_type=value_type,
            ))
            found_keys.add(key)

        def mark_consumed(matched_text: str):
            """Marque comme 'consommee' la ligne contenant ce texte, pour que
            le fallback generique ne la re-capture pas en double."""
            for idx, line in enumerate(lines):
                if matched_text in line:
                    consumed_lines.add(idx)
                    return

        # --- Champs connus : seulement s'ils sont reellement trouves ---
        if m := RE_NUMERO.search(full_text):
            add_field("numero_facture", m.group(1).strip(), "text")
            mark_consumed(m.group(0))

        if m := RE_DATE.search(full_text):
            if d := _parse_date(m.group(1)):
                add_field("date_facture", d, "date")
                mark_consumed(m.group(0))

        if fournisseur := _guess_fournisseur(lines):
            add_field("fournisseur", fournisseur, "text")
            mark_consumed(fournisseur)

        m_ht = RE_MONTANT_HT.search(full_text)
        montant_ht = _parse_decimal(m_ht.group(1)) if m_ht else None
        if montant_ht is not None:
            add_field("montant_ht", montant_ht, "number")
            mark_consumed(m_ht.group(0))

        m_ttc = RE_MONTANT_TTC.search(full_text)
        montant_ttc = _parse_decimal(m_ttc.group(1)) if m_ttc else None
        if montant_ttc is not None:
            add_field("montant_ttc", montant_ttc, "number")
            mark_consumed(m_ttc.group(0))

        m_taux = RE_TAUX_TVA.search(full_text)
        taux_tva = _parse_decimal(m_taux.group(1)) if m_taux else None
        m_tva = RE_TVA_MONTANT.search(full_text)
        montant_tva = _parse_decimal(m_tva.group(1)) if m_tva else None
        if m_taux:
            mark_consumed(m_taux.group(0))
        if m_tva:
            mark_consumed(m_tva.group(0))

        # Reconciliation : deduit ce qui manque UNIQUEMENT si les autres sont presents
        if montant_tva is None and montant_ht is not None and montant_ttc is not None:
            montant_tva = montant_ttc - montant_ht
        if taux_tva is None and montant_ht and montant_tva is not None and montant_ht != 0:
            taux_tva = (montant_tva / montant_ht * 100).quantize(Decimal("0.01"))

        if taux_tva is not None:
            add_field("taux_tva", taux_tva, "number")
        if montant_tva is not None:
            add_field("montant_tva", montant_tva, "number")

        # --- Fallback generique : capte les champs NON prevus a l'avance ---
        # Chaque PDF peut avoir des lignes "Label: Valeur" specifiques
        # (ex: "Reference commande: PO-55123", "Devise: USD", "Mode de paiement: Virement")
        # On ignore les lignes deja "consommees" par une regex specifique ci-dessus.
        for idx, line in enumerate(lines):
            if idx in consumed_lines:
                continue
            m = RE_GENERIC_LABEL_VALUE.match(line.strip())
            if not m:
                continue
            label_raw, value_raw = m.group(1).strip(), m.group(2).strip()
            key = _slugify(label_raw)
            if key in found_keys or key in CANONICAL_ORDER:
                continue
            if len(value_raw) < 1:
                continue
            add_field(key, value_raw, "text", label=label_raw)

        # --- Score de confiance : proportion de champs "cles" trouves ---
        key_fields = ["numero_facture", "date_facture", "fournisseur", "montant_ht", "montant_ttc"]
        found_key = sum(1 for k in key_fields if k in found_keys)
        result.confidence = round((found_key / len(key_fields)) * 100, 2)

        if result.confidence >= 80:
            result.status = "success"
        elif result.confidence >= 40 or found_keys:
            result.status = "manual_review"
        else:
            result.status = "failed"
            result.error = "Trop peu de champs detectes avec confiance suffisante."

        return result

    except Exception as exc:  # noqa: BLE001
        result.status = "failed"
        result.error = f"Erreur d'extraction : {exc}"
        return result