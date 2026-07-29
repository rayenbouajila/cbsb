from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/contact", tags=["contact"])

@router.post("/send", response_model=schemas.ContactMessageOut)
async def send_contact_message(payload: schemas.ContactMessageCreate, db: Session = Depends(get_db)):
    new_msg = models.ContactMessage(**payload.dict())
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return new_msg