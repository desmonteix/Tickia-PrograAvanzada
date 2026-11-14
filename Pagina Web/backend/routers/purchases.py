from datetime import datetime, timezone
import logging
import uuid

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, File, Form, UploadFile, Request, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user
from ..post_purchase import lock_review, can_respond, decide, utc
from ..qr_utils import encrypt_bytes_fernet, decrypt_bytes_fernet, validate_image_file, MAX_FILE_BYTES
from ..storage_utils import upload_encrypted_qr, download_encrypted_qr, delete_qr_file
from .admin import get_admin_user
from ..rate_limit import limiter

router = APIRouter(prefix='/api/purchases', tags=['purchases'])
logger = logging.getLogger(__name__)


def iso(value):
    return utc(value).isoformat() if value else None


def view(row, tx, ticket):
    result = schemas.TicketResponse.model_validate(ticket).model_dump(mode='json')
    available = can_respond(row, tx, ticket)
    return {**result, 'purchase_id': str(row.id), 'delivered_at': iso(row.delivered_at),
        'listed_amount': float(tx.listed_amount if tx.listed_amount is not None else tx.amount_total),
        'amount_paid': float(tx.amount_total), 'buyer_discount': float(tx.buyer_discount),
        'closes_at': iso(row.closes_at), 'review_state': row.review_state,
        'decision': row.decision, 'settlement_state': row.settlement_state,
        'settlement_error': row.settlement_error, 'can_confirm': available, 'can_report': available}


@router.get('')
def my_purchases(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(models.PurchaseReview, models.Transaction, models.Ticket).join(
        models.Transaction, models.Transaction.id == models.PurchaseReview.transaction_id,
    ).join(models.Ticket, models.Ticket.id == models.PurchaseReview.ticket_id).options(
        joinedload(models.Ticket.seller),
    ).filter(models.Transaction.buyer_id == current_user.id).order_by(models.Transaction.created_at.desc()).offset(skip).limit(limit).all()
    return [view(*row) for row in rows]


@router.post('/{purchase_id}/confirm')
@limiter.limit('10/minute')
def confirm(request: Request, purchase_id: uuid.UUID, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    row, tx, ticket = lock_review(db, purchase_id, current_user.id)
    if not can_respond(row, tx, ticket):
        raise HTTPException(409, 'La compra ya está cerrada, tiene un reclamo o está fuera de plazo.')
    decide(db, row, tx, ticket, 'CONFIRMED', current_user.id, 'Conformidad definitiva del comprador.')
    db.commit()
    return {'message': 'Confirmación registrada. El abono al vendedor está pendiente de ejecución.'}


@router.post('/{purchase_id}/dispute')
@limiter.limit('5/minute')
def dispute(request: Request, purchase_id: uuid.UUID, description: str = Form(..., min_length=10, max_length=4000), file: UploadFile = File(...), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if len(description.strip()) < 10:
        raise HTTPException(422, 'Describe el problema con al menos 10 caracteres.')
    row, tx, ticket = lock_review(db, purchase_id, current_user.id)
    if not can_respond(row, tx, ticket):
        raise HTTPException(409, 'El reclamo está fuera de plazo o la compra ya tiene una decisión.')
    data = file.file.read(MAX_FILE_BYTES + 1)
    if not validate_image_file(data, file.content_type):
        raise HTTPException(422, 'Adjunta evidencia PNG o JPG válida de hasta 5 MB.')
    try:
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[0] * image.shape[1] > 20_000_000:
            raise ValueError()
    except (cv2.error, ValueError):
        raise HTTPException(422, 'La imagen de evidencia no es válida.')
    path = 'disputes/' + uuid.uuid4().hex + '.enc'
    try:
        upload_encrypted_qr(path, encrypt_bytes_fernet(data))
    except Exception:
        raise HTTPException(503, 'No pudimos guardar la evidencia. El reclamo aún no fue presentado.')
    row.review_state = 'DISPUTED'
    row.dispute_text = description.strip()
    row.reported_at = datetime.now(timezone.utc)
    db.add(models.DisputeEvidence(review_id=row.id, storage_path=path, media_type=file.content_type))
    db.add(models.AuditLog(user_id=current_user.id, action='DISPUTE_OPENED', entity_type='purchase', entity_id=str(row.id), reason=description.strip()))
    try:
        db.commit()
    except Exception:
        db.rollback()
        try:
            delete_qr_file(path)
        except Exception:
            logger.warning('No se pudo limpiar evidencia huérfana de la compra %s', row.id)
        raise HTTPException(503, 'No pudimos registrar el reclamo. Inténtalo nuevamente.')
    return {'message': 'Reclamo presentado. El dinero permanece congelado durante la investigación.'}


@router.get('/evidence/{evidence_id}')
def evidence(evidence_id: uuid.UUID, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(models.DisputeEvidence, evidence_id)
    if not item:
        raise HTTPException(404, 'Evidencia no encontrada.')
    row = db.get(models.PurchaseReview, item.review_id)
    tx = db.get(models.Transaction, row.transaction_id)
    if not current_user.is_admin and current_user.id != tx.buyer_id:
        raise HTTPException(403, 'No tienes acceso a esta evidencia.')
    try:
        data = decrypt_bytes_fernet(download_encrypted_qr(item.storage_path))
    except Exception:
        raise HTTPException(503, 'No pudimos recuperar la evidencia.')
    return Response(data, media_type=item.media_type, headers={'Cache-Control': 'no-store, private', 'Content-Disposition': 'attachment; filename="evidencia.' + ('png' if item.media_type == 'image/png' else 'jpg') + '"'})


@router.get('/admin/cases')
def cases(admin=Depends(get_admin_user), db: Session = Depends(get_db)):
    rows = db.query(models.PurchaseReview, models.Transaction, models.Ticket).join(
        models.Transaction, models.Transaction.id == models.PurchaseReview.transaction_id,
    ).join(models.Ticket, models.Ticket.id == models.PurchaseReview.ticket_id).options(joinedload(models.Ticket.seller)).filter(
        or_(models.PurchaseReview.review_state == 'DISPUTED', and_(models.PurchaseReview.review_state == 'RESOLVED', models.PurchaseReview.settlement_state != 'SUCCEEDED')),
    ).order_by(models.PurchaseReview.reported_at).limit(100).all()
    evidence_by_review = {}
    for item in db.query(models.DisputeEvidence).filter(models.DisputeEvidence.review_id.in_([row[0].id for row in rows])).all():
        evidence_by_review.setdefault(item.review_id, []).append({'id': str(item.id), 'media_type': item.media_type})
    return [{**view(row, tx, ticket), 'description': row.dispute_text, 'reported_at': iso(row.reported_at),
        'evidence': evidence_by_review.get(row.id, [])} for row, tx, ticket in rows]


class Resolution(BaseModel):
    valid: StrictBool
    reason: str = Field(min_length=10, max_length=4000)


@router.post('/admin/{purchase_id}/resolve')
def resolve(purchase_id: uuid.UUID, body: Resolution, admin=Depends(get_admin_user), db: Session = Depends(get_db)):
    if len(body.reason.strip()) < 10:
        raise HTTPException(422, 'Explica la decisión con al menos 10 caracteres.')
    row, tx, ticket = lock_review(db, purchase_id)
    if row.review_state != 'DISPUTED':
        raise HTTPException(409, 'El reclamo ya fue resuelto o no está abierto.')
    decide(db, row, tx, ticket, 'VALID_CLAIM' if body.valid else 'INVALID_CLAIM', admin.id, body.reason.strip())
    db.commit()
    return {'message': 'Decisión registrada. La operación financiera está pendiente de confirmación.'}
