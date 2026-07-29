"""
payments_router.py

Gestion des paiements (honoraires du cabinet) par client. L'admin cree les
paiements et bascule leur statut paye/impaye. Le client consulte en lecture
seule l'etat de ses paiements.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas, auth_utils
from ..database import get_db

router = APIRouter(tags=["payments"])


def _to_admin_out(payment: models.Payment) -> schemas.PaymentAdminOut:
    return schemas.PaymentAdminOut(
        id=payment.id,
        label=payment.label,
        amount=float(payment.amount),
        due_date=payment.due_date,
        status=payment.status,
        paid_at=payment.paid_at,
        note=payment.note,
        created_at=payment.created_at,
        client_name=payment.client.full_name if payment.client else None,
        company_name=payment.client.company_name if payment.client else None,
    )


@router.post("/admin/payments", response_model=schemas.PaymentAdminOut)
def admin_create_payment(
    payload: schemas.PaymentCreate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    client = db.query(models.User).filter(
        models.User.id == payload.client_id,
        models.User.role == models.RoleEnum.client,
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable")

    payment = models.Payment(
        client_id=payload.client_id,
        label=payload.label,
        amount=payload.amount,
        due_date=payload.due_date,
        note=payload.note,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return _to_admin_out(payment)


@router.get("/admin/payments", response_model=List[schemas.PaymentAdminOut])
def admin_list_payments(
    client_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    query = db.query(models.Payment)
    if client_id:
        query = query.filter(models.Payment.client_id == client_id)
    if status:
        try:
            query = query.filter(models.Payment.status == models.PaymentStatusEnum(status))
        except ValueError:
            raise HTTPException(status_code=400, detail="Statut invalide")

    payments = query.order_by(models.Payment.due_date.asc().nullslast(), models.Payment.created_at.desc()).all()
    return [_to_admin_out(p) for p in payments]


@router.patch("/admin/payments/{payment_id}/status", response_model=schemas.PaymentAdminOut)
def admin_update_payment_status(
    payment_id: int,
    payload: schemas.PaymentStatusUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable")

    payment.status = payload.status
    payment.paid_at = datetime.utcnow() if payload.status == models.PaymentStatusEnum.paid else None
    db.commit()
    db.refresh(payment)
    return _to_admin_out(payment)


@router.delete("/admin/payments/{payment_id}")
def admin_delete_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    db.delete(payment)
    db.commit()
    return {"status": "deleted"}


@router.get("/client/payments", response_model=List[schemas.PaymentOut])
def list_my_payments(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    return (
        db.query(models.Payment)
        .filter(models.Payment.client_id == current_user.id)
        .order_by(models.Payment.due_date.asc().nullslast(), models.Payment.created_at.desc())
        .all()
    )