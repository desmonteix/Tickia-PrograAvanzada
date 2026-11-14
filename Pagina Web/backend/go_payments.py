"""Canonical Go payment reconciliation; checkout redirects never deliver tickets."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import or_, and_

from . import models
from .dlocal_go import money_cents
from .go_fees import payin_estimate, payout_amount
from .payment_provider import PaymentUncertain
from .post_purchase import ensure_review, utc
from .state_machine import validate_ticket_transition
from .promotions import consume_reward, release_failed_reward


def lock_transaction(db, transaction_id):
    tx = db.get(models.Transaction, transaction_id)
    if not tx:
        raise PaymentUncertain('Compra desconocida.')
    ticket = db.query(models.Ticket).filter_by(id=tx.ticket_id).populate_existing().with_for_update().one()
    tx = db.query(models.Transaction).filter_by(id=transaction_id).populate_existing().with_for_update().one()
    return tx, ticket


def reconcile_payment(db, transaction_id, payment):
    tx, ticket = lock_transaction(db, transaction_id)
    if (not isinstance(payment, dict) or tx.payment_provider != 'dlocal_go'
            or str(payment.get('order_id')) != str(tx.id)
            or payment.get('country') != 'PE' or payment.get('currency') != 'PEN'
            or money_cents(payment.get('amount')) != int(tx.amount_total * 100)
            or not isinstance(payment.get('id'), str)
            or (tx.provider_payment_id and tx.provider_payment_id != payment['id'])):
        raise PaymentUncertain('El pago no coincide con la reserva.')
    duplicate = db.query(models.Transaction).filter(
        models.Transaction.payment_provider == 'dlocal_go',
        models.Transaction.provider_payment_id == payment['id'], models.Transaction.id != tx.id).first()
    if duplicate:
        raise PaymentUncertain('El pago ya está asignado a otra compra.')
    status = payment.get('status')
    if tx.status == 'FAILED' and status in ('REJECTED', 'CANCELLED', 'EXPIRED'):
        # A failed upgraded quote may already be released or reserved by a new
        # buyer. A verified duplicate rejection acknowledges only the old order.
        db.rollback()
        return
    if tx.buyer_id != ticket.buyer_id:
        raise PaymentUncertain('El pago no coincide con la reserva.')
    tx.provider_payment_id = payment['id']
    if tx.status in ('REFUNDED', 'REFUND_PENDING'):
        db.rollback()
        return
    if status in ('REJECTED', 'CANCELLED', 'EXPIRED'):
        if tx.status in ('PROCESSING', 'UNKNOWN'):
            tx.status = 'FAILED'
            tx.checkout_url = None
            release_failed_reward(db, tx)
        db.commit()
        return
    if status != 'PAID':
        db.commit()
        return
    if tx.status not in ('PROCESSING', 'UNKNOWN', 'SUCCEEDED'):
        raise PaymentUncertain('El pago requiere conciliación administrativa.')
    if tx.status != 'SUCCEEDED':
        if ticket.estado != models.TicketState.RESERVADA:
            raise PaymentUncertain('Pago recibido para una reserva que requiere revisión.')
        nominated = ticket.ticket_type == 'nominada'
        target = models.TicketState.PENDIENTE_RENOMINACION if nominated else models.TicketState.VENDIDA
        validate_ticket_transition(ticket.estado, target)
        ticket.estado = target
        ticket.reserved_until = None
        if nominated:
            ticket.renomination_deadline = min(datetime.now(timezone.utc) + timedelta(hours=24), utc(ticket.event_date))
            ticket.renomination_reminder_sent = False
        tx.status = 'SUCCEEDED'
        consume_reward(db, tx)
        try:
            approved = utc(datetime.fromisoformat(str(payment.get('approved_date', '')).replace('Z', '+00:00')))
            if approved > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError()
        except (ValueError, OverflowError):
            approved = datetime.now(timezone.utc)
        tx.approved_at = approved
        # Go's published availability: 7 days for cards, 48 business hours
        # for APMs. Keep APM conservatively at seven days until the account's
        # precise business-calendar availability is reconciled operationally.
        tx.available_after = approved + timedelta(days=7)
        ensure_review(db, tx, ticket)
        db.add(models.AuditLog(user_id=tx.buyer_id, action='PAYMENT_SUCCEEDED',
                              entity_type='ticket', entity_id=str(ticket.id)))
    # Only provider-reported PEN fees authorize a final seller amount. Never
    # overwrite the immutable amounts of a payout already sent to the bank.
    review = db.query(models.PurchaseReview).filter_by(transaction_id=tx.id).first()
    if not review or review.settlement_state in ('NONE', 'QUEUED', 'BLOCKED'):
        try:
            terms = json.loads(tx.payout_terms)
            fee = Decimal(money_cents(payment.get('balance_fee'))) / 100
            credited = Decimal(money_cents(payment.get('balance_amount'))) / 100
            if (payment.get('balance_currency') != 'PEN' or credited + fee != tx.amount_total
                    or fee > payin_estimate(tx.amount_total, terms)):
                raise ValueError()
            net, payout_fee = payout_amount(tx.amount_seller - fee, terms)
            if net < Decimal(terms['minimum']):
                raise ValueError()
            tx.payin_fee, tx.payout_fee = fee, payout_fee
            tx.provider_fee = fee + payout_fee
            tx.seller_net_amount = net
        except (ValueError, TypeError, KeyError, ArithmeticError, PaymentUncertain):
            tx.provider_fee = None
            tx.seller_net_amount = None
    db.commit()


def recover_payment(db, tx, provider):
    if tx.provider_payment_id:
        return provider.retrieve_payment(tx.provider_payment_id)
    buyer = db.get(models.User, tx.buyer_id)
    # Payment creation has no documented idempotency: search our immutable
    # order_id instead of sending another charge after a timeout.
    for page in range(10):
        result = provider.list_payments(buyer.email, page)
        rows = result.get('data') if isinstance(result, dict) else None
        if not isinstance(rows, list):
            raise PaymentUncertain('No se pudo conciliar la orden de cobro.')
        found = [p for p in rows if isinstance(p, dict) and str(p.get('order_id')) == str(tx.id)]
        if len(found) == 1:
            return provider.retrieve_payment(found[0]['id'])
        if found:
            raise PaymentUncertain('La orden de cobro requiere revisión.')
        if len(rows) < 20:
            break
    raise PaymentUncertain('La orden sigue pendiente de conciliación. No vuelvas a pagar.')


def reconcile_go_payments(db, provider):
    if not provider.configured():
        return
    ids = [x.id for x in db.query(models.Transaction).filter(
        models.Transaction.payment_provider == 'dlocal_go',
        or_(models.Transaction.status.in_(('PROCESSING', 'UNKNOWN')),
            and_(models.Transaction.status == 'SUCCEEDED', models.Transaction.provider_fee.is_(None)))
    ).order_by(models.Transaction.created_at).limit(100).all()]
    for transaction_id in ids:
        try:
            tx = db.get(models.Transaction, transaction_id)
            payment = recover_payment(db, tx, provider)
            db.rollback()
            reconcile_payment(db, transaction_id, payment)
        except Exception:
            db.rollback()
