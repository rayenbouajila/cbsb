import enum
from datetime import datetime
from sqlalchemy import Column, Integer, Numeric, String, DateTime, Enum, Text, ForeignKey,Numeric, Date,Text,Boolean,UniqueConstraint
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from .database import Base
from sqlalchemy.dialects.postgresql import JSONB

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
    email_verified = Column(Boolean, nullable=False, default=False)
    verification_code_hash = Column(String, nullable=True)
    verification_code_expires_at = Column(DateTime, nullable=True)
    verification_attempts = Column(Integer, nullable=False, default=0)
    last_verification_sent_at = Column(DateTime, nullable=True)
 



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



class ExtractionStatusEnum(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    success = "success"
    failed = "failed"
    manual_review = "manual_review"


class InvoiceExtractedData(Base):
    __tablename__ = "invoice_extracted_data"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Colonnes fixes : gardees pour filtrage/recherche SQL rapide
    # (ex: WHERE fournisseur = 'X', ORDER BY montant_ttc, etc.)
    numero_facture = Column(String(100), nullable=True)
    date_facture = Column(Date, nullable=True)
    fournisseur = Column(String(255), nullable=True)
    categorie = Column(String(100), nullable=True)
    montant_ht = Column(Numeric(14, 2), nullable=True)
    taux_tva = Column(Numeric(5, 2), nullable=True)
    montant_tva = Column(Numeric(14, 2), nullable=True)
    montant_ttc = Column(Numeric(14, 2), nullable=True)

    # AJOUT : liste complete et dynamique des champs detectes par
    # invoice_extraction.py (ExtractionResult.to_json()). C'est cette
    # colonne que excel_export.py / export_router.py utilisent pour
    # generer les colonnes Excel dynamiques (y compris les champs "extra"
    # comme "Reference commande", "Mode de paiement", etc. qui n'ont pas
    # de colonne fixe dediee ci-dessus).
    extracted_fields = Column(JSONB, nullable=True, default=list)

    extraction_status = Column(Enum(ExtractionStatusEnum), nullable=False, default=ExtractionStatusEnum.pending)
    extraction_confidence = Column(Numeric(5, 2), nullable=True)
    extraction_engine = Column(String(50), nullable=True)
    raw_extracted_text = Column(Text, nullable=True)
    extraction_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    devise = Column(String(10), nullable=True)
    timbre_fiscal = Column(Numeric(14, 2), nullable=True)
    validation_status = Column(String(20), nullable=True, default="unknown")
    validation_message = Column(Text, nullable=True)
    manually_edited = Column(Boolean, nullable=False, default=False)
    invoice = relationship("Invoice", backref=backref("extracted_data", uselist=False))



class PaymentStatusEnum(str, enum.Enum):
    paid = "paid"
    unpaid = "unpaid"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label = Column(String(255), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    due_date = Column(Date, nullable=True)
    status = Column(Enum(PaymentStatusEnum), nullable=False, default=PaymentStatusEnum.unpaid)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    client = relationship("User", backref="payments")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sender_role = Column(Enum(RoleEnum), nullable=False)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("User", foreign_keys=[client_id])
    sender = relationship("User", foreign_keys=[sender_id])

class ClientTypeEnum(str, enum.Enum):
    personne_physique = "personne_physique"
    personne_morale = "personne_morale"


class FiscalStatusEnum(str, enum.Enum):
    envoye_paiement = "envoye_paiement"
    paiement_accepte = "paiement_accepte"
    paiement_rejete = "paiement_rejete"
class FiscalSituation(Base):
    __tablename__ = "fiscal_situations"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    year = Column(Integer, nullable=False)
    client_type = Column(Enum(ClientTypeEnum), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    client = relationship("User", backref="fiscal_situations")
    monthly_declarations = relationship("MonthlyFiscalDeclaration", cascade="all, delete-orphan", backref="fiscal_situation")
    annual_declarations = relationship("AnnualFiscalDeclaration", cascade="all, delete-orphan", backref="fiscal_situation")
    provisional_payments = relationship("ProvisionalPayment", cascade="all, delete-orphan", backref="fiscal_situation")

    __table_args__ = (UniqueConstraint("client_id", "year", name="uq_fiscal_situation_client_year"),)


class MonthlyFiscalDeclaration(Base):
    __tablename__ = "monthly_fiscal_declarations"

    id = Column(Integer, primary_key=True, index=True)
    fiscal_situation_id = Column(Integer, ForeignKey("fiscal_situations.id", ondelete="CASCADE"), nullable=False)
    month = Column(Integer, nullable=False)
    declaration_type = Column(String(40), nullable=False)
    due_date = Column(Date, nullable=False)
    submission_date = Column(Date, nullable=True)
    payment_date = Column(Date, nullable=True)
    status = Column(Enum(FiscalStatusEnum), nullable=False, default=FiscalStatusEnum.envoye_paiement)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AnnualFiscalDeclaration(Base):
    __tablename__ = "annual_fiscal_declarations"

    id = Column(Integer, primary_key=True, index=True)
    fiscal_situation_id = Column(Integer, ForeignKey("fiscal_situations.id", ondelete="CASCADE"), nullable=False)
    declaration_type = Column(String(40), nullable=False)
    due_date = Column(Date, nullable=False)
    submission_date = Column(Date, nullable=True)
    amount = Column(Numeric(14, 3), nullable=True)
    status = Column(Enum(FiscalStatusEnum), nullable=False, default=FiscalStatusEnum.envoye_paiement)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProvisionalPayment(Base):
    __tablename__ = "provisional_payments"

    id = Column(Integer, primary_key=True, index=True)
    fiscal_situation_id = Column(Integer, ForeignKey("fiscal_situations.id", ondelete="CASCADE"), nullable=False)
    installment_number = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False)
    amount = Column(Numeric(14, 3), nullable=True)
    payment_date = Column(Date, nullable=True)
    status = Column(Enum(FiscalStatusEnum), nullable=False, default=FiscalStatusEnum.envoye_paiement)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

