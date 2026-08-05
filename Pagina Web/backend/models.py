import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Enum, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
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
    is_suspended = Column(Boolean, default=False)
    banned_until = Column(DateTime(timezone=True), nullable=True)
    is_admin = Column(Boolean, default=False)
    
    # Waitlist y Referidos
    referral_code = Column(String, unique=True, index=True, nullable=True)
    referred_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    referral_count = Column(Integer, default=0)
    has_access = Column(Boolean, default=False)
    
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
    event_date = Column(DateTime, nullable=False)
    zone = Column(String, nullable=False)
    ticketing_company = Column(String, nullable=False) # e.g. teleticket, joinnus
    ticket_type = Column(String, nullable=False) # nominada, no_nominada
    is_renominated = Column(Boolean, default=False)
    price = Column(Float, nullable=False)
    
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
    
    # Fechas
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relaciones
    seller = relationship("User", back_populates="tickets_selling", foreign_keys=[seller_id])
    buyer = relationship("User", back_populates="tickets_bought", foreign_keys=[buyer_id])


class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Escrow y pagos
    culqi_charge_id = Column(String, nullable=True)
    amount_total = Column(Float, nullable=False)
    commission_platform = Column(Float, nullable=False)
    amount_seller = Column(Float, nullable=False)
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
    )


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
