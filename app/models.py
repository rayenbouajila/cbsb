import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class RoleEnum(str, enum.Enum):
    admin = "admin"
    client = "client"


class StatusEnum(str, enum.Enum):
    pending = "pending"
    active = "active"
    rejected = "rejected"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    matricule_fiscal = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    role = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.client)
    status = Column(Enum(StatusEnum), nullable=False, default=StatusEnum.pending)
    full_name = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DocumentTypeEnum(str, enum.Enum):
    purchase_invoice = "purchase_invoice"
    sales_invoice = "sales_invoice"
    bank_statement = "bank_statement"
    tax_declaration = "tax_declaration"
    payslip = "payslip"
    contract = "contract"


class RequestStatusEnum(str, enum.Enum):
    pending = "pending"
    fulfilled = "fulfilled"


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False, unique=True)
    content_type = Column(String, nullable=False, default="application/pdf")
    doc_type = Column(Enum(DocumentTypeEnum), nullable=False, default=DocumentTypeEnum.purchase_invoice)
    size = Column(Integer, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", backref="invoices")


class DocumentRequest(Base):
    __tablename__ = "document_requests"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    doc_type = Column(Enum(DocumentTypeEnum), nullable=False)
    note = Column(String, nullable=True)
    status = Column(Enum(RequestStatusEnum), nullable=False, default=RequestStatusEnum.pending)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    fulfilled_invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)

    client = relationship("User", backref="document_requests")
    fulfilled_invoice = relationship("Invoice")

class DeliverableTypeEnum(str, enum.Enum):
    bilan = "bilan"
    liasse_fiscale = "liasse_fiscale"
    rapport = "rapport"
    autre = "autre"


class Deliverable(Base):
    __tablename__ = "deliverables"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False, unique=True)
    content_type = Column(String, nullable=False, default="application/pdf")
    doc_type = Column(Enum(DeliverableTypeEnum), nullable=False, default=DeliverableTypeEnum.autre)
    note = Column(String, nullable=True)
    size = Column(Integer, nullable=False)
    client_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("User", backref="deliverables")