"""Maintenance jobs. A refund is never reported as executed without confirmation."""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import exists
from sqlalchemy.orm import Session
from . import models
from .state_machine import validate_ticket_transition

logger = logging.getLogger(__name__)


def release_expired_reservations(db: Session):
    # reserved_until already includes the ten-minute window.
    in_flight = exists().where(
        models.Transaction.ticket_id == models.Ticket.id,
        models.Transaction.status.in_(("PROCESSING", "UNKNOWN", "SUCCEEDED")),
    )
    expired = db.query(models.Ticket).filter(
        models.Ticket.estado == models.TicketState.RESERVADA,
        models.Ticket.reserved_until <= datetime.now(timezone.utc), ~in_flight,
    ).with_for_update(skip_locked=True).all()
    for ticket in expired:
        old_buyer = ticket.buyer_id
        validate_ticket_transition(ticket.estado, models.TicketState.DISPONIBLE)
        ticket.estado = models.TicketState.DISPONIBLE
        ticket.buyer_id = None
        ticket.reserved_until = None
        db.add(models.AuditLog(
            user_id=old_buyer, action="RESERVATION_EXPIRED_AUTO_RELEASED", entity_type="ticket",
            entity_id=str(ticket.id), previous_state="RESERVADA", new_state="DISPONIBLE",
        ))
    if expired:
        db.commit()


def check_renomination_deadlines(db: Session):
    from .post_purchase import decide

    now = datetime.now(timezone.utc)
    expired = db.query(models.Ticket).filter(
        models.Ticket.estado == models.TicketState.PENDIENTE_RENOMINACION,
        models.Ticket.renomination_deadline <= now,
    ).with_for_update(skip_locked=True).all()
    for ticket in expired:
        tx = db.query(models.Transaction).filter(
            models.Transaction.ticket_id == ticket.id,
            models.Transaction.status.in_(("SUCCEEDED", "REFUND_PENDING")),
        ).with_for_update().first()
        if tx is None:
            continue
        # Lock order matches checkout, claims and settlement: ticket, transaction,
        # review. A prior durable decision must never be replaced or sent twice.
        review = db.query(models.PurchaseReview).filter_by(
            transaction_id=tx.id,
        ).with_for_update().first()
        if review is not None and (review.review_state == 'RESOLVED' or review.settlement_state != 'NONE'):
            continue
        if review is None:
            review = models.PurchaseReview(transaction_id=tx.id, ticket_id=ticket.id)
            db.add(review)
            db.flush()

        legacy_pending = tx.status == 'REFUND_PENDING'
        reason = ('Renominación no entregada dentro del plazo. '
                  'Reembolso completo requerido; no confirmado todavía.')
        decide(db, review, tx, ticket, 'VALID_CLAIM', reason=reason)
        if legacy_pending:
            # An old pending flag cannot prove whether an operator already sent
            # a refund. Surface it for reconciliation without blindly resending.
            review.settlement_state = 'UNKNOWN'
            review.settlement_error = 'Reembolso pendiente previo: conciliar con la pasarela antes de reenviar.'

        # The worker changes this to REFUNDED only after a verified receipt.
        tx.status = "REFUND_PENDING"
        tx.download_token = None
        if not legacy_pending:
            seller = db.get(models.User, ticket.seller_id)
            if seller:
                seller.trust_score = 0
                seller.banned_until = now + timedelta(days=7)
        db.add(models.AuditLog(
            user_id=ticket.seller_id, action="RENOMINATION_REFUND_REVIEW_REQUIRED",
            entity_type="ticket", entity_id=str(ticket.id),
            reason=reason,
        ))
        logger.error("Renominación vencida; reembolso pendiente de confirmación operativa")
    if expired:
        db.commit()
