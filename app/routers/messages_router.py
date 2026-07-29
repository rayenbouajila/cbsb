"""
messages_router.py

Messagerie minimaliste : UN fil de discussion par client (pas de sujets/
tickets multiples). Le client ecrit, un admin repond, l'historique est
persiste. `is_read` sert a afficher un badge "non lu" cote admin quand un
client a ecrit une nouvelle question.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas, auth_utils
from ..database import get_db

router = APIRouter(tags=["messages"])


# ---------- Client ----------

@router.get("/client/messages", response_model=List[schemas.MessageOut])
def list_my_messages(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    messages = (
        db.query(models.Message)
        .filter(models.Message.client_id == current_user.id)
        .order_by(models.Message.created_at.asc())
        .all()
    )
    # Le client vient de lire le fil : marque comme lus les messages envoyes par l'admin
    unread_admin_msgs = [m for m in messages if m.sender_role == models.RoleEnum.admin and not m.is_read]
    for m in unread_admin_msgs:
        m.is_read = True
    if unread_admin_msgs:
        db.commit()

    return messages


@router.post("/client/messages", response_model=schemas.MessageOut)
def send_my_message(
    payload: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Le message ne peut pas etre vide.")

    message = models.Message(
        client_id=current_user.id,
        sender_id=current_user.id,
        sender_role=models.RoleEnum.client,
        content=content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


# ---------- Admin ----------

@router.get("/admin/messages", response_model=List[schemas.MessageOut])
def admin_list_messages(
    client_id: int = Query(...),
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    client = db.query(models.User).filter(
        models.User.id == client_id,
        models.User.role == models.RoleEnum.client,
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable")

    messages = (
        db.query(models.Message)
        .filter(models.Message.client_id == client_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )
    # L'admin vient d'ouvrir ce fil : marque comme lus les messages envoyes par le client
    unread_client_msgs = [m for m in messages if m.sender_role == models.RoleEnum.client and not m.is_read]
    for m in unread_client_msgs:
        m.is_read = True
    if unread_client_msgs:
        db.commit()

    return messages


@router.post("/admin/messages", response_model=schemas.MessageOut)
def admin_send_message(
    payload: schemas.AdminMessageCreate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Le message ne peut pas etre vide.")

    client = db.query(models.User).filter(
        models.User.id == payload.client_id,
        models.User.role == models.RoleEnum.client,
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable")

    message = models.Message(
        client_id=payload.client_id,
        sender_id=admin.id,
        sender_role=models.RoleEnum.admin,
        content=content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get("/admin/conversations", response_model=List[schemas.ConversationOut])
def admin_list_conversations(
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth_utils.require_admin),
):
    """Vue d'ensemble : un fil par client ayant echange au moins un message,
    trie par derniere activite, avec le nombre de messages client non lus."""
    messages = db.query(models.Message).order_by(models.Message.created_at.asc()).all()

    by_client: dict[int, list[models.Message]] = {}
    for m in messages:
        by_client.setdefault(m.client_id, []).append(m)

    conversations = []
    for client_id, msgs in by_client.items():
        last = msgs[-1]
        unread = sum(1 for m in msgs if m.sender_role == models.RoleEnum.client and not m.is_read)
        conversations.append(schemas.ConversationOut(
            client_id=client_id,
            client_name=last.client.full_name if last.client else None,
            company_name=last.client.company_name if last.client else None,
            last_message=last.content,
            last_message_at=last.created_at,
            unread_count=unread,
        ))

    conversations.sort(key=lambda c: c.last_message_at, reverse=True)
    return conversations