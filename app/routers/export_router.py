"""
export_router.py

Endpoints d'export Excel (facture unique ou selection consolidee). Chaque
facture apporte ses propres champs extraits (extracted_fields JSONB) - la
mise en colonnes dynamique se fait dans excel_export.py.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, auth_utils
from ..database import get_db
from ..excel_export import build_invoices_excel, InvoiceExport

router = APIRouter(prefix="/admin", tags=["export"])


class ExportRequest(BaseModel):
    invoice_ids: List[int]


def _invoice_to_export(invoice: models.Invoice) -> InvoiceExport:
    """Convertit une Invoice en InvoiceExport pour le generateur Excel.
    `fields` reprend TEL QUEL ce qui a ete detecte pour CETTE facture -
    aucune normalisation vers un schema fixe."""
    ext = invoice.extracted_data  # relation one-to-one (voir models.py)
    fields = ext.extracted_fields if ext else []

    return InvoiceExport(
        filename=invoice.filename,
        client_name=invoice.owner.full_name if invoice.owner else None,
        fields=fields,
    )


@router.post("/invoices/export-excel")
def export_invoices_excel(
    payload: ExportRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    """Genere UN classeur Excel consolide pour 1 ou plusieurs factures.
    Les colonnes du fichier sont deduites dynamiquement de l'union des
    champs reellement extraits parmi les factures selectionnees."""
    if not payload.invoice_ids:
        raise HTTPException(status_code=400, detail="Aucune facture selectionnee.")

    invoices = (
        db.query(models.Invoice)
        .filter(models.Invoice.id.in_(payload.invoice_ids))
        .all()
    )
    if not invoices:
        raise HTTPException(status_code=404, detail="Aucune facture trouvee pour cette selection.")

    order_map = {iid: idx for idx, iid in enumerate(payload.invoice_ids)}
    invoices.sort(key=lambda inv: order_map.get(inv.id, 0))

    exports = [_invoice_to_export(inv) for inv in invoices]
    buffer = build_invoices_excel(exports)

    filename = (
        "facture_export.xlsx" if len(invoices) == 1
        else f"export_{len(invoices)}_factures.xlsx"
    )

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )