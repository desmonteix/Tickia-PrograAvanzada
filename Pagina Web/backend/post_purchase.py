"""Review decisions and durable settlement intents; never invent money movement."""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException

from . import models
from .payment_provider import get_payment_provider, PaymentUnavailable, PaymentUncertain, PaymentDeclined
from .state_machine import validate_ticket_transition


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def review_deadline(event_end):
    if event_end is None:
        return None
    try:
        return utc(event_end).astimezone(timezone.utc) + timedelta(hours=24)
    except (OverflowError, ValueError):
        # Legacy malformed calendars must never break settlement after a charge.
        # No deadline means no automatic release, while explicit responses remain open.
        return None


def ensure_review(db, tx, ticket):
    row = db.query(models.PurchaseReview).filter_by(transaction_id=tx.id).first()
    if row is None:
        row = models.PurchaseReview(
            transaction_id=tx.id, ticket_id=ticket.id,
            closes_at=review_deadline(ticket.event_end_date),
            delivered_at=datetime.now(timezone.utc) if ticket.estado == models.TicketState.VENDIDA else None,
        )
        db.add(row)
    return row


def lock_review(db, review_id, buyer_id=None):
    row = db.get(models.PurchaseReview, review_id)
    if row is None:
        raise HTTPException(404, 'Compra no encontrada.')
    ticket = db.query(models.Ticket).filter_by(id=row.ticket_id).with_for_update().first()
    tx = db.query(models.Transaction).filter_by(id=row.transaction_id).populate_existing().with_for_update().first()
    row = db.query(models.PurchaseReview).filter_by(id=review_id).populate_existing().with_for_update().first()
    if tx is None or ticket is None or (buyer_id and tx.buyer_id != buyer_id):
        raise HTTPException(404, 'Compra no encontrada.')
    return row, tx, ticket


def can_respond(row, tx, ticket, now=None):
    now = now or datetime.now(timezone.utc)
    return bool(row.review_state == 'HELD' and row.delivered_at
                and (row.closes_at is None or now < utc(row.closes_at)) and tx.status == 'SUCCEEDED'
                and ticket.estado == models.TicketState.VENDIDA)


def decide(db, row, tx, ticket, decision, actor=None, reason=None):
    if row.review_state == 'RESOLVED' or row.settlement_state != 'NONE':
        raise HTTPException(409, 'Esta compra ya tiene una decisión definitiva.')
    if decision != 'VALID_CLAIM' and (not row.delivered_at or ticket.estado != models.TicketState.VENDIDA or tx.status != 'SUCCEEDED'):
        raise HTTPException(409, 'No se puede liberar dinero de una entrada pendiente de entrega o de pago.')
    row.review_state = 'RESOLVED'
    row.decision = decision
    row.decided_by = actor
    row.decision_reason = reason
    row.settlement_state = 'QUEUED'
    db.add(models.AuditLog(user_id=actor, action='PURCHASE_' + decision,
        entity_type='purchase', entity_id=str(row.id), reason=reason))


def close_expired_reviews(db):
    ids = [row.id for row in db.query(models.PurchaseReview).filter(
        models.PurchaseReview.review_state == 'HELD',
        models.PurchaseReview.closes_at <= datetime.now(timezone.utc),
        models.PurchaseReview.delivered_at.is_not(None),
    ).all()]
    for review_id in ids:
        row, tx, ticket = lock_review(db, review_id)
        if row.review_state == 'HELD' and row.closes_at and utc(row.closes_at) <= datetime.now(timezone.utc):
            if tx.status == 'SUCCEEDED' and ticket.estado == models.TicketState.VENDIDA:
                decide(db, row, tx, ticket, 'SILENT')
        db.commit()


def apply_reputation(db, row, tx, ticket):
    if row.reputation_applied:
        return
    users = {user.id: user for user in db.query(models.User).filter(
        models.User.id.in_([tx.buyer_id, ticket.seller_id]),
    ).order_by(models.User.id).populate_existing().with_for_update().all()}
    buyer_delta, seller_delta = {
        'CONFIRMED': (1, 1), 'SILENT': (0, 1),
        'VALID_CLAIM': (1, 0), 'INVALID_CLAIM': (-1, 1),
    }[row.decision]
    for user_id, delta in ((tx.buyer_id, buyer_delta), (ticket.seller_id, seller_delta)):
        user = users[user_id]
        user.rating = max(Decimal('0'), min(Decimal('5'), user.rating + Decimal('0.25') * delta))
    if row.decision == 'VALID_CLAIM':
        users[ticket.seller_id].warning_count += 1
        db.add(models.AuditLog(user_id=ticket.seller_id, action='SELLER_WARNING',
            entity_type='purchase', entity_id=str(row.id), reason='Reclamo aceptado y reembolso confirmado.'))
    row.reputation_applied = True


def process_settlements(db, provider=None):
    if os.getenv('SETTLEMENT_ENABLED', 'false').lower() != 'true':
        return
    provider = provider or get_payment_provider()
    ids = [row.id for row in db.query(models.PurchaseReview).filter(
        models.PurchaseReview.review_state == 'RESOLVED',
        models.PurchaseReview.settlement_state.in_(['QUEUED', 'BLOCKED']),
    ).all()]
    for review_id in ids:
        row, tx, ticket = lock_review(db, review_id)
        if row.settlement_state not in ('QUEUED', 'BLOCKED'):
            db.rollback()
            continue
        refund = row.decision == 'VALID_CLAIM'
        if not refund and (tx.provider_fee is None or tx.seller_net_amount is None
                or tx.provider_fee < 0 or tx.seller_net_amount <= 0
                or tx.amount_seller - tx.provider_fee != tx.seller_net_amount):
            row.settlement_state = 'BLOCKED'
            row.settlement_error = 'Falta conciliar los cargos del vendedor con la pasarela.'
            db.commit()
            continue
        amount_cents = int((tx.amount_total if refund else tx.seller_net_amount) * 100)
        charge_id, seller_id = tx.culqi_charge_id, str(ticket.seller_id)
        row.settlement_state = 'PROCESSING'
        row.settlement_error = None
        db.commit()  # Durable intent prevents a second worker from sending money.
        try:
            receipt = (provider.refund_buyer(charge_id, amount_cents, str(review_id)) if refund
                else provider.release_funds_to_seller(charge_id, amount_cents, str(review_id), seller_id))
            if not isinstance(receipt, dict) or receipt.get('operation_id') != str(review_id) or receipt.get('amount_cents') != amount_cents or receipt.get('status') != 'SUCCEEDED' or not isinstance(receipt.get('reference'), str) or not receipt['reference']:
                raise PaymentUncertain('El resultado de la liquidación no está confirmado.')
            row, tx, ticket = lock_review(db, review_id)
            finish_settlement(db, row, tx, ticket, receipt['reference'])
        except (PaymentUnavailable, PaymentDeclined):
            db.rollback()
            row, _, _ = lock_review(db, review_id)
            if row.settlement_state == 'SUCCEEDED':
                db.rollback()
                continue
            row.settlement_state = 'BLOCKED'
            row.settlement_error = 'La operación requiere configurar el proveedor o revisar su rechazo.'
            db.commit()
        except Exception:
            # Includes transport, persistence or receipt validation errors after sending.
            # Never retry an uncertain transfer automatically.
            db.rollback()
            row, _, _ = lock_review(db, review_id)
            if row.settlement_state == 'SUCCEEDED':
                db.rollback()
                continue
            row.settlement_state = 'UNKNOWN'
            row.settlement_error = 'Resultado pendiente de conciliación. No repetir la transferencia.'
            db.commit()


def finish_settlement(db, row, tx, ticket, reference):
    if row.settlement_state == 'SUCCEEDED':
        db.rollback()
        return
    refund = row.decision == 'VALID_CLAIM'
    target = models.TicketState.REEMBOLSADA if refund else models.TicketState.LIBERADA
    validate_ticket_transition(ticket.estado, target)
    ticket.estado = target
    if refund:
        tx.status = 'REFUNDED'
        tx.download_token = None
        ticket.hash_estado = models.HashState.REEMBOLSADO
    row.settlement_reference = reference
    row.settlement_state = 'SUCCEEDED'
    row.settlement_error = None
    apply_reputation(db, row, tx, ticket)
    db.add(models.AuditLog(action='SETTLEMENT_CONFIRMED', entity_type='purchase', entity_id=str(row.id), reason=row.decision))
    db.commit()


def reconcile_refunds(db, provider=None):
    if os.getenv('SETTLEMENT_ENABLED', 'false').lower() != 'true':
        return
    provider = provider or get_payment_provider()
    reconcile = getattr(provider, 'refund_is_complete', None)
    if reconcile is None:
        return
    ids = [row.id for row in db.query(models.PurchaseReview).filter(
        models.PurchaseReview.decision == 'VALID_CLAIM',
        models.PurchaseReview.settlement_state.in_(['UNKNOWN', 'PROCESSING']),
    ).all()]
    for review_id in ids:
        row = db.get(models.PurchaseReview, review_id)
        tx = db.get(models.Transaction, row.transaction_id)
        charge_id, amount_cents = tx.culqi_charge_id, int(tx.amount_total * 100)
        db.rollback()  # Do not hold locks while consulting the provider.
        try:
            if reconcile(charge_id, amount_cents) is not True:
                continue
            row, tx, ticket = lock_review(db, review_id)
            if row.settlement_state in ('UNKNOWN', 'PROCESSING') and row.decision == 'VALID_CLAIM':
                # This is a verified charge reference, not an invented refund ID.
                finish_settlement(db, row, tx, ticket, 'verified-full-refund:' + charge_id)
            else:
                db.rollback()
        except Exception:
            db.rollback()  # Keep uncertain; a lookup never resends a refund.
