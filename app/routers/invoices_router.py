import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas, auth_utils
from ..database import get_db

router = APIRouter(prefix="/client/invoices", tags=["invoices"])

# app/routers/invoices_router.py -> parent.parent = app/  -> app/storage/invoices
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "storage" / "invoices"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_SIZE = 10 * 1024 * 1024  # 10 Mo
ALLOWED_CONTENT_TYPES = {"application/pdf"}


def _invoice_or_404(invoice_id: int, db: Session) -> models.Invoice:
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    return invoice


@router.get("", response_model=List[schemas.InvoiceOut])
def list_my_invoices(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    return (
        db.query(models.Invoice)
        .filter(models.Invoice.owner_id == current_user.id)
        .order_by(models.Invoice.uploaded_at.desc())
        .all()
    )


@router.post("", response_model=schemas.InvoiceOut)
async def upload_invoice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont acceptes.")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Le fichier depasse la taille maximale (10 Mo).")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Le fichier est vide.")

    stored_filename = f"{uuid.uuid4().hex}.pdf"
    dest_path = UPLOAD_DIR / stored_filename
    with open(dest_path, "wb") as f:
        f.write(content)

    invoice = models.Invoice(
        filename=file.filename,
        stored_filename=stored_filename,
        content_type="application/pdf",
        size=len(content),
        owner_id=current_user.id,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/{invoice_id}/download")
def download_my_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    invoice = _invoice_or_404(invoice_id, db)
    if invoice.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acces refuse")

    file_path = UPLOAD_DIR / invoice.stored_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le serveur")

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=invoice.filename,
    )


@router.delete("/{invoice_id}")
def delete_my_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    invoice = _invoice_or_404(invoice_id, db)
    if invoice.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acces refuse")

    file_path = UPLOAD_DIR / invoice.stored_filename
    if file_path.exists():
        file_path.unlink()

    db.delete(invoice)
    db.commit()
    return {"status": "deleted"}