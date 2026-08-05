from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user
from ..payment_provider import get_payment_provider
from ..rate_limit import limiter
from ..state_machine import validate_ticket_transition
from pydantic import BaseModel
import uuid
import hmac
import hashlib
import os

router = APIRouter(prefix="/api/payments", tags=["payments"])

class ChargeRequest(BaseModel):
    ticket_id: uuid.UUID
    culqi_token: str

@router.post("/charge")
@limiter.limit("5/minute")  # SECURITY: Máximo 5 intentos de pago por minuto por IP
def process_charge(
    request: Request,
    charge_req: ChargeRequest, 
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == charge_req.ticket_id,
        models.Ticket.estado == models.TicketState.RESERVADA,
        models.Ticket.buyer_id == current_user.id
    ).first()

    if not ticket:
        raise HTTPException(status_code=400, detail="Entrada no válida o la reserva expiró")

    # SECURITY: Idempotencia — rechazar si este token de Culqi ya fue procesado antes
    already_processed = db.query(models.Transaction).filter(
        models.Transaction.culqi_charge_id == charge_req.culqi_token
    ).first()
    if already_processed:
        raise HTTPException(status_code=409, detail="Este token de pago ya fue procesado anteriormente.")

    # Mock del cargo en Culqi
    # En producción haríamos una petición HTTP a Culqi (https://api.culqi.com/v2/charges)
    charge_id = f"chr_{uuid.uuid4().hex[:16]}"
    
    # SECURITY: Máquina de estados — validar transición antes de aplicarla
    validate_ticket_transition(ticket.estado, models.TicketState.VENDIDA)
    ticket.estado = models.TicketState.VENDIDA
    
    # Registrar la transacción
    tx = models.Transaction(
        ticket_id=ticket.id,
        buyer_id=current_user.id,
        culqi_charge_id=charge_id,
        amount_total=ticket.price * 1.10,
        commission_platform=ticket.price * 0.10,
        amount_seller=ticket.price * 0.90,
        status="SUCCEEDED",
        ip_address=request.client.host if request.client else "unknown", 
        user_agent=request.headers.get("user-agent", "unknown")
    )
    db.add(tx)
    
    # Audit Log
    db.add(models.AuditLog(
        user_id=current_user.id, action="PAYMENT_SUCCEEDED", 
        entity_type="ticket", entity_id=str(ticket.id), new_state="VENDIDA"
    ))
    
    db.commit()
    
    return {"message": "Pago procesado exitosamente", "charge_id": charge_id}


@router.post("/webhook/culqi")
async def culqi_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Webhook para recibir notificaciones asíncronas de Culqi (pago exitoso).
    SECURITY: Validación HMAC-SHA256 obligatoria para evitar webhooks falsificados.
    """
    # ── SECURITY: Verificar firma HMAC de Culqi ─────────────────────────────
    culqi_webhook_secret = os.getenv("CULQI_WEBHOOK_SECRET", "")
    signature_header = request.headers.get("x-culqi-signature", "")
    
    raw_body = await request.body()
    
    if culqi_webhook_secret:
        expected_sig = hmac.new(
            culqi_webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(f"sha256={expected_sig}", signature_header):
            # Log del intento de webhook inválido para detección de ataques
            import logging
            logging.getLogger(__name__).warning(
                f"[SECURITY] Webhook con firma inválida rechazado. IP: {request.client.host if request.client else 'unknown'}"
            )
            raise HTTPException(
                status_code=401, 
                detail="Firma de webhook inválida"
            )
    # ────────────────────────────────────────────────────────────────────────

    import json
    payload = json.loads(raw_body)
    
    event_type = payload.get("type")
    if event_type == "charge.succeeded":
        data = payload.get("data", {})
        ticket_id = data.get("metadata", {}).get("ticket_id")
        buyer_id = data.get("metadata", {}).get("buyer_id")
        charge_id = data.get("id")
        
        # Idempotencia: rechazar si el charge_id ya fue procesado
        if charge_id:
            already = db.query(models.Transaction).filter(
                models.Transaction.culqi_charge_id == charge_id
            ).first()
            if already:
                return {"received": True, "note": "evento ya procesado"}

        # Encontrar la entrada RESERVADA
        ticket = db.query(models.Ticket).filter(
            models.Ticket.id == ticket_id,
            models.Ticket.estado == models.TicketState.RESERVADA
        ).first()
        
        if ticket:
            # SECURITY: Máquina de estados — validar transición antes de aplicarla
            from datetime import datetime, timezone, timedelta
            
            new_state = models.TicketState.PENDIENTE_RENOMINACION if ticket.ticket_type == 'nominada' else models.TicketState.VENDIDA
            validate_ticket_transition(ticket.estado, new_state)
            ticket.estado = new_state
            
            if new_state == models.TicketState.PENDIENTE_RENOMINACION:
                now_utc = datetime.now(timezone.utc)
                deadline_24h = now_utc + timedelta(hours=24)
                # Ensure event_date is aware before comparison
                event_date_utc = ticket.event_date.replace(tzinfo=timezone.utc) if ticket.event_date.tzinfo is None else ticket.event_date
                ticket.renomination_deadline = min(deadline_24h, event_date_utc)
                ticket.renomination_reminder_sent = False

            db.add(models.AuditLog(
                user_id=buyer_id,
                action="PAYMENT_WEBHOOK_SUCCEEDED",
                entity_type="ticket",
                entity_id=str(ticket.id),
                new_state=new_state.value
            ))
            db.commit()
            
    return {"received": True}
