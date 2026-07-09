from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr,Field
from .models import RoleEnum, StatusEnum


class RegisterRequest(BaseModel):
    email: str
    full_name: str
    company_name: str
    password: str

class ActivateRequest(BaseModel):
    token: str
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: RoleEnum
    status: StatusEnum


class UserOut(BaseModel):
    id: int
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
    uploaded_at: datetime

    class Config:
        from_attributes = True


class InvoiceAdminOut(BaseModel):
    id: int
    filename: str
    uploaded_at: datetime
    client_name: Optional[str] = None
    company_name: Optional[str] = None

    class Config:
        from_attributes = True