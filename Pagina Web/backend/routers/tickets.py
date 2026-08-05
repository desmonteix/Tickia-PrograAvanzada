from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user
from ..qr_utils import validate_image_file, process_qr_image
from ..state_machine import validate_ticket_transition
from ..rate_limit import limiter
import uuid
from datetime import datetime, timezone
from typing import List

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

@router.get("", response_model=List[schemas.TicketResponse])
def list_tickets(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Devuelve las entradas disponibles con paginación, ordenadas por el motor de Boost"""
    if limit > 100:
        limit = 100
        
    from sqlalchemy import case
    now_utc = datetime.now(timezone.utc)
    
    tickets = db.query(models.Ticket).filter(
        models.Ticket.estado == models.TicketState.DISPONIBLE
    ).order_by(
        case(
            (models.Ticket.boosted_until > now_utc, 1),
            else_=0
        ).desc(),
        models.Ticket.boost_referral_clicks.desc(),
        models.Ticket.created_at.desc()
    ).offset(skip).limit(limit).all()
    
    return tickets

@router.post("/upload", response_model=schemas.TicketResponse)
@limiter.limit("5/minute")
async def upload_ticket(
    request: Request,
    file: UploadFile = File(...),
    price: float = Form(...),
    event_name: str = Form(...),
    zone: str = Form(...),
    is_nominated: bool = Form(...),
    is_renominated: bool = Form(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # SECURITY: Validar campos enviados por el frontend en el servidor (nunca confiar en el cliente)
    # El frontend no puede dictar valores fuera de estos rangos aunque modifique el request.
    PRICE_MIN = 1.0       # S/ 1 mínimo
    PRICE_MAX = 5_000.0   # S/ 5,000 máximo por entrada
    if not (PRICE_MIN <= price <= PRICE_MAX):
        raise HTTPException(
            status_code=422,
            detail=f"El precio debe estar entre S/ {PRICE_MIN:.0f} y S/ {PRICE_MAX:,.0f}."
        )
    if len(event_name.strip()) < 3 or len(event_name) > 200:
        raise HTTPException(status_code=422, detail="Nombre del evento inválido (3-200 caracteres).")
    if len(zone.strip()) < 1 or len(zone) > 100:
        raise HTTPException(status_code=422, detail="Zona inválida (1-100 caracteres).")
        
    # SECURITY: Anti-Evasion Moderation
    import re
    from datetime import datetime, timezone, timedelta
    
    forbidden_patterns = [
        r"(?i)(ig|instagram|fb|facebook|wa\.me|whatsapp|t\.me|telegram)[\s:-]*[a-zA-Z0-9_\.]+",
        r"@[a-zA-Z0-9_]+",
        r"(\+?51)?\s*9\d{2}\s*\d{3}\s*\d{3}", # Peruvian phone number format
        r"\d{9}" # 9 continuous digits (typical mobile phone)
    ]
    
    text_to_check = f"{event_name} {zone}"
    for pattern in forbidden_patterns:
        if re.search(pattern, text_to_check):
            # Penalize the user
            current_user.trust_score = 0
            current_user.banned_until = datetime.now(timezone.utc) + timedelta(days=7)
            db.commit()
            
            # Log the ban
            audit = models.AuditLog(
                user_id=current_user.id,
                action="USER_BANNED_EVASION",
                entity_type="user",
                entity_id=str(current_user.id),
                reason=f"Detected contact info sharing. Pattern matched.",
                ip_address=request.client.host if request.client else "unknown"
            )
            db.add(audit)
            db.commit()
            
            raise HTTPException(
                status_code=403,
                detail="Tu cuenta ha sido baneada por 7 días. Está estrictamente prohibido intentar vender entradas por fuera compartiendo datos de contacto."
            )
    # SECURITY: Límite de velocidad de negocio (Business Logic Rate Limiting)
    # Máximo 10 tickets por cuenta en un lapso de 24 horas para evitar saturación de bots o lavado.
    from datetime import datetime, timezone, timedelta
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    
    recent_tickets_count = db.query(models.Ticket).filter(
        models.Ticket.seller_id == current_user.id,
        models.Ticket.created_at >= yesterday
    ).count()
    
    if recent_tickets_count >= 10:
        raise HTTPException(
            status_code=429, 
            detail="Has superado el límite de 10 tickets publicados por día. Intenta de nuevo mañana."
        )
    file_bytes = await file.read()
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo excede el límite de 5MB")
        
    if not validate_image_file(file_bytes, file.content_type):
        raise HTTPException(status_code=400, detail="Formato de archivo inválido o manipulado")
        
    qr_result, error = process_qr_image(file_bytes)
    if error:
        raise HTTPException(status_code=400, detail=error)
        
    qr_hash = qr_result["hash"]
    
    # Prevenir deduplicación (Regla estricta)
    existing_active = db.query(models.Ticket).filter(
        models.Ticket.qr_hash_sha256 == qr_hash,
        models.Ticket.hash_estado == models.HashState.ACTIVO
    ).first()
    
    if existing_active:
        raise HTTPException(status_code=409, detail="Esta entrada ya se encuentra publicada y activa en la plataforma.")
        
    # Cifrar imagen con AES-256
    from ..qr_utils import encrypt_bytes_fernet
    from ..storage_utils import upload_encrypted_qr
    
    encrypted_bytes = encrypt_bytes_fernet(file_bytes)
    
    # Subir a Supabase Storage
    storage_path = f"tickets/encrypted_{uuid.uuid4()}.enc"
    encrypted_url = upload_encrypted_qr(storage_path, encrypted_bytes)
    
    ticket_type = "nominada" if is_nominated else "no_nominada"

    ticket = models.Ticket(
        seller_id=current_user.id,
        event_name=event_name,
        event_date=datetime.now(timezone.utc),
        zone=zone,
        ticketing_company="teleticket",
        ticket_type=ticket_type,
        is_renominated=is_renominated,
        price=price,
        estado=models.TicketState.DISPONIBLE,
        qr_hash_sha256=qr_hash,
        hash_estado=models.HashState.ACTIVO,
        qr_image_url_encrypted=encrypted_url
    )
    
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    
    # Audit Log
    db.add(models.AuditLog(
        user_id=current_user.id, action="TICKET_PUBLISHED", 
        entity_type="ticket", entity_id=str(ticket.id), new_state="DISPONIBLE"
    ))
    db.commit()
    
    return ticket

@router.post("/{ticket_id}/buy")
@limiter.limit("5/minute")
def buy_ticket(
    request: Request,
    ticket_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Módulo Transaccional: Bloqueo atómico con SELECT FOR UPDATE
    Implementación estricta de la especificación para evitar doble venta.
    """
    try:
        # Transacción corta: Solo reservar usando text() para queries raw o SQLAlchemy object
        # Usamos row-level lock
        ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).with_for_update().first()
        
        if not ticket:
            raise HTTPException(status_code=404, detail="Entrada no encontrada")
            
        if ticket.estado != models.TicketState.DISPONIBLE:
            raise HTTPException(status_code=409, detail="La entrada ya no está disponible")
            
        if ticket.seller_id == current_user.id:
            raise HTTPException(status_code=400, detail="No puedes comprar tu propia entrada")
            
        # SECURITY: Máquina de estados — validar transición antes de aplicarla
        validate_ticket_transition(ticket.estado, models.TicketState.RESERVADA)
        ticket.estado = models.TicketState.RESERVADA
        ticket.buyer_id = current_user.id
        
        # En postgres raw: NOW() + INTERVAL '10 minutes'. En Python:
        import datetime
        ticket.reserved_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=10)
        
        db.commit()
        
    except HTTPException:
        # Si es una excepción HTTP controlada, solo deshacemos la BD y la re-lanzamos
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print("ERROR EN RESERVA:", str(e))
        raise HTTPException(status_code=500, detail=f"Error de base de datos o servidor: {str(e)}")

    # DESPUÉS del commit (lock liberado), se debe iniciar el pago con Culqi.
    # En este punto se retorna el intent de pago al cliente.
    return {
        "status": "RESERVADA",
        "message": "Entrada reservada por 10 minutos. Proceda al pago.",
        "ticket_id": ticket.id,
        "price": ticket.price,
        "payment_provider": "culqi"
    }

@router.get("/me", response_model=List[schemas.TicketResponse])
def get_my_tickets(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Devuelve las entradas compradas por el usuario"""
    tickets = db.query(models.Ticket).filter(
        models.Ticket.buyer_id == current_user.id,
        models.Ticket.estado == models.TicketState.VENDIDA
    ).all()
    return tickets

@router.get("/{ticket_id}/qr")
def get_ticket_qr(
    ticket_id: uuid.UUID,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Devuelve la imagen original del QR desencriptada (Mock para el MVP)"""
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id,
        models.Ticket.buyer_id == current_user.id,
        models.Ticket.estado == models.TicketState.VENDIDA
    ).first()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="No tienes acceso a esta entrada")
        
    # Generar token HMAC de un solo uso
    import hmac
    import hashlib
    import os
    import secrets
    from datetime import datetime, timezone, timedelta
    
    # Buscamos la transacción correspondiente para atar el token
    tx = db.query(models.Transaction).filter(
        models.Transaction.ticket_id == ticket.id,
        models.Transaction.buyer_id == current_user.id,
        models.Transaction.status == "SUCCEEDED"
    ).first()
    
    if not tx:
        raise HTTPException(status_code=400, detail="No se encontró una transacción de pago exitosa.")
        
    secret = os.getenv("QR_HMAC_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Configuración de servidor incompleta")
        
    # Crear token único
    raw_token = secrets.token_hex(16)
    token_hash = hmac.new(
        secret.encode(),
        raw_token.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Guardar token en BD
    tx.download_token = token_hash
    tx.download_token_used = False
    tx.download_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.commit()
    
    # Construir URL
    download_url = f"/api/download/{token_hash}"
    
    return {
        "ticket_id": ticket.id,
        "qr_image_url": download_url,
        "hash": ticket.qr_hash_sha256,
        "message": "Enlace de descarga seguro generado exitosamente (válido por 15 minutos)."
    }

@router.post("/{ticket_id}/renominate")
async def renominate_ticket(
    ticket_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id,
        models.Ticket.seller_id == current_user.id
    ).first()
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    if ticket.estado != models.TicketState.PENDIENTE_RENOMINACION:
        raise HTTPException(status_code=400, detail="Ticket is not pending renomination")

    qr_hash, encrypted_path = await process_qr_image(file)
    
    existing_qr = db.query(models.Ticket).filter(
        models.Ticket.qr_hash_sha256 == qr_hash,
        models.Ticket.hash_estado == models.HashState.ACTIVO,
        models.Ticket.id != ticket.id
    ).first()
    if existing_qr:
        raise HTTPException(status_code=409, detail="El nuevo código QR ya ha sido vendido en la plataforma.")
        
    ticket.qr_hash_sha256 = qr_hash
    ticket.qr_image_url_encrypted = encrypted_path
    
    validate_ticket_transition(ticket.estado, models.TicketState.VENDIDA)
    ticket.estado = models.TicketState.VENDIDA
    
    db.add(models.AuditLog(
        user_id=current_user.id, action="TICKET_RENOMINATED", 
        entity_type="ticket", entity_id=str(ticket.id), new_state="VENDIDA"
    ))
    db.commit()
    return {"message": "Renominación exitosa. Entrada entregada al comprador."}

@router.get("/my-sales")
def get_my_sales(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    tickets = db.query(models.Ticket).filter(
        models.Ticket.seller_id == current_user.id,
        models.Ticket.estado.in_([models.TicketState.VENDIDA, models.TicketState.PENDIENTE_RENOMINACION])
    ).all()
    
    result = []
    for t in tickets:
        buyer_data = None
        if t.buyer_id:
            buyer = db.query(models.User).filter(models.User.id == t.buyer_id).first()
            if buyer:
                buyer_data = {"full_name": buyer.full_name or "Sin Nombre", "dni": buyer.dni or "Sin DNI"}
                
        result.append({
            "id": str(t.id),
            "event_name": t.event_name,
            "zone": t.zone,
            "price": t.price,
            "estado": t.estado.value,
            "renomination_deadline": t.renomination_deadline.isoformat() if t.renomination_deadline else None,
            "buyer": buyer_data
        })
    return result

@router.post("/{ticket_id}/track-visit")
def track_ticket_visit(ticket_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """
    Rastrea un clic/visita en el enlace de referido de una entrada.
    Esto otorga/extiende el 'Social Boost' automáticamente.
    (Endpoint público, sin autenticación requerida)
    """
    ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
        
    from datetime import timedelta
    now_utc = datetime.now(timezone.utc)
    
    ticket.boost_referral_clicks += 1
    ticket.boosted_until = now_utc + timedelta(hours=48)
    
    db.commit()
    return {"message": "Visita rastreada", "clicks": ticket.boost_referral_clicks}
