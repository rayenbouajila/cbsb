from datetime import datetime,date
from typing import Optional,List
from pydantic import BaseModel, EmailStr,Field
from .models import RoleEnum, StatusEnum, DocumentTypeEnum, RequestStatusEnum,DeliverableTypeEnum,PaymentStatusEnum,ClientTypeEnum, FiscalStatusEnum
from datetime import date as date_type

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


class DeliverableOut(BaseModel):
    id: int
    filename: str
    doc_type: DeliverableTypeEnum
    note: Optional[str] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class DeliverableAdminOut(BaseModel):
    id: int
    filename: str
    doc_type: DeliverableTypeEnum
    note: Optional[str] = None
    uploaded_at: datetime
    client_name: Optional[str] = None
    company_name: Optional[str] = None

    class Config:
        from_attributes = True




class PaymentCreate(BaseModel):
    client_id: int
    label: str
    amount: float
    due_date: Optional[date_type] = None
    note: Optional[str] = None


class PaymentStatusUpdate(BaseModel):
    status: PaymentStatusEnum


class PaymentOut(BaseModel):
    id: int
    label: str
    amount: float
    due_date: Optional[date_type] = None
    status: PaymentStatusEnum
    paid_at: Optional[datetime] = None
    note: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentAdminOut(PaymentOut):
    client_name: Optional[str] = None
    company_name: Optional[str] = None

class MessageCreate(BaseModel):
    content: str

class AdminMessageCreate(BaseModel):
    client_id: int
    content: str

class MessageOut(BaseModel):
    id: int
    sender_role: RoleEnum
    content: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ConversationOut(BaseModel):
    client_id: int
    client_name: Optional[str] = None
    company_name: Optional[str] = None
    last_message: str
    last_message_at: datetime
    unread_count: int

class FiscalSituationCreate(BaseModel):
    year: int
    client_type: ClientTypeEnum


class MonthlyDeclarationOut(BaseModel):
    id: int
    month: int
    declaration_type: str
    due_date: date
    submission_date: Optional[date] = None
    payment_date: Optional[date] = None
    status: FiscalStatusEnum
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class AnnualDeclarationOut(BaseModel):
    id: int
    declaration_type: str
    due_date: date
    submission_date: Optional[date] = None
    amount: Optional[float] = None
    status: FiscalStatusEnum
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class ProvisionalPaymentOut(BaseModel):
    id: int
    installment_number: int
    due_date: date
    amount: Optional[float] = None
    payment_date: Optional[date] = None
    status: FiscalStatusEnum
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class FiscalSituationOut(BaseModel):
    id: int
    year: int
    client_type: ClientTypeEnum
    monthly_declarations: List[MonthlyDeclarationOut]
    annual_declarations: List[AnnualDeclarationOut]
    provisional_payments: List[ProvisionalPaymentOut]

    class Config:
        from_attributes = True


class FiscalLineUpdate(BaseModel):
    """Payload generique pour PUT /admin/fiscal-status/{id} - entity_type
    determine dans quelle table `id` doit etre cherche."""
    entity_type: str  # "monthly" | "annual" | "provisional"
    submission_date: Optional[date] = None
    payment_date: Optional[date] = None
    amount: Optional[float] = None
    status: Optional[FiscalStatusEnum] = None
    notes: Optional[str] = None


 
 
class EmailVerificationRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
 
 
class ResendVerificationRequest(BaseModel):
    email: EmailStr
 
 
class VerificationMessageResponse(BaseModel):
    message: str
 