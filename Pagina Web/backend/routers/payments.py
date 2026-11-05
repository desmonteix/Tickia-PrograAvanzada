import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .. import models
from ..database import get_db
from ..dependencies import get_current_user
from ..payment_provider import get_payment_provider, PaymentUnavailable, PaymentDeclined, PaymentUncertain
from ..rate_limit import limiter
from ..state_machine import validate_ticket_transition
from ..money import amounts
from ..post_purchase import review_deadline

router = APIRouter(prefix="/api/payments", tags=["payments"])
logger = logging.getLogger(__name__)
ACTIVE_PAYMENT_STATES = ("PROCESSING", "UNKNOWN", "SUCCEEDED", "REFUND_PENDING", "REFUNDED")


def as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class ChargeRequest(BaseModel):
    ticket_id: uuid.UUID
    culqi_token: str = Field(min_length=10, max_length=100, pattern=r"^(tkn|ype)_(test|live)_[A-Za-z0-9]+$")


def settle_verified_charge(db, tx, ticket, charge):
    if not isinstance(charge, dict):
        raise PaymentUncertain("Respuesta de cargo invalida.")
    total_cents = int(Decimal(str(tx.amount_total)) * 100)
    metadata = charge.get("metadata") or {}
    outcome = charge.get("outcome") or {}
    if not isinstance(metadata, dict) or not isinstance(outcome, dict):
        raise PaymentUncertain("Metadata de cargo invalida.")
    if (
        charge.get("object") != "charge" or not isinstance(charge.get("id"), str)
        or not re.fullmatch(r"chr_[A-Za-z0-9_]{6,100}", charge["id"])
        or charge.get("amount") != total_cents or charge.get("currency_code") != "PEN"
        or charge.get("capture") is not True
        or outcome.get("type") != "venta_exitosa"
        or charge.get("dispute", False) is not False
        or charge.get("amount_refunded", 0) != 0
        or metadata.get("transaction_id") != str(tx.id)
        or metadata.get("ticket_id") != str(ticket.id)
        or metadata.get("buyer_id") != str(tx.buyer_id)
        or ticket.buyer_id != tx.buyer_id
    ):
        raise PaymentUncertain("La confirmación no coincide con la compra.")
    existing = db.query(models.Transaction).filter(
        models.Transaction.culqi_charge_id == charge["id"], models.Transaction.id != tx.id,
    ).first()
    if existing:
        raise PaymentUncertain("El cargo ya pertenece a otra compra.")
    if tx.status == "SUCCEEDED" and tx.culqi_charge_id == charge["id"]:
        return
    if tx.status not in ("PROCESSING", "UNKNOWN") or ticket.estado != models.TicketState.RESERVADA:
        raise PaymentUncertain("La compra requiere conciliación manual.")
    nominated = ticket.ticket_type == "nominada"
    new_state = models.TicketState.PENDIENTE_RENOMINACION if nominated else models.TicketState.VENDIDA
    validate_ticket_transition(ticket.estado, new_state)
    ticket.estado = new_state
    ticket.reserved_until = None
    if nominated:
        ticket.renomination_deadline = min(datetime.now(timezone.utc) + timedelta(hours=24), as_utc(ticket.event_date))
        ticket.renomination_reminder_sent = False
    tx.status = "SUCCEEDED"
    tx.culqi_charge_id = charge["id"]
    from ..post_purchase import ensure_review
    ensure_review(db, tx, ticket)
    db.add(models.AuditLog(
        user_id=tx.buyer_id, action="PAYMENT_SUCCEEDED", entity_type="ticket",
        entity_id=str(ticket.id), previous_state="RESERVADA", new_state=new_state.value,
    ))


@router.get("/status")
def payment_status():
    return {"enabled": get_payment_provider().enabled()}


@router.post("/charge")
@limiter.limit("5/minute")
def process_charge(request: Request, charge_req: ChargeRequest, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    provider = get_payment_provider()
    if not provider.enabled():
        raise HTTPException(503, "Los pagos aún no están habilitados.")
    ticket = db.query(models.Ticket).filter(models.Ticket.id == charge_req.ticket_id).with_for_update().first()
    if not ticket or ticket.buyer_id != current_user.id:
        db.rollback()
        raise HTTPException(400, "Entrada no válida para este comprador.")
    previous = db.query(models.Transaction).filter(
        models.Transaction.ticket_id == ticket.id, models.Transaction.status.in_(ACTIVE_PAYMENT_STATES),
    ).first()
    if previous:
        db.rollback()
        raise HTTPException(409, "Esta compra ya está procesada o pendiente de confirmación. No repitas el pago.")
    if ticket.estado != models.TicketState.RESERVADA or not ticket.reserved_until or as_utc(ticket.reserved_until) <= datetime.now(timezone.utc):
        db.rollback()
        raise HTTPException(409, "La reserva expiró. Vuelve a seleccionar la entrada.")
    if ticket.ticket_type == "nominada" and not (
        current_user.is_kyc_verified and current_user.full_name and current_user.dni
    ):
        db.rollback()
        raise HTTPException(403, "La compra nominada requiere identidad verificada.")
    if ticket.event_end_date is not None and review_deadline(ticket.event_end_date) is None:
        db.rollback()
        raise HTTPException(422, 'La fecha de finalización requiere corrección antes de cobrar.')
    total, fee, seller = amounts(ticket.price)
    tx = models.Transaction(
        ticket_id=ticket.id, buyer_id=current_user.id,
        payment_token_hash=hashlib.sha256(charge_req.culqi_token.encode()).hexdigest(),
        amount_total=total, commission_platform=fee, amount_seller=seller,
        status="PROCESSING", ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:512],
    )
    try:
        db.add(tx)
        db.commit()
        transaction_id = tx.id
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El token o la compra ya están en proceso.")
    try:
        charge = provider.create_charge(charge_req.culqi_token, int(total * 100), current_user.email, {
            "transaction_id": str(transaction_id), "ticket_id": str(ticket.id), "buyer_id": str(current_user.id),
        })
        # Reacquire locks after network I/O; the durable intent prevents another payment.
        db.expire_all()
        ticket = db.query(models.Ticket).filter(models.Ticket.id == charge_req.ticket_id).with_for_update().first()
        tx = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).with_for_update().first()
        settle_verified_charge(db, tx, ticket, charge)
        db.commit()
    except PaymentDeclined:
        db.rollback()
        # Compare-and-update in the database: a webhook/refund may already have
        # advanced the ledger while the original HTTP request was in flight.
        db.query(models.Transaction).filter(
            models.Transaction.id == transaction_id, models.Transaction.status == 'PROCESSING',
        ).update({'status': 'FAILED'}, synchronize_session=False)
        db.commit()
        raise HTTPException(402, "La pasarela rechazó el pago. Verifica los datos de tu tarjeta.")
    except (PaymentUnavailable, PaymentUncertain, IntegrityError):
        db.rollback()
        db.query(models.Transaction).filter(
            models.Transaction.id == transaction_id, models.Transaction.status == 'PROCESSING',
        ).update({'status': 'UNKNOWN'}, synchronize_session=False)
        db.commit()
        raise HTTPException(502, "Estamos verificando el pago. No vuelvas a pagar; contacta a soporte.")
    return {"message": "Pago confirmado.", "charge_id": tx.culqi_charge_id, "estado": ticket.estado.value}


@router.post("/webhook/culqi")
@limiter.limit("30/minute")
async def culqi_webhook(request: Request, db: Session = Depends(get_db)):
    # Culqi's public docs do not specify an HMAC protocol. Treat notifications as
    # untrusted hints, and retrieve the charge directly over authenticated HTTPS.
    raw = await request.body()
    if len(raw) > 64 * 1024:
        raise HTTPException(413, "Notificación demasiado grande.")
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError()
        if payload.get("type") not in ("charge.succeeded", "charge.creation.succeeded"):
            return {"received": True}
        data = payload.get("data")
        if isinstance(data, str):
            data = json.loads(data)
        charge_id = data.get("id") if isinstance(data, dict) else None
        if not isinstance(charge_id, str) or not re.fullmatch(r"chr_[A-Za-z0-9_]{6,100}", charge_id):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, "Notificación inválida.")
    provider = get_payment_provider()
    if not provider.enabled():
        raise HTTPException(503, "Los pagos aún no están habilitados.")
    try:
        charge = provider.retrieve_charge(charge_id)
        if not isinstance(charge, dict):
            raise PaymentUncertain()
        tx_id = uuid.UUID((charge.get("metadata") or {}).get("transaction_id", ""))
        tx = db.get(models.Transaction, tx_id)
        if tx is None:
            raise HTTPException(409, "El cargo no corresponde a una compra iniciada aquí.")
        # Same lock order as checkout, QR and maintenance: ticket, then transaction.
        ticket = db.query(models.Ticket).filter(models.Ticket.id == tx.ticket_id).with_for_update().first()
        tx = db.query(models.Transaction).filter(models.Transaction.id == tx_id).populate_existing().with_for_update().first()
        if ticket is None:
            raise PaymentUncertain("Entrada no encontrada.")
        settle_verified_charge(db, tx, ticket, charge)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except (PaymentUnavailable, PaymentDeclined, PaymentUncertain, ValueError, TypeError, AttributeError, IntegrityError):
        db.rollback()
        raise HTTPException(502, "La notificación no pudo verificarse con la pasarela.")
    return {"received": True}
