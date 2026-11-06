import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Enum, Float, UniqueConstraint, Index, text, CheckConstraint, Numeric, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from decimal import Decimal
from .database import Base

class HashState(str, enum.Enum):
    ACTIVO = "ACTIVO"
    LIBERADO = "LIBERADO"
    REEMBOLSADO = "REEMBOLSADO"

class TicketState(str, enum.Enum):
    DISPONIBLE = "DISPONIBLE"
    RESERVADA = "RESERVADA"
    VENDIDA = "VENDIDA"
    PENDIENTE_RENOMINACION = "PENDIENTE_RENOMINACION"
    LIBERADA = "LIBERADA"
    REEMBOLSADA = "REEMBOLSADA"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    # KYC y Verificación
    full_name = Column(String, nullable=True)
    dni = Column(String, unique=True, nullable=True)
    phone_number = Column(String, nullable=True)
    is_email_verified = Column(Boolean, default=False)
    is_kyc_verified = Column(Boolean, default=False)
    
    # Riesgo y Scoring
    trust_score = Column(Integer, default=100)
    rating = Column(Numeric(3, 2), default=Decimal('4.00'), nullable=False)
    warning_count = Column(Integer, default=0, nullable=False)
    __table_args__ = (CheckConstraint('rating >= 0 AND rating <= 5', name='chk_user_rating'),)
    is_suspended = Column(Boolean, default=False)
    banned_until = Column(DateTime(timezone=True), nullable=True)
    is_admin = Column(Boolean, default=False)
    
    # Waitlist y Referidos
    referral_code = Column(String, unique=True, index=True, nullable=True)
    referred_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    referral_count = Column(Integer, default=0)
    has_access = Column(Boolean, default=True)
    
    # Relaciones
    tickets_selling = relationship("Ticket", back_populates="seller", foreign_keys="Ticket.seller_id")
    tickets_bought = relationship("Ticket", back_populates="buyer", foreign_keys="Ticket.buyer_id")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # Metadatos del evento (ingresados por vendedor y verificados)
    event_name = Column(String, nullable=False)
    event_date = Column(DateTime(timezone=True), nullable=False)
    event_end_date = Column(DateTime(timezone=True), nullable=True)  # Legacy events require manual review.
    zone = Column(String, nullable=False)
    ticketing_company = Column(String, nullable=False) # e.g. teleticket, joinnus
    ticket_type = Column(String, nullable=False) # nominada, no_nominada
    is_renominated = Column(Boolean, default=False)
    price = Column(Numeric(12, 2), nullable=False)
    
    # Estado de concurrencia y escrow
    estado = Column(Enum(TicketState), default=TicketState.DISPONIBLE, nullable=False)
    reserved_until = Column(DateTime(timezone=True), nullable=True)
    
    # Renominación Escrow
    renomination_deadline = Column(DateTime(timezone=True), nullable=True)
    renomination_reminder_sent = Column(Boolean, default=False)
    
    # Social Boost (Traffic-driven)
    boost_referral_clicks = Column(Integer, default=0)
    boosted_until = Column(DateTime(timezone=True), nullable=True)
    
    # Datos de seguridad QR (nunca exponer hash o qr url en el API público)
    qr_hash_sha256 = Column(String, unique=False, index=True, nullable=False)
    hash_estado = Column(Enum(HashState), default=HashState.ACTIVO, nullable=False)
    qr_image_url_encrypted = Column(String, nullable=False) # Path in Storage
    qr_watermarked_url = Column(String, nullable=True)
    
    __table_args__ = (
        Index("uq_ticket_active_qr", "qr_hash_sha256", unique=True,
              postgresql_where=text("hash_estado = 'ACTIVO'"), sqlite_where=text("hash_estado = 'ACTIVO'")),
        CheckConstraint("price >= 3 AND price <= 5000", name="chk_ticket_price"),
        CheckConstraint("estado NOT IN ('VENDIDA', 'PENDIENTE_RENOMINACION', 'LIBERADA') OR buyer_id IS NOT NULL", name="chk_ticket_buyer"),
    )

    # Fechas
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relaciones
    seller = relationship("User", back_populates="tickets_selling", foreign_keys=[seller_id])
    buyer = relationship("User", back_populates="tickets_bought", foreign_keys=[buyer_id])

    @property
    def seller_rating(self):
        return float(self.seller.rating)


class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Escrow y pagos
    payment_token_hash = Column(String, nullable=True, unique=True)
    culqi_charge_id = Column(String, nullable=True)
    amount_total = Column(Numeric(12, 2), nullable=False)
    commission_platform = Column(Numeric(12, 2), nullable=False)
    amount_seller = Column(Numeric(12, 2), nullable=False)  # Estimate before provider fees.
    provider_fee = Column(Numeric(12, 2), nullable=True)
    seller_net_amount = Column(Numeric(12, 2), nullable=True)  # Final only after verified reconciliation.
    status = Column(String, default="PENDING") # PENDING, SUCCEEDED, FAILED, REFUNDED
    
    # Anti-chargeback evidencia
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    hmac_link_generated_at = Column(DateTime(timezone=True), nullable=True)
    hmac_link_opened_at = Column(DateTime(timezone=True), nullable=True)
    
    # Entrega segura QR (1 solo uso)
    download_token = Column(String, nullable=True, unique=True, index=True)
    download_token_used = Column(Boolean, default=False)
    download_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # SECURITY: Restricción única en BD — impide procesar el mismo cargo de Culqi dos veces
    __table_args__ = (
        UniqueConstraint('culqi_charge_id', name='uq_transaction_culqi_charge_id'),
        Index('uq_ticket_settlement', 'ticket_id', unique=True,
              postgresql_where=text("status IN ('PROCESSING','UNKNOWN','SUCCEEDED','REFUND_PENDING','REFUNDED')"),
              sqlite_where=text("status IN ('PROCESSING','UNKNOWN','SUCCEEDED','REFUND_PENDING','REFUNDED')")),
        CheckConstraint('amount_total > 0 AND commission_platform >= 0 AND amount_seller >= 0', name='chk_transaction_amounts'),
    )


class PurchaseReview(Base):
    __tablename__ = 'purchase_reviews'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey('transactions.id'), nullable=False, unique=True)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey('tickets.id'), nullable=False, unique=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    closes_at = Column(DateTime(timezone=True), nullable=True)
    review_state = Column(String, nullable=False, default='HELD')
    decision = Column(String, nullable=True)
    dispute_text = Column(Text, nullable=True)
    reported_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    decision_reason = Column(Text, nullable=True)
    settlement_state = Column(String, nullable=False, default='NONE')
    settlement_reference = Column(String, nullable=True, unique=True)
    settlement_error = Column(String, nullable=True)
    reputation_applied = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        CheckConstraint("review_state IN ('HELD','DISPUTED','RESOLVED')", name='chk_review_state'),
        CheckConstraint("settlement_state IN ('NONE','QUEUED','BLOCKED','PROCESSING','UNKNOWN','SUCCEEDED')", name='chk_review_settlement'),
    )


class DisputeEvidence(Base):
    __tablename__ = 'dispute_evidence'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(UUID(as_uuid=True), ForeignKey('purchase_reviews.id'), nullable=False, index=True)
    storage_path = Column(String, nullable=False)
    media_type = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False) # e.g. TICKET_STATE_CHANGE
    entity_type = Column(String, nullable=False) # e.g. ticket
    entity_id = Column(String, nullable=False)
    previous_state = Column(String, nullable=True)
    new_state = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
