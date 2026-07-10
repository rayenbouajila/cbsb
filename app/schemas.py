from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr,Field
from .models import RoleEnum, StatusEnum, DocumentTypeEnum, RequestStatusEnum


class RegisterRequest(BaseModel):
    email: str
    full_name: str
    matricule_fiscal: str
    company_name: str
    password: str

class ActivateRequest(BaseModel):
    token: str
    password: str


class LoginRequest(BaseModel):
    matricule_fiscal: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: RoleEnum
    status: StatusEnum


class UserOut(BaseModel):
    id: int
    matricule_fiscal: str
    email: str
    role: RoleEnum
    status: StatusEnum
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
class ContactMessageCreate(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str

class ContactMessageOut(BaseModel):
    id: int
    name: str
    email: str
    subject: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True
class InvoiceOut(BaseModel):
    id: int
    filename: str
    doc_type: DocumentTypeEnum
    uploaded_at: datetime

    class Config:
        from_attributes = True


class InvoiceAdminOut(BaseModel):
    id: int
    filename: str
    doc_type: DocumentTypeEnum
    uploaded_at: datetime
    client_name: Optional[str] = None
    company_name: Optional[str] = None

    class Config:
        from_attributes = True


class ClientOut(BaseModel):
    id: int
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    email: str

    class Config:
        from_attributes = True


class DocumentRequestCreate(BaseModel):
    client_id: int
    doc_type: DocumentTypeEnum
    note: Optional[str] = None


class DocumentRequestOut(BaseModel):
    id: int
    doc_type: DocumentTypeEnum
    note: Optional[str] = None
    status: RequestStatusEnum
    created_at: datetime

    class Config:
        from_attributes = True