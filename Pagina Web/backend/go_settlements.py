"""Durable, asynchronous Go payouts/refunds. No receipt is synthesized as paid."""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from . import models
from .dlocal_go import money_cents
from .go_profiles import refresh_profile
from .payment_provider import PaymentUnavailable, PaymentDeclined, PaymentUncertain
from .post_purchase import lock_review, finish_settlement, utc


def lock_operation(db, operation_id):
    item = db.get(models.FinancialOperation, operation_id)
    if item is None:
        raise PaymentUncertain('Operación no encontrada.')
    row, tx, ticket = lock_review(db, item.review_id)
    item = db.query(models.FinancialOperation).filter_by(id=operation_id).populate_existing().with_for_update().one()
    return item, row, tx, ticket


def _remember(db, operation_id, result):
    operation, _, _, _ = lock_operation(db, operation_id)
    if operation.status in ('SUCCEEDED', 'REJECTED'):
        db.rollback()
        return
    field = 'payout_id' if operation.kind == 'PAYOUT' else 'id'
    ref = result.get(field) if isinstance(result, dict) else None
    if (not isinstance(ref, str) or not ref or len(ref) > 128
            or (operation.provider_id and operation.provider_id != ref)):
        raise PaymentUncertain('No se pudo verificar la referencia financiera.')
    if operation.kind == 'PAYOUT' and (
        result.get('currency_to_pay') != 'PEN' or money_cents(result.get('amount')) != int(operation.amount * 100)):
        raise PaymentUncertain('El depósito no coincide con la orden.')
    operation.provider_id = ref
    operation.status = 'PENDING'
    operation.next_check_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    db.commit()


def _find_refund(db, operation, tx, provider):
    matches = []
    for page in range(10):
        result = provider.list_refunds(page)
        rows = result.get('data') if isinstance(result, dict) else None
        if not isinstance(rows, list):
            raise PaymentUncertain('No se pudo conciliar el reembolso.')
        for item in rows:
            if isinstance(item, dict) and (item.get('payment_id') == tx.provider_payment_id
                    or str(item.get('order_id')) == str(tx.id)):
                if item.get('currency') == 'PEN' and money_cents(item.get('amount')) == int(operation.amount * 100):
                    matches.append(item)
        if len(rows) < 20:
            break
    if len(matches) != 1:
        raise PaymentUncertain('Reembolso sin referencia inequívoca; requiere conciliación, no reenvío.')
    return matches[0]


def reconcile_go_operation(db, operation_id, provider):
    operation = db.get(models.FinancialOperation, operation_id)
    if not operation or operation.status in ('SUCCEEDED', 'REJECTED'):
        db.rollback()
        return
    tx = db.get(models.Transaction, db.get(models.PurchaseReview, operation.review_id).transaction_id)
    kind, ref = operation.kind, operation.provider_id
    if ref:
        result = provider.retrieve_payout(ref) if kind == 'PAYOUT' else provider.retrieve_refund(ref)
    elif kind == 'PAYOUT' and operation.payload:
        # The exact persisted body and key recover an uncertain creation using
        # Go's documented idempotency, never a new bank order/reference.
        result = provider.submit_payout(json.loads(operation.payload), str(operation.id))
        _remember(db, operation_id, result)
        ref = result['payout_id']
        result = provider.retrieve_payout(ref)
    elif kind == 'REFUND':
        result = _find_refund(db, operation, tx, provider)
        _remember(db, operation_id, result)
        ref = result['id']
        result = provider.retrieve_refund(ref)
    else:
        raise PaymentUncertain('La operación no tiene referencia verificable.')
    operation, row, tx, ticket = lock_operation(db, operation_id)
    if operation.status in ('SUCCEEDED', 'REJECTED'):
        db.rollback()
        return
    if not isinstance(result, dict):
        raise PaymentUncertain('Resultado financiero inválido.')
    valid = (money_cents(result.get('amount')) == int(operation.amount * 100))
    if kind == 'PAYOUT':
        saved = json.loads(operation.payload)
        valid = (valid and result.get('payout_id') == ref and result.get('currency_to_pay') == 'PEN'
                 and result.get('description') == saved['description']
                 and result.get('purpose') == saved['purpose'])
        # Go's own Help Center defines BOTH as credited, unlike dLocal v3.
        complete = result.get('status') in ('DELIVERED', 'COMPLETED')
    else:
        valid = (valid and result.get('id') == ref and result.get('currency') == 'PEN'
                 and (result.get('payment_id') == tx.provider_payment_id
                      or str(result.get('order_id')) == str(tx.id)))
        complete = result.get('status') == 'SUCCESS'
    if not valid:
        raise PaymentUncertain('Importe, moneda o referencia financiera no coinciden.')
    if complete:
        operation.status = 'SUCCEEDED'
        operation.error = None
        operation.provider_id = ref
        finish_settlement(db, row, tx, ticket, ref)
    elif result.get('status') in ('REJECTED', 'CANCELLED', 'FAILED'):
        operation.status = 'REJECTED'
        row.settlement_state = 'BLOCKED'
        row.settlement_error = 'El proveedor rechazó la operación. Requiere revisar los datos y autorizar un nuevo intento.'
        operation.error = row.settlement_error
        db.commit()
    else:
        operation.status = 'PENDING'
        operation.next_check_at = datetime.now(timezone.utc) + timedelta(minutes=1)
        row.settlement_state = 'PROCESSING'
        row.settlement_error = None
        db.commit()


def _submit(db, operation_id, provider):
    operation, row, tx, _ = lock_operation(db, operation_id)
    if operation.status != 'READY':
        db.rollback()
        return
    operation.status = 'SENDING'
    row.settlement_state = 'PROCESSING'
    operation.next_check_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    kind, payment_id, amount_cents = operation.kind, tx.provider_payment_id, int(operation.amount * 100)
    payload = json.loads(operation.payload) if operation.payload else None
    db.commit()  # Release locks before sending money; this intent survives crashes.
    try:
        if kind == 'PAYOUT':
            result = provider.submit_payout(payload, str(operation_id))
        else:
            result = provider.create_refund(payment_id, amount_cents)
        _remember(db, operation_id, result)
        reconcile_go_operation(db, operation_id, provider)
    except (PaymentUnavailable, PaymentDeclined):
        db.rollback()
        operation, row, _, _ = lock_operation(db, operation_id)
        if operation.status in ('SUCCEEDED', 'REJECTED'):
            db.rollback()
            return
        if operation.provider_id:
            operation.status = 'PENDING'  # A GET failure must not declare the preceding POST rejected.
            row.settlement_state = 'PROCESSING'
        else:
            operation.status = 'REJECTED'
            row.settlement_state = 'BLOCKED'
        row.settlement_error = 'La operación requiere revisar saldo, habilitación o datos bancarios con el proveedor.'
        operation.error = row.settlement_error
        db.commit()
    except Exception:
        db.rollback()
        operation, row, _, _ = lock_operation(db, operation_id)
        if operation.status not in ('SUCCEEDED', 'REJECTED'):
            operation.status = 'UNKNOWN'
            row.settlement_state = 'UNKNOWN'
            row.settlement_error = 'Resultado pendiente de conciliación. No repetir manualmente la transferencia.'
            operation.error = row.settlement_error
            db.commit()
        else:
            db.rollback()


def process_go_settlements(db, provider=None):
    if os.getenv('SETTLEMENT_ENABLED', 'false').lower() != 'true':
        return
    if provider is None:
        from .dlocal_go import DLocalGoProvider
        provider = DLocalGoProvider()
    if not provider.configured():
        return
    now = datetime.now(timezone.utc)
    pending = [x.id for x in db.query(models.FinancialOperation).filter(
        models.FinancialOperation.status.in_(('SENDING', 'PENDING', 'UNKNOWN')),
        or_(models.FinancialOperation.next_check_at.is_(None), models.FinancialOperation.next_check_at <= now)
    ).limit(100).all()]
    for operation_id in pending:
        try:
            # Claim a reconciliation lease so concurrent maintenance/webhooks can
            # only query or safely recover the same idempotent payout.
            operation, _, _, _ = lock_operation(db, operation_id)
            if operation.status in ('SUCCEEDED', 'REJECTED') or (operation.next_check_at and utc(operation.next_check_at) > now):
                db.rollback()
                continue
            operation.next_check_at = now + timedelta(minutes=2)
            db.commit()
            reconcile_go_operation(db, operation_id, provider)
        except Exception:
            db.rollback()
    ids = [x.id for x in db.query(models.PurchaseReview).join(models.Transaction,
        models.Transaction.id == models.PurchaseReview.transaction_id).filter(
        models.Transaction.payment_provider == 'dlocal_go', models.PurchaseReview.review_state == 'RESOLVED',
        models.PurchaseReview.settlement_state.in_(('QUEUED', 'BLOCKED')),
        or_(models.PurchaseReview.settlement_check_at.is_(None), models.PurchaseReview.settlement_check_at <= now)
    ).order_by(models.PurchaseReview.created_at).limit(100).all()]
    for review_id in ids:
        try:
            row, tx, ticket = lock_review(db, review_id)
            if row.settlement_state not in ('QUEUED', 'BLOCKED'):
                db.rollback()
                continue
            active = db.query(models.FinancialOperation).filter_by(review_id=review_id).filter(
                models.FinancialOperation.status != 'REJECTED').first()
            if active:
                db.rollback()
                if active.status == 'READY':
                    _submit(db, active.id, provider)
                continue
            rejected = db.query(models.FinancialOperation).filter_by(review_id=review_id, status='REJECTED').first()
            if rejected and row.settlement_state != 'QUEUED':
                db.rollback()
                continue
            refund = row.decision == 'VALID_CLAIM'
            if not refund:
                if (tx.provider_fee is None or tx.seller_net_amount is None or tx.seller_net_amount <= 0
                        or tx.amount_seller - tx.provider_fee != tx.seller_net_amount):
                    row.settlement_state = 'BLOCKED'
                    row.settlement_error = 'Falta conciliar los cargos reales en PEN con el tarifario aceptado.'
                    row.settlement_check_at = now + timedelta(minutes=15)
                    db.commit()
                    continue
                if not tx.available_after or utc(tx.available_after) > now:
                    row.settlement_state = 'BLOCKED'
                    row.settlement_error = 'El cobro todavía no cumplió el plazo de disponibilidad de dLocal Go.'
                    row.settlement_check_at = tx.available_after or now + timedelta(minutes=15)
                    db.commit()
                    continue
                seller_id = ticket.seller_id
                db.rollback()  # Do not hold the ticket lock during provider KYC lookup.
                profile = db.get(models.PayoutProfile, seller_id)
                if not profile:
                    raise PaymentUnavailable('Falta la cuenta bancaria verificada.')
                refresh_profile(db, profile, provider)
                if profile.status != 'VERIFIED':
                    raise PaymentUnavailable('El beneficiario debe completar la verificación de identidad.')
                row, tx, ticket = lock_review(db, review_id)
                if row.settlement_state not in ('QUEUED', 'BLOCKED'):
                    db.rollback()
                    continue
            operation_id = uuid.uuid4()
            bank_id = profile.bank_account_id if not refund else None
            amount = tx.amount_total if refund else tx.seller_net_amount
            payload = None
            if not refund:
                terms = json.loads(tx.payout_terms)
                payload = json.dumps({'bank_account_id': bank_id, 'transfer_amount': int(amount * 100) / 100,
                    'purpose': terms['purpose'], 'description': 'Tickia ' + str(operation_id),
                    'notification_url': provider.notification_url()})
            operation = models.FinancialOperation(id=operation_id, review_id=review_id,
                kind='REFUND' if refund else 'PAYOUT', amount=amount, bank_account_id=bank_id, payload=payload)
            db.add(operation)
            row.settlement_error = None
            db.commit()
            _submit(db, operation_id, provider)
        except Exception:
            db.rollback()
            row = db.get(models.PurchaseReview, review_id)
            if row and row.settlement_state in ('QUEUED', 'BLOCKED'):
                row.settlement_state = 'BLOCKED'
                row.settlement_error = 'No se pudo verificar la operación. Revisa la cuenta y la habilitación del proveedor.'
                row.settlement_check_at = now + timedelta(minutes=15)
                db.commit()
