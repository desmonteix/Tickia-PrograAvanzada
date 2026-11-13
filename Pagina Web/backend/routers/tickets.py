import logging
import os
import re
from decimal import Decimal
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query
from sqlalchemy import case, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user
from ..qr_utils import MAX_FILE_BYTES, validate_image_file, process_qr_image, encrypt_bytes_fernet
from ..storage_utils import upload_encrypted_qr, delete_qr_file
from ..state_machine import validate_ticket_transition
from ..rate_limit import limiter
from ..money import amounts
from ..payment_provider import get_payment_provider
from ..post_purchase import review_deadline
from ..promotions import commission_rate_for, reserve_quote, qualify_seller_referral
from ..campaigns import require_operation

router = APIRouter(prefix="/api/tickets", tags=["tickets"])
logger = logging.getLogger(__name__)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def read_qr(file):
    data = file.file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "El archivo excede el límite de 5 MB.")
    if not validate_image_file(data, file.content_type):
        raise HTTPException(400, "Solo se admiten imágenes PNG o JPEG válidas.")
    result, error = process_qr_image(data)
    if error:
        raise HTTPException(400, error)
    return data, result["hash"]


def save_qr(data):
    path = "tickets/encrypted_" + str(uuid.uuid4()) + ".enc"
    try:
        return upload_encrypted_qr(path, encrypt_bytes_fernet(data))
    except Exception:
        logger.exception("No se pudo guardar el QR cifrado")
        raise HTTPException(503, "No se pudo guardar la entrada. Intenta de nuevo más tarde.")


def remove_orphan(path):
    try:
        delete_qr_file(path)
    except Exception:
        logger.warning("No se pudo limpiar un archivo QR huérfano")


@router.get("", response_model=list[schemas.TicketResponse])
def list_tickets(skip: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    return db.query(models.Ticket).join(models.User, models.Ticket.seller_id == models.User.id).options(joinedload(models.Ticket.seller)).filter(
        models.Ticket.estado == models.TicketState.DISPONIBLE,
        models.Ticket.event_date > now,
    ).order_by(
        models.User.rating.desc(),
        case((models.Ticket.boosted_until > now, 1), else_=0).desc(),
        models.Ticket.boost_referral_clicks.desc(), models.Ticket.created_at.desc(),
    ).offset(skip).limit(limit).all()


@router.post("/upload", response_model=schemas.TicketResponse)
@limiter.limit("5/minute")
def upload_ticket(
    request: Request, file: UploadFile = File(...),
    price: float = Form(...), event_name: str = Form(...), zone: str = Form(...),
    is_nominated: bool = Form(...), is_renominated: bool = Form(...),
    event_date: datetime = Form(...),
    event_end_date: datetime = Form(...),
    ticketing_company: Literal["teleticket", "joinnus"] = Form(...),
    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    published_at = datetime.now(timezone.utc)
    require_operation(db, 'publications')
    commission_rate = commission_rate_for(published_at, db)
    if not 3 <= price <= 5000 or Decimal(str(price)).as_tuple().exponent < -2:
        raise HTTPException(422, "El precio debe estar entre S/ 3 y S/ 5,000, con hasta dos decimales.")
    if os.getenv('PAYMENT_PROVIDER', 'culqi') == 'dlocal_go':
        from ..go_fees import fee_terms, payin_estimate, payout_amount
        from ..go_profiles import profile_ready
        from ..payment_provider import PaymentUnavailable
        try:
            terms = fee_terms()
            if not profile_ready(db.get(models.PayoutProfile, current_user.id), terms):
                raise HTTPException(409, 'Completa la verificación bancaria y acepta los cargos antes de vender.')
            total, _, seller = amounts(price, commission_rate)
            if payout_amount(seller - payin_estimate(total, terms), terms)[0] < Decimal(terms['minimum']):
                raise HTTPException(422, 'El precio no cubre los cargos y el mínimo de depósito de dLocal Go.')
        except PaymentUnavailable as exc:
            raise HTTPException(503, str(exc)) from None
    if not 3 <= len(event_name.strip()) <= 200 or not 1 <= len(zone.strip()) <= 100:
        raise HTTPException(422, "Verifica el nombre del evento y la zona.")
    contact_text = event_name + " " + zone
    if re.search(r"(?i)(?:instagram\.com|facebook\.com|wa\.me|t\.me)/|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\d)(?:\+51[ -]?)?9\d{2}[ -]?\d{3}[ -]?\d{3}(?!\d)", contact_text):
        raise HTTPException(422, "No incluyas datos de contacto en la publicación.")
    if event_date.tzinfo is None or event_date <= datetime.now(timezone.utc):
        raise HTTPException(422, "La fecha debe ser futura e incluir zona horaria.")
    if event_end_date.tzinfo is None or event_end_date <= event_date:
        raise HTTPException(422, 'La finalización debe ser posterior al inicio e incluir zona horaria.')
    if review_deadline(event_end_date) is None:
        raise HTTPException(422, 'La fecha de finalización está fuera del rango permitido.')
    if not is_nominated and is_renominated:
        raise HTTPException(422, "Una entrada no nominada no necesita renominación.")
    since = datetime.now(timezone.utc) - timedelta(days=1)
    count = db.query(models.Ticket).filter(
        models.Ticket.seller_id == current_user.id, models.Ticket.created_at >= since,
    ).count()
    if count >= 10:
        raise HTTPException(429, "Alcanzaste el límite diario de 10 entradas.")
    data, qr_hash = read_qr(file)
    if db.query(models.Ticket).filter(
        models.Ticket.qr_hash_sha256 == qr_hash, models.Ticket.hash_estado == models.HashState.ACTIVO,
    ).first():
        raise HTTPException(409, "Esta entrada ya está publicada y activa.")
    path = save_qr(data)
    ticket = models.Ticket(
        seller_id=current_user.id, event_name=event_name.strip(), event_date=event_date, event_end_date=event_end_date,
        zone=zone.strip(), ticketing_company=ticketing_company,
        ticket_type="nominada" if is_nominated else "no_nominada",
        is_renominated=is_renominated, price=price, created_at=published_at, commission_rate=commission_rate,
        estado=models.TicketState.DISPONIBLE, qr_hash_sha256=qr_hash,
        hash_estado=models.HashState.ACTIVO, qr_image_url_encrypted=path,
    )
    try:
        db.add(ticket)
        db.flush()
        qualify_seller_referral(db, ticket)
        db.add(models.AuditLog(
            user_id=current_user.id, action="TICKET_PUBLISHED", entity_type="ticket",
            entity_id=str(ticket.id), new_state="DISPONIBLE",
        ))
        db.commit()
        db.refresh(ticket)
    except IntegrityError:
        db.rollback()
        remove_orphan(path)
        raise HTTPException(409, "Esta entrada ya está publicada y activa.")
    except SQLAlchemyError:
        db.rollback()
        remove_orphan(path)
        raise HTTPException(503, "No se pudo publicar la entrada. Intenta de nuevo.")
    return ticket


@router.post("/{ticket_id}/buy")
@limiter.limit("5/minute")
def buy_ticket(request: Request, ticket_id: uuid.UUID, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_operation(db, 'purchases')
    if not get_payment_provider().enabled():
        raise HTTPException(503, "Los pagos aún no están habilitados. No se creó una reserva.")
    try:
        ticket = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).with_for_update().first()
        if not ticket:
            raise HTTPException(404, "Entrada no encontrada.")
        if ticket.estado != models.TicketState.DISPONIBLE:
            raise HTTPException(409, "La entrada ya no está disponible.")
        if ticket.seller_id == current_user.id:
            raise HTTPException(400, "No puedes comprar tu propia entrada.")
        if ticket.ticket_type == "nominada" and not (
            current_user.is_kyc_verified and current_user.full_name and current_user.dni
        ):
            raise HTTPException(403, "Las entradas nominadas requieren identidad verificada del comprador.")
        if utc(ticket.event_date) <= datetime.now(timezone.utc):
            raise HTTPException(409, "El evento ya comenzó.")
        validate_ticket_transition(ticket.estado, models.TicketState.RESERVADA)
        ticket.estado = models.TicketState.RESERVADA
        ticket.buyer_id = current_user.id
        ticket.reserved_until = datetime.now(timezone.utc) + timedelta(minutes=10)
        quote = reserve_quote(db, ticket, current_user.id)
        db.add(models.AuditLog(
            user_id=current_user.id, action="TICKET_RESERVED", entity_type="ticket",
            entity_id=str(ticket.id), previous_state="DISPONIBLE", new_state="RESERVADA",
        ))
        db.commit()
        return {
            "status": "RESERVADA", "ticket_id": str(ticket.id), "price": float(ticket.price),
            **quote,
            "reserved_until": utc(ticket.reserved_until).isoformat(), "payment_provider": os.getenv('PAYMENT_PROVIDER', 'culqi'),
        }
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("No se pudo reservar una entrada")
        raise HTTPException(503, "No se pudo reservar la entrada. Intenta de nuevo.")


@router.get("/me", response_model=list[schemas.TicketResponse])
def get_my_tickets(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Ticket).filter(
        models.Ticket.buyer_id == current_user.id,
        models.Ticket.estado.in_([
            models.TicketState.VENDIDA, models.TicketState.PENDIENTE_RENOMINACION,
            models.TicketState.LIBERADA, models.TicketState.REEMBOLSADA,
        ]),
    ).order_by(models.Ticket.created_at.desc()).all()


@router.get("/{ticket_id}/qr")
def get_ticket_qr(ticket_id: uuid.UUID, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id, models.Ticket.buyer_id == current_user.id,
        models.Ticket.estado.in_([models.TicketState.VENDIDA, models.TicketState.LIBERADA]),
    ).with_for_update().first()
    if not ticket:
        raise HTTPException(404, "No tienes acceso a esta entrada.")
    tx = db.query(models.Transaction).filter(
        models.Transaction.ticket_id == ticket.id, models.Transaction.buyer_id == current_user.id,
        models.Transaction.status == "SUCCEEDED",
    ).with_for_update().first()
    if not tx:
        raise HTTPException(409, "La compra no tiene un pago confirmado.")
    tx.download_token = secrets.token_urlsafe(32)
    tx.download_token_used = False
    tx.download_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.commit()
    return {
        "ticket_id": str(ticket.id), "qr_image_url": "/api/download/" + tx.download_token,
        "message": "Enlace de un solo uso válido por 15 minutos.",
    }


@router.post("/{ticket_id}/renominate")
@limiter.limit("5/minute")
def renominate_ticket(request: Request, ticket_id: uuid.UUID, file: UploadFile = File(...), current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    ticket = db.query(models.Ticket).filter(
        models.Ticket.id == ticket_id, models.Ticket.seller_id == current_user.id,
    ).with_for_update().first()
    if not ticket:
        raise HTTPException(404, "Entrada no encontrada.")
    if ticket.estado != models.TicketState.PENDIENTE_RENOMINACION:
        raise HTTPException(409, "La entrada no está pendiente de renominación.")
    if not ticket.renomination_deadline or utc(ticket.renomination_deadline) <= datetime.now(timezone.utc):
        raise HTTPException(409, "El plazo de renominación venció.")
    data, qr_hash = read_qr(file)
    if qr_hash == ticket.qr_hash_sha256:
        raise HTTPException(422, "Sube el QR nuevo emitido para el comprador.")
    if db.query(models.Ticket).filter(
        models.Ticket.qr_hash_sha256 == qr_hash, models.Ticket.hash_estado == models.HashState.ACTIVO,
        models.Ticket.id != ticket.id,
    ).first():
        raise HTTPException(409, "El QR ya corresponde a otra entrada.")
    path = save_qr(data)
    old_path = ticket.qr_image_url_encrypted
    ticket.qr_hash_sha256 = qr_hash
    ticket.qr_image_url_encrypted = path
    ticket.is_renominated = True
    validate_ticket_transition(ticket.estado, models.TicketState.VENDIDA)
    ticket.estado = models.TicketState.VENDIDA
    review = db.query(models.PurchaseReview).filter_by(ticket_id=ticket.id).with_for_update().first()
    if review:
        review.delivered_at = datetime.now(timezone.utc)
    db.add(models.AuditLog(
        user_id=current_user.id, action="TICKET_RENOMINATED", entity_type="ticket",
        entity_id=str(ticket.id), previous_state="PENDIENTE_RENOMINACION", new_state="VENDIDA",
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        remove_orphan(path)
        raise HTTPException(409, "El QR ya corresponde a otra entrada.")
    remove_orphan(old_path)
    return {"message": "Entrada renominada y disponible para el comprador."}


@router.get("/my-sales")
def get_my_sales(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    tickets = db.query(models.Ticket).options(joinedload(models.Ticket.buyer)).filter(models.Ticket.seller_id == current_user.id).all()
    transaction_by_ticket = {tx.ticket_id: tx for tx in db.query(models.Transaction).filter(
        models.Transaction.ticket_id.in_([ticket.id for ticket in tickets]),
        models.Transaction.status.in_(("PROCESSING", "UNKNOWN", "SUCCEEDED", "REFUND_PENDING", "REFUNDED")),
    ).all()} if tickets else {}
    reviews = {row.ticket_id: row for row in db.query(models.PurchaseReview).filter(
        models.PurchaseReview.ticket_id.in_([t.id for t in tickets])).all()} if tickets else {}
    return [{
        "id": str(ticket.id), "event_name": ticket.event_name, "zone": ticket.zone,
        "price": float(ticket.price), "estado": ticket.estado.value,
        'settlement_state': reviews[ticket.id].settlement_state if ticket.id in reviews else None,
        'settlement_error': reviews[ticket.id].settlement_error if ticket.id in reviews else None,
        'settlement_reference': reviews[ticket.id].settlement_reference if ticket.id in reviews else None,
        "commission_rate": float(transaction_by_ticket[ticket.id].commission_rate
            if ticket.id in transaction_by_ticket and transaction_by_ticket[ticket.id].commission_rate is not None
            else ticket.commission_rate),
        "listing_commission_rate": float(ticket.commission_rate),
        "estimated_seller_amount": float(transaction_by_ticket[ticket.id].amount_seller
            if ticket.id in transaction_by_ticket else amounts(ticket.price, ticket.commission_rate)[2]),
        "seller_net_amount": (float(transaction_by_ticket[ticket.id].seller_net_amount)
            if ticket.id in transaction_by_ticket and transaction_by_ticket[ticket.id].seller_net_amount is not None else None),
        "provider_fee": (float(transaction_by_ticket[ticket.id].provider_fee)
            if ticket.id in transaction_by_ticket and transaction_by_ticket[ticket.id].provider_fee is not None else None),
        "renomination_deadline": utc(ticket.renomination_deadline).isoformat() if ticket.renomination_deadline else None,
        "ticket_type": ticket.ticket_type, "is_renominated": ticket.is_renominated,
        "buyer": {"full_name": ticket.buyer.full_name, "dni": ticket.buyer.dni}
                 if ticket.buyer and ticket.estado == models.TicketState.PENDIENTE_RENOMINACION else None,
    } for ticket in tickets]


@router.post("/{ticket_id}/track-visit")
@limiter.limit("10/minute")
def track_ticket_visit(ticket_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    result = db.execute(update(models.Ticket).where(
        models.Ticket.id == ticket_id, models.Ticket.estado == models.TicketState.DISPONIBLE,
    ).values(
        boost_referral_clicks=models.Ticket.boost_referral_clicks + 1,
        boosted_until=datetime.now(timezone.utc) + timedelta(hours=48),
    ))
    if not result.rowcount:
        db.rollback()
        raise HTTPException(404, "Entrada no disponible.")
    db.commit()
    return {"message": "Visita registrada."}
