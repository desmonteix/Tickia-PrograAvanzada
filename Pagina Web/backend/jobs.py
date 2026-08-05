"""
Background Jobs de mantenimiento de seguridad.
- Libera reservas de entradas que llevan más de 10 minutos sin completar el pago.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from . import models
from .state_machine import validate_ticket_transition
import logging

logger = logging.getLogger(__name__)

def release_expired_reservations(db: Session):
    """
    Job que devuelve a DISPONIBLE las entradas que llevan más de 10 minutos en estado RESERVADA.
    Esto ocurre cuando el comprador abre el modal de Culqi pero no completa el pago.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    expired = db.query(models.Ticket).filter(
        models.Ticket.estado == models.TicketState.RESERVADA,
        models.Ticket.reserved_until < cutoff
    ).all()

    if not expired:
        return

    for ticket in expired:
        old_buyer = ticket.buyer_id
        # SECURITY: Validar transición mediante la máquina de estados
        try:
            validate_ticket_transition(ticket.estado, models.TicketState.DISPONIBLE)
        except Exception as e:
            logger.error(f"[SECURITY-JOB] No se puede liberar ticket {ticket.id}: {e}")
            continue
        ticket.estado = models.TicketState.DISPONIBLE
        ticket.buyer_id = None
        ticket.reserved_until = None

        db.add(models.AuditLog(
            user_id=old_buyer,
            action="RESERVATION_EXPIRED_AUTO_RELEASED",
            entity_type="ticket",
            entity_id=str(ticket.id),
            previous_state="RESERVADA",
            new_state="DISPONIBLE",
            reason="Reserva expirada (>10 min sin pago completado)"
        ))
        logger.info(f"[SECURITY-JOB] Entrada {ticket.id} liberada automáticamente por reserva expirada.")

    db.commit()
    logger.info(f"[SECURITY-JOB] {len(expired)} reserva(s) expirada(s) liberada(s).")

def check_renomination_deadlines(db: Session):
    """
    Job que verifica si los vendedores cumplieron el plazo para renominar una entrada.
    Otorga una extensión de 12h (con alerta) o penaliza y reembolsa si fallan.
    """
    now_utc = datetime.now(timezone.utc)
    expired = db.query(models.Ticket).filter(
        models.Ticket.estado == models.TicketState.PENDIENTE_RENOMINACION,
        models.Ticket.renomination_deadline < now_utc
    ).all()
    
    for ticket in expired:
        event_date_utc = ticket.event_date.replace(tzinfo=timezone.utc) if ticket.event_date.tzinfo is None else ticket.event_date
        
        if not ticket.renomination_reminder_sent and (now_utc + timedelta(hours=12)) < event_date_utc:
            # Otorgar extensión de 12 horas
            ticket.renomination_deadline = now_utc + timedelta(hours=12)
            ticket.renomination_reminder_sent = True
            db.add(models.AuditLog(
                user_id=ticket.seller_id, action="RENOMINATION_REMINDER_SENT",
                entity_type="ticket", entity_id=str(ticket.id),
                reason="Extensión de 12h otorgada"
            ))
            logger.info(f"[RENOMINATION-JOB] Ticket {ticket.id}: Extensión de 12h otorgada al vendedor.")
        else:
            # Penalizar y Reembolsar
            validate_ticket_transition(ticket.estado, models.TicketState.REEMBOLSADA)
            ticket.estado = models.TicketState.REEMBOLSADA
            
            # Penalizar al vendedor (Ban de 7 días)
            seller = db.query(models.User).filter(models.User.id == ticket.seller_id).first()
            if seller:
                seller.trust_score = 0
                seller.banned_until = now_utc + timedelta(days=7)
                
            db.add(models.AuditLog(
                user_id=ticket.seller_id, action="RENOMINATION_FAILED_PENALTY",
                entity_type="ticket", entity_id=str(ticket.id),
                reason="Plazo vencido, reembolsando al comprador y baneando vendedor", new_state="REEMBOLSADA"
            ))
            logger.info(f"[RENOMINATION-JOB] Ticket {ticket.id}: Vendedor falló. Reembolso ejecutado.")
            
    if expired:
        db.commit()
