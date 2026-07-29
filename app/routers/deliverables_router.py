import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas, auth_utils
from ..database import get_db

router = APIRouter(tags=["deliverables"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "storage" / "deliverables"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_SIZE = 10 * 1024 * 1024  # 10 Mo
ALLOWED_CONTENT_TYPES = {"application/pdf"}


def _validate_doc_type(doc_type: str) -> models.DeliverableTypeEnum:
    try:
        return models.DeliverableTypeEnum(doc_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Type de document invalide")


# ---------- Admin: send deliverables to clients ----------

@router.post("/admin/deliverables", response_model=schemas.DeliverableAdminOut)
async def admin_upload_deliverable(
    file: UploadFile = File(...),
    client_id: int = Form(...),
    doc_type: str = Form(...),
    note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    client = db.query(models.User).filter(
        models.User.id == client_id,
        models.User.role == models.RoleEnum.client,
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable")

    doc_type_enum = _validate_doc_type(doc_type)

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

    deliverable = models.Deliverable(
        filename=file.filename,
        stored_filename=stored_filename,
        content_type="application/pdf",
        doc_type=doc_type_enum,
        note=note,
        size=len(content),
        client_id=client_id,
    )
    db.add(deliverable)
    db.commit()
    db.refresh(deliverable)

    return schemas.DeliverableAdminOut(
        id=deliverable.id,
        filename=deliverable.filename,
        doc_type=deliverable.doc_type,
        note=deliverable.note,
        uploaded_at=deliverable.uploaded_at,
        client_name=client.full_name,
        company_name=client.company_name,
    )


@router.get("/admin/deliverables", response_model=List[schemas.DeliverableAdminOut])
def admin_list_deliverables(
    client_id: Optional[int] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    query = db.query(models.Deliverable)
    if client_id:
        query = query.filter(models.Deliverable.client_id == client_id)
    if doc_type:
        query = query.filter(models.Deliverable.doc_type == _validate_doc_type(doc_type))

    items = query.order_by(models.Deliverable.uploaded_at.desc()).all()
    return [
        schemas.DeliverableAdminOut(
            id=d.id,
            filename=d.filename,
            doc_type=d.doc_type,
            note=d.note,
            uploaded_at=d.uploaded_at,
            client_name=d.client.full_name if d.client else None,
            company_name=d.client.company_name if d.client else None,
        )
        for d in items
    ]


@router.get("/admin/deliverables/{deliverable_id}/download")
def admin_download_deliverable(
    deliverable_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    deliverable = db.query(models.Deliverable).filter(models.Deliverable.id == deliverable_id).first()
    if not deliverable:
        raise HTTPException(status_code=404, detail="Document introuvable")

    file_path = UPLOAD_DIR / deliverable.stored_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le serveur")

    return FileResponse(path=file_path, media_type="application/pdf", filename=deliverable.filename)


@router.delete("/admin/deliverables/{deliverable_id}")
def admin_delete_deliverable(
    deliverable_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    deliverable = db.query(models.Deliverable).filter(models.Deliverable.id == deliverable_id).first()
    if not deliverable:
        raise HTTPException(status_code=404, detail="Document introuvable")

    file_path = UPLOAD_DIR / deliverable.stored_filename
    if file_path.exists():
        file_path.unlink()

    db.delete(deliverable)
    db.commit()
    return {"status": "deleted"}


# ---------- Client: view deliverables received ----------

@router.get("/client/deliverables", response_model=List[schemas.DeliverableOut])
def list_my_deliverables(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    return (
        db.query(models.Deliverable)
        .filter(models.Deliverable.client_id == current_user.id)
        .order_by(models.Deliverable.uploaded_at.desc())
        .all()
    )


@router.get("/client/deliverables/{deliverable_id}/download")
def download_my_deliverable(
    deliverable_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    deliverable = db.query(models.Deliverable).filter(models.Deliverable.id == deliverable_id).first()
    if not deliverable:
        raise HTTPException(status_code=404, detail="Document introuvable")
    if deliverable.client_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acces refuse")

    file_path = UPLOAD_DIR / deliverable.stored_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le serveur")

    return FileResponse(path=file_path, media_type="application/pdf", filename=deliverable.filename)