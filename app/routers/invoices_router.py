import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas, auth_utils
from ..database import get_db

router = APIRouter(prefix="/client", tags=["invoices"])

# app/routers/invoices_router.py -> parent.parent = app/  -> app/storage/invoices
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "storage" / "invoices"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_SIZE = 10 * 1024 * 1024  # 10 Mo
ALLOWED_CONTENT_TYPES = {"application/pdf"}


def _invoice_or_404(invoice_id: int, db: Session) -> models.Invoice:
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return invoice


def _validate_doc_type(doc_type: str) -> models.DocumentTypeEnum:
    try:
        return models.DocumentTypeEnum(doc_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Type de document invalide")


# ---------- Invoices (client) ----------

@router.get("/invoices", response_model=List[schemas.InvoiceOut])
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


@router.post("/invoices", response_model=schemas.InvoiceOut)
async def upload_invoice(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    request_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    doc_type_enum = _validate_doc_type(doc_type)

    if file.content_type not in ALLOWED_CONTENT_TYPES and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont acceptes.")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Le fichier depasse la taille maximale (10 Mo).")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Le fichier est vide.")

    doc_request = None
    if request_id is not None:
        doc_request = (
            db.query(models.DocumentRequest)
            .filter(
                models.DocumentRequest.id == request_id,
                models.DocumentRequest.client_id == current_user.id,
            )
            .first()
        )
        if not doc_request:
            raise HTTPException(status_code=404, detail="Demande de document introuvable")

    stored_filename = f"{uuid.uuid4().hex}.pdf"
    dest_path = UPLOAD_DIR / stored_filename
    with open(dest_path, "wb") as f:
        f.write(content)

    invoice = models.Invoice(
        filename=file.filename,
        stored_filename=stored_filename,
        content_type="application/pdf",
        doc_type=doc_type_enum,
        size=len(content),
        owner_id=current_user.id,
    )
    db.add(invoice)
    db.flush()  # get invoice.id before commit

    if doc_request:
        doc_request.status = models.RequestStatusEnum.fulfilled
        doc_request.fulfilled_invoice_id = invoice.id

    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/invoices/{invoice_id}/download")
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

    return FileResponse(path=file_path, media_type="application/pdf", filename=invoice.filename)


@router.delete("/invoices/{invoice_id}")
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


# ---------- Document requests (client side) ----------

@router.get("/document-requests", response_model=List[schemas.DocumentRequestOut])
def list_my_document_requests(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    return (
        db.query(models.DocumentRequest)
        .filter(
            models.DocumentRequest.client_id == current_user.id,
            models.DocumentRequest.status == models.RequestStatusEnum.pending,
        )
        .order_by(models.DocumentRequest.created_at.desc())
        .all()
    )