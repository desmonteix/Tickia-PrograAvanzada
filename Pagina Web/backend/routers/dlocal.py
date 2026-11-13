"""Tickia's authenticated Go checkout, payout profile and signed webhooks."""
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..dependencies import get_current_user
from ..dlocal_go import DLocalGoProvider
from ..go_fees import fee_terms, payin_estimate, payout_amount
from ..go_profiles import identity_hash, account_hash, apply_beneficiary, refresh_profile, profile_ready, profile_view
from ..go_payments import reconcile_payment, recover_payment
from ..promotions import checkout_values, bind_reward, fail_transaction
from ..payment_provider import PaymentUnavailable, PaymentDeclined, PaymentUncertain
from ..post_purchase import utc, review_deadline
from ..qr_utils import encrypt_bytes_fernet
from ..rate_limit import limiter
from .admin import get_admin_user

router = APIRouter(prefix='/api/payments', tags=['dlocal-go'])


class RetryOperation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(min_length=10, max_length=1000)


@router.get('/admin/operations')
def list_operations(admin=Depends(get_admin_user), db: Session = Depends(get_db)):
    rows = db.query(models.FinancialOperation, models.PurchaseReview, models.Ticket).join(
        models.PurchaseReview, models.FinancialOperation.review_id == models.PurchaseReview.id).join(
        models.Ticket, models.PurchaseReview.ticket_id == models.Ticket.id).order_by(
        models.FinancialOperation.created_at.desc()).limit(100).all()
    return [{'operation_id': str(op.id), 'purchase_id': str(review.id), 'event_name': ticket.event_name,
             'kind': op.kind, 'status': op.status, 'provider_id': op.provider_id,
             'amount': float(op.amount), 'error': op.error,
             'can_retry': op.status == 'REJECTED' and review.settlement_state == 'BLOCKED'}
            for op, review, ticket in rows]


@router.post('/admin/operations/{operation_id}/retry')
@limiter.limit('5/minute')
def retry_operation(request: Request, operation_id: uuid.UUID, body: RetryOperation,
                    admin=Depends(get_admin_user), db: Session = Depends(get_db)):
    from ..go_settlements import lock_operation
    from ..dlocal_go import money_cents
    operation = db.get(models.FinancialOperation, operation_id)
    if not operation:
        raise HTTPException(404, 'Operación no encontrada.')
    if operation.status != 'REJECTED':
        raise HTTPException(409, 'Solo se puede reintentar un rechazo definitivo.')
    if not body.reason.strip() or len(body.reason.strip()) < 10:
        raise HTTPException(422, 'Indica el motivo de la revisión.')
    provider = get_go_provider()
    if not selected() or not provider.payouts_enabled():
        raise HTTPException(503, 'Los depósitos no están habilitados.')
    if operation.provider_id:
        try:
            result = (provider.retrieve_payout(operation.provider_id) if operation.kind == 'PAYOUT'
                      else provider.retrieve_refund(operation.provider_id))
            tx = db.get(models.Transaction, db.get(models.PurchaseReview, operation.review_id).transaction_id)
            matches = money_cents(result.get('amount')) == int(operation.amount * 100)
            if operation.kind == 'PAYOUT':
                saved = json.loads(operation.payload)
                matches = (matches and result.get('payout_id') == operation.provider_id
                    and result.get('currency_to_pay') == 'PEN' and result.get('description') == saved['description']
                    and result.get('purpose') == saved['purpose'])
            else:
                matches = (matches and result.get('id') == operation.provider_id and result.get('currency') == 'PEN'
                    and (result.get('payment_id') == tx.provider_payment_id or str(result.get('order_id')) == str(tx.id)))
            if not matches or result.get('status') not in ('REJECTED', 'CANCELLED', 'FAILED'):
                raise HTTPException(409, 'El proveedor no confirma el rechazo definitivo. Requiere conciliación.')
        except (PaymentUnavailable, PaymentDeclined, PaymentUncertain, ValueError, TypeError, KeyError):
            db.rollback()
            raise HTTPException(503, 'No se pudo confirmar el rechazo. No se enviará otra operación.') from None
    db.rollback()  # Provider lookup must not keep financial locks open.
    operation, review, _, _ = lock_operation(db, operation_id)
    active = db.query(models.FinancialOperation).filter(
        models.FinancialOperation.review_id == review.id, models.FinancialOperation.status != 'REJECTED').first()
    if operation.status != 'REJECTED' or review.settlement_state != 'BLOCKED' or active:
        db.rollback()
        raise HTTPException(409, 'La operación ya cambió o tiene otro intento en curso.')
    review.settlement_state = 'QUEUED'
    review.settlement_error = None
    review.settlement_check_at = None
    db.add(models.AuditLog(user_id=admin.id, action='GO_OPERATION_RETRY_AUTHORIZED',
        entity_type='financial_operation', entity_id=str(operation_id), reason=body.reason.strip()))
    db.commit()
    return {'queued': True}


def get_go_provider():
    return DLocalGoProvider()


def selected():
    return os.getenv('PAYMENT_PROVIDER', 'culqi') == 'dlocal_go'


class PayoutProfileRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    first_name: str = Field(min_length=1, max_length=80, pattern=r'^[^\x00-\x1f<>]+$')
    last_name: str = Field(min_length=1, max_length=80, pattern=r'^[^\x00-\x1f<>]+$')
    document_type: Literal['DNI', 'RUC']
    document: str = Field(pattern=r'^\d{8}(?:\d{3})?$')
    bank_code: str = Field(pattern=r'^\d{3}$')
    account_number: str = Field(pattern=r'^\d{20}$')
    account_type: Literal['SAVINGS', 'CHECKING']
    bank_branch: str | None = Field(default=None, max_length=20, pattern=r'^[A-Za-z0-9 -]*$')
    accept_fees: StrictBool
    fee_terms_hash: str = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def valid_identity(self):
        if (len(self.document) != (8 if self.document_type == 'DNI' else 11)
                or not self.account_number.startswith(self.bank_code)
                or not self.first_name.strip() or not self.last_name.strip()):
            raise ValueError('Revisa el documento, banco y CCI.')
        return self


class AcceptFees(BaseModel):
    model_config = ConfigDict(extra='forbid')
    accept_fees: StrictBool
    fee_terms_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


@router.get('/payout-profile')
@limiter.limit('15/minute')
def get_profile(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    provider = get_go_provider()
    if not selected():
        return profile_view(None, provider, required=False)
    profile = db.get(models.PayoutProfile, user.id)
    error = None
    if profile:
        try:
            refresh_profile(db, profile, provider)
        except (PaymentUnavailable, PaymentDeclined, PaymentUncertain):
            db.rollback()
            error = 'No se pudo comprobar la verificación bancaria. Consulta de nuevo antes de vender.'
    return profile_view(profile, provider, error=error)


@router.post('/payout-profile')
@limiter.limit('5/minute')
def create_profile(request: Request, body: PayoutProfileRequest, user=Depends(get_current_user), db: Session = Depends(get_db)):
    provider = get_go_provider()
    if not selected() or not provider.configured():
        raise HTTPException(503, 'La vinculación bancaria de dLocal Go no está configurada.')
    if not body.accept_fees:
        raise HTTPException(422, 'Debes aceptar los cargos informados para continuar.')
    try:
        terms = fee_terms()
    except PaymentUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    if body.fee_terms_hash != terms['hash']:
        raise HTTPException(409, 'Los cargos cambiaron. Revisa el tarifario antes de aceptar.')
    if db.get(models.PayoutProfile, user.id):
        raise HTTPException(409, 'Ya existe un perfil. Consulta su estado; no repitas el registro. Para cambiar de banco solicita revisión.')
    payload = {'flow_type': 'B2C', 'first_name': body.first_name.strip(), 'last_name': body.last_name.strip(),
               'document': body.document, 'document_type': body.document_type,
               'country': 'PE', 'email': user.email, 'relationship': 'OTHER',
               'notification_url': provider.notification_url(),
               'bank_account': {'country': 'PE', 'currency': 'PEN', 'bank_code': body.bank_code,
                                'bank_account': body.account_number, 'account_type': body.account_type,
                                'preferred': True}}
    if body.bank_branch:
        payload['bank_account']['bank_branch'] = body.bank_branch
    profile = models.PayoutProfile(user_id=user.id, status='CREATING', account_last4=body.account_number[-4:],
        identity_hash=identity_hash(payload), account_hash=account_hash(payload['bank_account']),
        request_encrypted=encrypt_bytes_fernet(json.dumps(payload).encode()).decode('ascii'),
        fee_terms_hash=terms['hash'])
    db.add(profile)
    db.add(models.AuditLog(user_id=user.id, action='PAYOUT_FEES_ACCEPTED', entity_type='user',
                          entity_id=str(user.id), reason=terms['hash']))
    try:
        db.commit()  # Durable ownership before sending non-idempotent registration.
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'La identidad ya tiene un registro bancario. Solicita revisión.') from None
    try:
        data = provider.create_beneficiary(payload)
        apply_beneficiary(profile, data, user.email)
        db.commit()
    except PaymentDeclined as exc:
        db.rollback()
        profile = db.get(models.PayoutProfile, user.id)
        if exc.http_status != 409:
            db.delete(profile)
            db.add(models.AuditLog(user_id=user.id, action='PAYOUT_PROFILE_REJECTED',
                entity_type='user', entity_id=str(user.id), reason='El proveedor rechazó el registro antes de crearlo.'))
            db.commit()
            raise HTTPException(422, 'El proveedor rechazó los datos del registro. Revisa los datos bancarios antes de intentarlo de nuevo.') from None
        profile.status = 'UNKNOWN'
        profile.error = 'La identidad ya está registrada en el proveedor. Consulta para conciliarla sin duplicarla.'
        db.commit()
    except (PaymentUnavailable, PaymentUncertain):
        db.rollback()
        profile = db.get(models.PayoutProfile, user.id)
        profile.status = 'UNKNOWN'
        profile.error = 'Registro pendiente de conciliación. Consulta el estado; no vuelvas a enviar los datos.'
        db.commit()
    return profile_view(profile, provider)


@router.post('/payout-profile/accept-fees')
@limiter.limit('5/minute')
def accept_fees(request: Request, body: AcceptFees, user=Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(models.PayoutProfile).filter_by(user_id=user.id).with_for_update().first()
    if not profile or not body.accept_fees:
        raise HTTPException(422, 'Se requiere un perfil y la aceptación de los cargos.')
    try:
        terms = fee_terms()
    except PaymentUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    if body.fee_terms_hash != terms['hash']:
        raise HTTPException(409, 'Los cargos cambiaron. Revisa el tarifario antes de aceptar.')
    profile.fee_terms_hash = terms['hash']
    db.add(models.AuditLog(user_id=user.id, action='PAYOUT_FEES_ACCEPTED', entity_type='user',
                          entity_id=str(user.id), reason=terms['hash']))
    db.commit()
    return profile_view(profile, get_go_provider())


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ticket_id: uuid.UUID
    reservation_id: uuid.UUID | None = None


def checkout_view(tx):
    return {'transaction_id': str(tx.id), 'status': tx.status, 'redirect_url': tx.checkout_url,
            'amount_total': float(tx.amount_total), 'buyer_discount': float(tx.buyer_discount),
            'listed_amount': float(tx.listed_amount if tx.listed_amount is not None else tx.amount_total),
            'commission_rate': float(tx.commission_rate) if tx.commission_rate is not None else None}


@router.post('/checkout')
@limiter.limit('5/minute')
def checkout(request: Request, body: CheckoutRequest, user=Depends(get_current_user), db: Session = Depends(get_db)):
    from ..campaigns import require_operation
    require_operation(db, 'purchases')
    provider = get_go_provider()
    if not selected() or not provider.enabled() or not provider.payouts_enabled():
        raise HTTPException(503, 'Los cobros y depósitos de dLocal Go todavía no están habilitados.')
    try:
        terms = fee_terms()
        ticket = db.query(models.Ticket).filter_by(id=body.ticket_id).with_for_update().first()
        if not ticket or ticket.buyer_id != user.id:
            raise HTTPException(404, 'Reserva no encontrada.')
        previous = db.query(models.Transaction).filter(models.Transaction.ticket_id == ticket.id,
            models.Transaction.status.in_(('PROCESSING', 'UNKNOWN', 'SUCCEEDED', 'REFUND_PENDING', 'REFUNDED'))).first()
        if previous:
            if previous.buyer_id == user.id and previous.payment_provider == 'dlocal_go':
                return checkout_view(previous)
            raise HTTPException(409, 'La compra ya está en proceso. No vuelvas a pagar.')
        if (ticket.estado != models.TicketState.RESERVADA or not ticket.reserved_until
                or utc(ticket.reserved_until) <= datetime.now(timezone.utc)
                or utc(ticket.event_date) <= datetime.now(timezone.utc)):
            raise HTTPException(409, 'La reserva venció. Vuelve a seleccionar la entrada.')
        if ticket.ticket_type == 'nominada' and not (user.is_kyc_verified and user.full_name and user.dni):
            raise HTTPException(403, 'La compra nominada requiere identidad verificada.')
        if ticket.event_end_date is None or review_deadline(ticket.event_end_date) is None:
            raise HTTPException(422, 'Falta una fecha de finalización válida antes de cobrar.')
        profile = db.get(models.PayoutProfile, ticket.seller_id)
        if not profile_ready(profile, terms):
            raise HTTPException(409, 'El vendedor debe completar su verificación bancaria y aceptar los cargos.')
        refresh_profile(db, profile, provider)
        # Refresh commits outside the provider call; reacquire the reservation.
        ticket = db.query(models.Ticket).filter_by(id=body.ticket_id).populate_existing().with_for_update().one()
        if (ticket.buyer_id != user.id or ticket.estado != models.TicketState.RESERVADA
                or not ticket.reserved_until or utc(ticket.reserved_until) <= datetime.now(timezone.utc)
                or utc(ticket.event_date) <= datetime.now(timezone.utc) or not profile_ready(profile, terms)):
            raise HTTPException(409, 'La reserva o la verificación del vendedor cambió.')
        pricing = checkout_values(db, ticket, user.id, body.reservation_id)
        total, seller = pricing['amount_total'], pricing['amount_seller']
        net, _ = payout_amount(seller - payin_estimate(total, terms), terms)
        if net < Decimal(terms['minimum']):
            raise HTTPException(422, 'El precio no cubre los cargos y el mínimo de depósito del proveedor.')
        tx = models.Transaction(ticket_id=ticket.id, buyer_id=user.id, payment_provider='dlocal_go',
            **pricing,
            fee_terms_hash=terms['hash'], payout_terms=json.dumps(terms), status='PROCESSING')
        db.add(tx)
        bind_reward(db, tx)
        db.commit()
        transaction_id = tx.id
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'La compra ya está en proceso. No vuelvas a pagar.') from None
    except (PaymentUnavailable, PaymentUncertain, PaymentDeclined) as exc:
        db.rollback()
        raise HTTPException(503, str(exc)) from None
    try:
        result = provider.create_checkout(str(transaction_id), int(total * 100), user.email)
        tx = db.query(models.Transaction).filter_by(id=transaction_id).populate_existing().with_for_update().one()
        if tx.status in ('PROCESSING', 'UNKNOWN'):
            tx.provider_payment_id = result['id']
            tx.checkout_url = result['redirect_url']
        db.commit()
    except (PaymentUnavailable, PaymentDeclined):
        db.rollback()
        released = fail_transaction(db, transaction_id)
        db.commit()
        return JSONResponse(status_code=402, content={
            'detail': 'El proveedor rechazó la creación del pago. No se confirmó ningún cobro; revisa los datos o solicita atención.',
            'reservation_released': released})
    except (PaymentUncertain, IntegrityError):
        db.rollback()
        db.query(models.Transaction).filter_by(id=transaction_id, status='PROCESSING').update({'status': 'UNKNOWN'})
        db.commit()
        # Keep the durable order visible even when checkout creation timed out.
        # 202 acknowledges tracking, never successful payment or delivery.
        tx = db.get(models.Transaction, transaction_id)
        return JSONResponse(status_code=202, content=checkout_view(tx))
    return checkout_view(tx)


@router.get('/transactions/{transaction_id}')
@limiter.limit('30/minute')
def transaction_status(request: Request, transaction_id: uuid.UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    tx = db.get(models.Transaction, transaction_id)
    if not tx or tx.buyer_id != user.id:
        raise HTTPException(404, 'Compra no encontrada.')
    if tx.payment_provider == 'dlocal_go' and (tx.status in ('PROCESSING', 'UNKNOWN')
                                               or (tx.status == 'SUCCEEDED' and tx.provider_fee is None)):
        try:
            data = recover_payment(db, tx, get_go_provider())
            db.rollback()
            reconcile_payment(db, transaction_id, data)
        except (PaymentUnavailable, PaymentDeclined, PaymentUncertain, IntegrityError):
            db.rollback()
        tx = db.get(models.Transaction, transaction_id)
    return {'transaction_id': str(tx.id), 'ticket_id': str(tx.ticket_id), 'status': tx.status,
            'provider': tx.payment_provider}


@router.post('/webhooks/dlocal-go')
@limiter.limit('120/minute')
async def webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if len(raw) > 65536:
        raise HTTPException(413, 'Notificación demasiado grande.')
    provider = get_go_provider()
    if not provider.verify_notification(raw, request.headers.get('authorization')):
        raise HTTPException(401, 'Firma de notificación no válida.')
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError()
        if 'payment_id' in payload:
            payment = provider.retrieve_payment(payload['payment_id'])
            transaction_id = uuid.UUID(str(payment.get('order_id')))
            tx = db.get(models.Transaction, transaction_id)
            if not tx or tx.payment_provider != 'dlocal_go':
                raise ValueError()
            db.rollback()
            reconcile_payment(db, transaction_id, payment)
        elif 'beneficiary_id' in payload:
            profile = db.query(models.PayoutProfile).filter_by(beneficiary_id=str(payload['beneficiary_id'])).first()
            if profile:
                refresh_profile(db, profile, provider)
        elif 'payout_id' in payload or 'refund_id' in payload:
            from ..go_settlements import reconcile_go_operation
            ref = payload.get('payout_id') or payload.get('refund_id')
            operation = db.query(models.FinancialOperation).filter_by(provider_id=str(ref)).first()
            if operation:
                reconcile_go_operation(db, operation.id, provider)
        else:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        db.rollback()
        raise HTTPException(400, 'La notificación no corresponde a una operación de Tickia.') from None
    except (PaymentUnavailable, PaymentDeclined, PaymentUncertain, IntegrityError):
        db.rollback()
        raise HTTPException(503, 'La notificación sigue pendiente de conciliación.') from None
    return {'received': True}
