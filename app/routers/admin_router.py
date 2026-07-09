from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth_utils
from ..database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/pending-users", response_model=List[schemas.UserOut])
def pending_users(db: Session = Depends(get_db), _: models.User = Depends(auth_utils.require_admin)):
    return db.query(models.User).filter(models.User.status == models.StatusEnum.pending).all()


@router.post("/approve-user/{user_id}")
def approve_user(user_id: int, db: Session = Depends(get_db), _: models.User = Depends(auth_utils.require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    user.status = models.StatusEnum.active
    db.commit()

    activation_token = auth_utils.create_activation_token(user.id)
    activation_link = f"http://localhost:5500/activate.html?token={activation_token}"

    # TODO : remplacer ce print par un envoi email reel (smtplib, Resend, Mailjet...)
    print(f"[EMAIL] Lien d'activation pour {user.email} : {activation_link}")

    return {"detail": "Compte valide", "activation_link": activation_link}


@router.post("/reject-user/{user_id}")
def reject_user(user_id: int, db: Session = Depends(get_db), _: models.User = Depends(auth_utils.require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    user.status = models.StatusEnum.rejected
    db.commit()
    return {"detail": "Compte rejete"}
@router.get("/contact-messages", response_model=list[schemas.ContactMessageOut])
async def get_contact_messages(db: Session = Depends(get_db), admin=Depends(auth_utils.require_admin)):
    return db.query(models.ContactMessage).order_by(models.ContactMessage.created_at.desc()).all()

@router.delete("/contact-messages/{message_id}")
async def delete_contact_message(message_id: int, db: Session = Depends(get_db), admin=Depends(auth_utils.require_admin)):
    msg = db.query(models.ContactMessage).filter(models.ContactMessage.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message introuvable.")
    db.delete(msg)
    db.commit()
    return {"status": "deleted"}
from pathlib import Path
from fastapi.responses import FileResponse

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "storage" / "invoices"


@router.get("/invoices", response_model=list[schemas.InvoiceAdminOut])
def admin_list_invoices(db: Session = Depends(get_db), admin=Depends(auth_utils.require_admin)):
    invoices = db.query(models.Invoice).order_by(models.Invoice.uploaded_at.desc()).all()
    return [
        schemas.InvoiceAdminOut(
            id=inv.id,
            filename=inv.filename,
            uploaded_at=inv.uploaded_at,
            client_name=inv.owner.full_name if inv.owner else None,
            company_name=inv.owner.company_name if inv.owner else None,
        )
        for inv in invoices
    ]


@router.get("/invoices/{invoice_id}/download")
def admin_download_invoice(invoice_id: int, db: Session = Depends(get_db), admin=Depends(auth_utils.require_admin)):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture introuvable")

    file_path = UPLOAD_DIR / invoice.stored_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le serveur")

    return FileResponse(path=file_path, media_type="application/pdf", filename=invoice.filename)


@router.delete("/invoices/{invoice_id}")
def admin_delete_invoice(invoice_id: int, db: Session = Depends(get_db), admin=Depends(auth_utils.require_admin)):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture introuvable")

    file_path = UPLOAD_DIR / invoice.stored_filename
    if file_path.exists():
        file_path.unlink()

    db.delete(invoice)
    db.commit()
    return {"status": "deleted"}