"""Optional campaigns and immutable, one-use financial rewards.

Lock order: ticket, transaction, then participating rewards in UUID order.
A reward bound to an uncertain money operation never expires by a timer.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import os
import re
import secrets
import uuid

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from . import models
from .campaigns import active_campaign, settings_view, REGULAR_COMMISSION
from .money import amounts
from .payment_provider import PaymentUncertain

START = datetime(2026, 11, 13, 5, tzinfo=timezone.utc)
END = datetime(2026, 12, 13, 5, tzinfo=timezone.utc)
CODE_PATTERN = re.compile(r'^[A-Za-z0-9_-]{6,64}$')


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def in_launch_window(instant, starts_at=START, ends_at=END):
    return utc(starts_at) <= utc(instant) < utc(ends_at)


def commission_rate_for(instant, db):
    campaign = active_campaign(db, instant)
    return campaign.listing_commission_rate if campaign else REGULAR_COMMISSION


def campaign_view(db):
    campaign = active_campaign(db)
    shown = campaign or db.query(models.PromotionCampaign).filter_by(enabled=True, archived=False).filter(
        models.PromotionCampaign.starts_at > datetime.now(timezone.utc)).order_by(models.PromotionCampaign.starts_at).first()
    return {'starts_at': utc(shown.starts_at).isoformat() if shown else None,
            'ends_at': utc(shown.ends_at).isoformat() if shown else None, 'timezone': 'America/Lima',
            'active': bool(campaign), 'current_commission_rate': float(campaign.listing_commission_rate if campaign else REGULAR_COMMISSION),
            'regular_commission_rate': float(REGULAR_COMMISSION),
            'launch_commission_rate': float(shown.listing_commission_rate) if shown else None,
            'referral_discount_rate': float(shown.registration_discount_rate) if shown else 0,
            'seller_referral_discount_rate': float(shown.seller_buyer_discount_rate) if shown else 0,
            'seller_referral_commission_rate': float(shown.seller_commission_rate) if shown else None,
            'referral_reward_expires': False, 'settings': settings_view(db)}


def ensure_referral_code(db, user_id):
    user = db.get(models.User, user_id)
    if user.referral_code and CODE_PATTERN.fullmatch(user.referral_code):
        return user.referral_code
    user = db.query(models.User).filter_by(id=user_id).populate_existing().with_for_update().one()
    if not user.referral_code or not CODE_PATTERN.fullmatch(user.referral_code):
        user.referral_code = secrets.token_urlsafe(12)
    code = user.referral_code
    db.commit()  # No reward lock while changing a unique user key.
    return code


def apply_upgrade(reward, data):
    reward.campaign_id = uuid.UUID(data['campaign_id']) if data.get('campaign_id') else None
    reward.buyer_discount_rate = Decimal(data['buyer_discount_rate'])
    reward.seller_commission_rate = Decimal(data['seller_commission_rate'])
    reward.reward_kind, reward.choice, reward.pending_upgrade = 'SELLER_REFERRAL', None, None


def grant_reward(db, user_id, campaign, seller=False):
    now = datetime.now(timezone.utc)
    insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
    db.execute(insert(models.ReferralReward).values(user_id=user_id, earned_at=now,
        campaign_id=campaign.id, reward_kind='REGISTRATION', buyer_discount_rate=campaign.registration_discount_rate,
        choice='BUY').on_conflict_do_nothing(index_elements=['user_id']))
    reward = db.query(models.ReferralReward).filter_by(user_id=user_id).populate_existing().with_for_update().one()
    expire_hold(reward)
    if not seller or reward.used_transaction_id or reward.revoked_at or reward.reward_kind != 'REGISTRATION':
        return
    data = dict(campaign_id=str(campaign.id), buyer_discount_rate=str(campaign.seller_buyer_discount_rate),
                seller_commission_rate=str(campaign.seller_commission_rate))
    if reward.reserved_ticket_id:
        reward.pending_upgrade = json.dumps(data)  # Preserve an already accepted quote.
    else:
        apply_upgrade(reward, data)


def record_referral(db, new_user, code):
    if not code:
        return
    referrer = db.query(models.User).filter_by(referral_code=code).first()
    if not referrer or referrer.id == new_user.id or referrer.is_suspended:
        raise HTTPException(422, 'El código de referido no es válido.')
    campaign = active_campaign(db)
    db.add(models.Referral(referred_user_id=new_user.id, referrer_id=referrer.id,
                           qualified=bool(campaign), created_at=datetime.now(timezone.utc)))
    if campaign and campaign.registration_discount_rate > 0:
        grant_reward(db, referrer.id, campaign)
    db.add(models.AuditLog(user_id=referrer.id, action='REFERRAL_REGISTERED', entity_type='user',
                          entity_id=str(new_user.id), reason='qualified' if campaign else 'outside_campaign'))


def qualify_seller_referral(db, ticket):
    referral = db.query(models.Referral).filter_by(referred_user_id=ticket.seller_id).populate_existing().with_for_update().first()
    if not referral or referral.seller_ticket_id:
        return
    earlier = db.query(models.Ticket.id).filter(models.Ticket.seller_id == ticket.seller_id,
                                               models.Ticket.id != ticket.id).first()
    referral.seller_ticket_id = earlier[0] if earlier else ticket.id
    campaign = active_campaign(db, ticket.created_at)
    if earlier or not campaign:
        return
    referrer = db.get(models.User, referral.referrer_id)
    if referrer.is_suspended:
        return
    referral.seller_qualified_at = ticket.created_at
    grant_reward(db, referrer.id, campaign, seller=True)
    db.add(models.AuditLog(user_id=referrer.id, action='SELLER_REFERRAL_QUALIFIED',
                          entity_type='ticket', entity_id=str(ticket.id)))


def clear_hold(reward):
    reward.reserved_ticket_id = reward.reserved_transaction_id = reward.reserved_until = None
    if reward.pending_upgrade and not reward.used_transaction_id and not reward.revoked_at:
        apply_upgrade(reward, json.loads(reward.pending_upgrade))


def expire_hold(reward):
    if (reward and reward.used_transaction_id is None and reward.reserved_transaction_id is None
            and reward.reserved_until is not None and utc(reward.reserved_until) <= datetime.now(timezone.utc)):
        clear_hold(reward)


def reward_state(reward):
    return ('NOT_EARNED' if reward is None else 'USED' if reward.used_transaction_id else 'REVOKED' if reward.revoked_at
            else 'RESERVED' if reward.reserved_ticket_id else 'AVAILABLE')


def reward_fields(reward):
    return {'reward_status': reward_state(reward), 'discount_rate': float(reward.buyer_discount_rate) if reward else 0,
            'seller_commission_rate': float(reward.seller_commission_rate) if reward and reward.seller_commission_rate is not None else None,
            'choice': reward.choice if reward else None, 'reward_kind': reward.reward_kind if reward else None,
            'pending_upgrade': bool(reward and reward.pending_upgrade),
            'reserved_ticket_id': str(reward.reserved_ticket_id) if reward and reward.reserved_ticket_id else None,
            'reserved_until': utc(reward.reserved_until).isoformat() if reward and reward.reserved_until else None}


def reward_view(db, user_id):
    code = ensure_referral_code(db, user_id)
    reward = db.query(models.ReferralReward).filter_by(user_id=user_id).populate_existing().with_for_update().first()
    expire_hold(reward)
    result = {'referral_code': code, 'invite_path': '/?ref=' + code + '#login',
              'qualifying_referral_count': db.query(models.Referral).filter_by(referrer_id=user_id, qualified=True).count(),
              'qualifying_seller_count': db.query(models.Referral).filter(models.Referral.referrer_id == user_id,
                  models.Referral.seller_qualified_at.is_not(None)).count(), **reward_fields(reward), 'campaign': campaign_view(db)}
    db.commit()
    return result


def reward_rows(db, ticket, buyer_id):
    return db.query(models.ReferralReward).filter(or_(models.ReferralReward.reserved_ticket_id == ticket.id,
        models.ReferralReward.user_id.in_([buyer_id, ticket.seller_id]))).order_by(
        models.ReferralReward.user_id).populate_existing().with_for_update().all()


def hold(reward, ticket):
    if reward.reserved_ticket_id and reward.reserved_ticket_id != ticket.id:
        raise HTTPException(409, 'El beneficio está reservado en otra operación. Retómala o espera a que termine su reserva.')
    if reward.reserved_transaction_id:
        raise HTTPException(409, 'El beneficio está vinculado a un pago pendiente de confirmación.')
    reward.reserved_ticket_id, reward.reserved_until = ticket.id, ticket.reserved_until


def reserve_quote(db, ticket, buyer_id):
    rows = reward_rows(db, ticket, buyer_id)
    for row in rows:
        expire_hold(row)
    db.flush()
    if any(row.user_id not in (buyer_id, ticket.seller_id) and row.reserved_ticket_id == ticket.id for row in rows):
        raise HTTPException(409, 'La entrada aún está vinculada a otro beneficio en proceso.')
    buyer_rate, rate, seller_reward_id = Decimal('0'), ticket.commission_rate, None
    for reward in rows:
        if reward.used_transaction_id or reward.revoked_at:
            continue
        if reward.user_id == buyer_id and reward.choice == 'BUY':
            buyer_rate = reward.buyer_discount_rate
            if (ticket.price * buyer_rate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP):
                hold(reward, ticket)
        if (reward.user_id == ticket.seller_id and reward.choice == 'SELL' and reward.seller_commission_rate is not None
                and reward.seller_commission_rate < rate):
            hold(reward, ticket)
            rate, seller_reward_id = reward.seller_commission_rate, reward.user_id
    discount = (ticket.price * buyer_rate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    total, _, _ = amounts(ticket.price, rate, discount)
    if os.getenv('PAYMENT_PROVIDER', 'culqi') == 'culqi' and total < Decimal('3'):
        raise HTTPException(422, 'Con el descuento, el cobro queda por debajo del mínimo de S/ 3 de Culqi. Elige una entrada de mayor precio; tu beneficio seguirá disponible.')
    ticket.reservation_id, ticket.reservation_total, ticket.reservation_discount = uuid.uuid4(), total, discount
    ticket.reservation_discount_rate = buyer_rate
    ticket.reservation_commission_rate, ticket.reservation_seller_reward_id = rate, seller_reward_id
    return quote_view(ticket)


def quote_view(ticket):
    return {'reservation_id': str(ticket.reservation_id), 'listed_amount': float(ticket.price),
            'amount_total': float(ticket.reservation_total), 'amount_total_cents': int(ticket.reservation_total * 100),
            'buyer_discount': float(ticket.reservation_discount or 0),
            'buyer_discount_rate': float(ticket.reservation_discount_rate or 0),
            'commission_rate': float(ticket.reservation_commission_rate if ticket.reservation_commission_rate is not None else ticket.commission_rate)}


def checkout_values(db, ticket, buyer_id, reservation_id=None):
    if ticket.reservation_total is None:
        reserve_quote(db, ticket, buyer_id)
    if reservation_id and reservation_id != ticket.reservation_id:
        raise HTTPException(409, 'La cotización cambió. Vuelve a seleccionar la entrada.')
    discount = ticket.reservation_discount or Decimal('0')
    rate = ticket.reservation_commission_rate if ticket.reservation_commission_rate is not None else ticket.commission_rate
    buyer_rate = ticket.reservation_discount_rate or Decimal('0')
    total, commission, seller = amounts(ticket.price, rate, discount)
    if total != ticket.reservation_total:
        raise HTTPException(409, 'La cotización requiere actualizarse antes de pagar.')
    expected = {buyer_id: ('BUY', buyer_rate)} if discount else {}
    if ticket.reservation_seller_reward_id:
        if ticket.reservation_seller_reward_id != ticket.seller_id:
            raise HTTPException(409, 'La bonificación no corresponde al vendedor.')
        expected[ticket.seller_id] = ('SELL', rate)
    rows = reward_rows(db, ticket, buyer_id)
    for user_id, (choice, expected_rate) in expected.items():
        reward = next((r for r in rows if r.user_id == user_id), None)
        actual_rate = (reward.buyer_discount_rate if choice == 'BUY' else reward.seller_commission_rate) if reward else None
        if not reward or reward.used_transaction_id or reward.revoked_at or reward.choice != choice or actual_rate != expected_rate:
            raise HTTPException(409, 'El beneficio cambió. Vuelve a seleccionar la entrada para actualizar la cotización.')
        hold(reward, ticket)
        if not reward.reserved_until or utc(reward.reserved_until) <= datetime.now(timezone.utc):
            raise HTTPException(409, 'La reserva del beneficio venció. Vuelve a seleccionar la entrada.')
    return {'listed_amount': ticket.price, 'buyer_discount': discount, 'buyer_discount_rate': buyer_rate,
            'commission_rate': rate, 'amount_total': total, 'commission_platform': commission, 'amount_seller': seller,
            'referral_reward_user_id': buyer_id if discount else None,
            'seller_referral_reward_user_id': ticket.reservation_seller_reward_id}


def participating_rewards(db, tx):
    ids = [i for i in (tx.referral_reward_user_id, tx.seller_referral_reward_user_id) if i]
    rows = db.query(models.ReferralReward).filter(models.ReferralReward.user_id.in_(ids)).order_by(
        models.ReferralReward.user_id).populate_existing().with_for_update().all() if ids else []
    if len(rows) != len(set(ids)):
        raise PaymentUncertain('Los beneficios del pago requieren conciliación.')
    return rows


def bind_reward(db, tx):
    db.flush()
    for reward in participating_rewards(db, tx):
        if (reward.used_transaction_id or reward.revoked_at or reward.reserved_ticket_id != tx.ticket_id
                or reward.reserved_transaction_id or not reward.reserved_until
                or utc(reward.reserved_until) <= datetime.now(timezone.utc)):
            raise HTTPException(409, 'La reserva del beneficio cambió antes de iniciar el pago.')
        reward.reserved_transaction_id, reward.reserved_until = tx.id, None


def consume_reward(db, tx):
    for reward in participating_rewards(db, tx):
        if reward.used_transaction_id == tx.id:
            continue
        if reward.used_transaction_id or reward.reserved_ticket_id != tx.ticket_id or reward.reserved_transaction_id != tx.id:
            raise PaymentUncertain('El beneficio del pago requiere conciliación.')
        reward.pending_upgrade = None
        clear_hold(reward)
        reward.used_transaction_id, reward.used_at = tx.id, datetime.now(timezone.utc)
        db.add(models.AuditLog(user_id=reward.user_id, action='REFERRAL_REWARD_USED', entity_type='transaction', entity_id=str(tx.id)))


def release_failed_reward(db, tx):
    if tx.status == 'FAILED':
        upgraded = False
        for reward in participating_rewards(db, tx):
            if not reward.used_transaction_id and reward.reserved_ticket_id == tx.ticket_id and reward.reserved_transaction_id == tx.id:
                upgraded = upgraded or bool(reward.pending_upgrade)
                clear_hold(reward)
        if upgraded:
            # Both callers already own Ticket -> Transaction locks. The failed
            # quote cannot price the upgraded benefit; release it atomically so
            # the buyer can choose and explicitly confirm a fresh reservation.
            ticket = db.get(models.Ticket, tx.ticket_id)
            active = db.query(models.Transaction.id).filter(models.Transaction.ticket_id == tx.ticket_id,
                models.Transaction.id != tx.id,
                models.Transaction.status.in_(('PROCESSING', 'UNKNOWN', 'SUCCEEDED', 'REFUND_PENDING', 'REFUNDED'))).first()
            if ticket.buyer_id == tx.buyer_id and ticket.estado == models.TicketState.RESERVADA and not active:
                ticket.estado, ticket.buyer_id, ticket.reserved_until = models.TicketState.DISPONIBLE, None, None
                ticket.reservation_id = ticket.reservation_total = ticket.reservation_discount = None
                ticket.reservation_discount_rate = ticket.reservation_commission_rate = ticket.reservation_seller_reward_id = None
                db.add(models.AuditLog(user_id=tx.buyer_id, action='UPGRADED_REWARD_REQUIRES_NEW_QUOTE',
                                      entity_type='ticket', entity_id=str(ticket.id)))
                return True
    return False


def fail_transaction(db, transaction_id):
    tx = db.get(models.Transaction, transaction_id)
    db.query(models.Ticket).filter_by(id=tx.ticket_id).populate_existing().with_for_update().one()
    tx = db.query(models.Transaction).filter_by(id=transaction_id).populate_existing().with_for_update().one()
    if tx.status == 'PROCESSING':
        tx.status = 'FAILED'
    return release_failed_reward(db, tx)
