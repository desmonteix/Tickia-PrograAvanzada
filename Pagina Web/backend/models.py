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
    commission_rate = Column(Numeric(5, 4), nullable=False, default=Decimal('.10'), server_default='0.10')
    reservation_id = Column(UUID(as_uuid=True), nullable=True)
    reservation_total = Column(Numeric(12, 2), nullable=True)
    reservation_discount = Column(Numeric(12, 2), nullable=True)
    reservation_discount_rate = Column(Numeric(5, 4), nullable=True)
    reservation_commission_rate = Column(Numeric(5, 4), nullable=True)
    reservation_seller_reward_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    
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
        CheckConstraint('commission_rate >= 0 AND commission_rate <= 1', name='chk_ticket_commission_rate'),
        CheckConstraint('(reservation_id IS NULL AND reservation_total IS NULL AND reservation_discount IS NULL) OR '
                        '(reservation_id IS NOT NULL AND reservation_total IS NOT NULL AND reservation_discount IS NOT NULL '
                        'AND reservation_total > 0 AND reservation_discount >= 0 '
                        'AND round(reservation_total * 100, 0) + round(reservation_discount * 100, 0) '
                        '= round(price * 100, 0))', name='chk_ticket_quote'),
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
    payment_provider = Column(String, nullable=False, default='culqi', server_default='culqi')
    provider_payment_id = Column(String, nullable=True)
    checkout_url = Column(Text, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    available_after = Column(DateTime(timezone=True), nullable=True)
    payin_fee = Column(Numeric(12, 2), nullable=True)
    payout_fee = Column(Numeric(12, 2), nullable=True)
    fee_terms_hash = Column(String, nullable=True)
    payout_terms = Column(Text, nullable=True)
    amount_total = Column(Numeric(12, 2), nullable=False)
    # NULL listed_amount/rate identifies an unchanged historical transaction.
    listed_amount = Column(Numeric(12, 2), nullable=True)
    buyer_discount = Column(Numeric(12, 2), nullable=False, default=Decimal('0'), server_default='0')
    commission_rate = Column(Numeric(5, 4), nullable=True)
    referral_reward_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    buyer_discount_rate = Column(Numeric(5, 4), nullable=False, default=Decimal('0'), server_default='0')
    seller_referral_reward_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
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
        UniqueConstraint('payment_provider', 'provider_payment_id', name='uq_transaction_provider_payment'),
        Index('uq_ticket_settlement', 'ticket_id', unique=True,
              postgresql_where=text("status IN ('PROCESSING','UNKNOWN','SUCCEEDED','REFUND_PENDING','REFUNDED')"),
              sqlite_where=text("status IN ('PROCESSING','UNKNOWN','SUCCEEDED','REFUND_PENDING','REFUNDED')")),
        CheckConstraint('amount_total > 0 AND commission_platform >= 0 AND amount_seller >= 0', name='chk_transaction_amounts'),
        CheckConstraint("buyer_discount >= 0 AND ((listed_amount IS NULL AND buyer_discount = 0) OR "
                        "(listed_amount IS NOT NULL AND commission_rate IS NOT NULL "
                        "AND commission_rate >= 0 AND commission_rate <= 1 "
                        "AND round(listed_amount * 100, 0) = round(amount_total * 100, 0) + round(buyer_discount * 100, 0) "
                        "AND round(listed_amount * 100, 0) = round(commission_platform * 100, 0) + round(amount_seller * 100, 0) "
                        "AND round(commission_platform * 100, 0) = round(listed_amount * commission_rate * 100, 0) "
                        "AND buyer_discount_rate >= 0 AND buyer_discount_rate < 1 "
                        "AND round(buyer_discount * 100, 0) = round(listed_amount * buyer_discount_rate * 100, 0)))", name='chk_transaction_promotion_amounts'),
        CheckConstraint('(buyer_discount = 0 AND referral_reward_user_id IS NULL) OR '
                        '(buyer_discount > 0 AND referral_reward_user_id IS NOT NULL '
                        'AND referral_reward_user_id = buyer_id)', name='chk_transaction_reward_owner'),
    )


class Referral(Base):
    __tablename__ = 'referrals'
    referred_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), primary_key=True)
    referrer_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    qualified = Column(Boolean, nullable=False, default=False)
    seller_qualified_at = Column(DateTime(timezone=True), nullable=True)
    seller_ticket_id = Column(UUID(as_uuid=True), ForeignKey('tickets.id'), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (CheckConstraint('referrer_id != referred_user_id', name='chk_referral_not_self'),)


class ReferralReward(Base):
    __tablename__ = 'referral_rewards'
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), primary_key=True)
    earned_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    campaign_id = Column(UUID(as_uuid=True), nullable=True)
    reward_kind = Column(String, nullable=False, default='REGISTRATION', server_default='REGISTRATION')
    buyer_discount_rate = Column(Numeric(5, 4), nullable=False, default=Decimal('.05'), server_default='0.05')
    seller_commission_rate = Column(Numeric(5, 4), nullable=True)
    choice = Column(String, nullable=True, default='BUY')
    pending_upgrade = Column(Text, nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    reserved_ticket_id = Column(UUID(as_uuid=True), ForeignKey('tickets.id'), nullable=True, index=True)
    reserved_until = Column(DateTime(timezone=True), nullable=True)
    reserved_transaction_id = Column(UUID(as_uuid=True), ForeignKey('transactions.id'), nullable=True, index=True)
    used_transaction_id = Column(UUID(as_uuid=True), ForeignKey('transactions.id'), nullable=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint('buyer_discount_rate >= 0 AND buyer_discount_rate < 1 AND '
                        '(seller_commission_rate IS NULL OR (seller_commission_rate >= 0 AND seller_commission_rate <= 1))', name='chk_reward_rates'),
        CheckConstraint("choice IS NULL OR choice IN ('BUY','SELL')", name='chk_reward_choice'),
        CheckConstraint('(used_transaction_id IS NULL AND used_at IS NULL) OR '
                        '(used_transaction_id IS NOT NULL AND used_at IS NOT NULL '
                        'AND reserved_ticket_id IS NULL AND reserved_transaction_id IS NULL '
                        'AND reserved_until IS NULL)', name='chk_reward_used'),
        CheckConstraint('reserved_transaction_id IS NULL OR reserved_ticket_id IS NOT NULL', name='chk_reward_transaction'),
        CheckConstraint('reserved_ticket_id IS NOT NULL OR '
                        '(reserved_transaction_id IS NULL AND reserved_until IS NULL)', name='chk_reward_empty_hold'),
        CheckConstraint('reserved_ticket_id IS NULL OR reserved_transaction_id IS NOT NULL '
                        'OR reserved_until IS NOT NULL', name='chk_reward_hold_expiry'),
    )


class PromotionCampaign(Base):
    __tablename__ = 'promotion_campaigns'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    archived = Column(Boolean, nullable=False, default=False)
    listing_commission_rate = Column(Numeric(5, 4), nullable=False)
    registration_discount_rate = Column(Numeric(5, 4), nullable=False)
    seller_buyer_discount_rate = Column(Numeric(5, 4), nullable=False)
    seller_commission_rate = Column(Numeric(5, 4), nullable=False)
    __table_args__ = (
        CheckConstraint('ends_at > starts_at', name='chk_campaign_dates'),
        CheckConstraint('listing_commission_rate >= 0 AND listing_commission_rate < 1 AND '
                        'registration_discount_rate >= 0 AND registration_discount_rate <= 0.5 AND '
                        'seller_buyer_discount_rate >= 0 AND seller_buyer_discount_rate <= 0.5 AND '
                        'seller_commission_rate >= 0 AND seller_commission_rate < 1', name='chk_campaign_rates'),
    )


class SiteSettings(Base):
    __tablename__ = 'site_settings'
    id = Column(Integer, primary_key=True, default=1)
    registrations_enabled = Column(Boolean, nullable=False, default=True)
    publications_enabled = Column(Boolean, nullable=False, default=True)
    purchases_enabled = Column(Boolean, nullable=False, default=True)
    maintenance_mode = Column(Boolean, nullable=False, default=False)
    announcement = Column(String(500), nullable=False, default='')
    __table_args__ = (CheckConstraint('id = 1', name='chk_settings_singleton'),)


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
    settlement_check_at = Column(DateTime(timezone=True), nullable=True)
    reputation_applied = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        CheckConstraint("review_state IN ('HELD','DISPUTED','RESOLVED')", name='chk_review_state'),
        CheckConstraint("settlement_state IN ('NONE','QUEUED','BLOCKED','PROCESSING','UNKNOWN','SUCCEEDED')", name='chk_review_settlement'),
    )


class PayoutProfile(Base):
    __tablename__ = 'payout_profiles'
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), primary_key=True)
    beneficiary_id = Column(String, unique=True, nullable=True)
    bank_account_id = Column(Integer, unique=True, nullable=True)
    status = Column(String, nullable=False, default='CREATING')
    account_last4 = Column(String(4), nullable=False)
    identity_hash = Column(String(64), nullable=False, unique=True)
    account_hash = Column(String(64), nullable=False)
    request_encrypted = Column(Text, nullable=True)
    fee_terms_hash = Column(String(64), nullable=False)
    error = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class FinancialOperation(Base):
    __tablename__ = 'financial_operations'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(UUID(as_uuid=True), ForeignKey('purchase_reviews.id'), nullable=False, index=True)
    kind = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    bank_account_id = Column(Integer, nullable=True)
    provider_id = Column(String, nullable=True, unique=True)
    status = Column(String, nullable=False, default='READY')
    payload = Column(Text, nullable=True)
    error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    next_check_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index('uq_financial_active_review', 'review_id', unique=True,
              postgresql_where=text("status != 'REJECTED'"), sqlite_where=text("status != 'REJECTED'")),
        CheckConstraint("kind IN ('PAYOUT','REFUND')", name='chk_financial_kind'),
        CheckConstraint('amount > 0', name='chk_financial_amount'),
        CheckConstraint("status IN ('READY','SENDING','PENDING','UNKNOWN','SUCCEEDED','REJECTED')", name='chk_financial_status'),
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
