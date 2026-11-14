"""Audited campaign controls. No endpoint can override payment credentials/gates."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .. import models
from ..campaigns import settings_view
from ..database import get_db
from ..promotions import expire_hold, reward_fields, reward_state, utc
from .admin import get_admin_user

router = APIRouter()
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=500)]
Rate = Annotated[Decimal, Field(ge=0, lt=1, max_digits=5, decimal_places=4, allow_inf_nan=False)]
BuyerRate = Annotated[Decimal, Field(ge=0, le=Decimal('.5'), max_digits=5, decimal_places=4, allow_inf_nan=False)]


class Mutation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: Reason


class CampaignCreate(Mutation):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    starts_at: datetime
    ends_at: datetime
    enabled: bool = True
    listing_commission_rate: Rate
    registration_discount_rate: BuyerRate
    seller_buyer_discount_rate: BuyerRate
    seller_commission_rate: Rate


class CampaignPatch(Mutation):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    enabled: bool | None = None
    listing_commission_rate: Rate | None = None
    registration_discount_rate: BuyerRate | None = None
    seller_buyer_discount_rate: BuyerRate | None = None
    seller_commission_rate: Rate | None = None


class SettingsPatch(Mutation):
    registrations_enabled: bool | None = None
    publications_enabled: bool | None = None
    purchases_enabled: bool | None = None
    maintenance_mode: bool | None = None
    announcement: Annotated[str, StringConstraints(max_length=500)] | None = None


class RewardGrant(Mutation):
    user_id: uuid.UUID
    buyer_discount_rate: Annotated[Decimal, Field(gt=0, le=Decimal('.5'), max_digits=5, decimal_places=4)]
    seller_commission_rate: Rate | None = None


def audit(db, admin, action, entity, entity_id, reason, before=None, after=None):
    db.add(models.AuditLog(user_id=admin.id, action=action, entity_type=entity, entity_id=str(entity_id),
        reason=reason, previous_state=json.dumps(before, default=str) if before is not None else None,
        new_state=json.dumps(after, default=str) if after is not None else None))


def lock_controls(db):
    insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
    db.execute(insert(models.SiteSettings).values(id=1, registrations_enabled=True, publications_enabled=True,
        purchases_enabled=True, maintenance_mode=False, announcement='').on_conflict_do_nothing(index_elements=['id']))
    return db.query(models.SiteSettings).filter_by(id=1).populate_existing().with_for_update().one()


def campaign_dto(row):
    return {key: utc(getattr(row, key)).isoformat() if key in ('starts_at', 'ends_at') else
            float(getattr(row, key)) if isinstance(getattr(row, key), Decimal) else getattr(row, key) for key in ('id', 'name', 'starts_at', 'ends_at', 'enabled', 'archived',
        'listing_commission_rate', 'registration_discount_rate', 'seller_buyer_discount_rate', 'seller_commission_rate')}


def validate_campaign(db, row):
    if row.starts_at.tzinfo is None or row.ends_at.tzinfo is None or utc(row.ends_at) <= utc(row.starts_at):
        raise HTTPException(422, 'Incluye zona horaria y una finalización posterior al inicio.')
    row.starts_at, row.ends_at = utc(row.starts_at), utc(row.ends_at)
    if row.archived and row.enabled:
        raise HTTPException(409, 'Una campaña archivada no puede reactivarse.')
    if row.enabled and not row.archived:
        with db.no_autoflush:
            overlapping = db.query(models.PromotionCampaign).filter(
                models.PromotionCampaign.id != row.id, models.PromotionCampaign.enabled.is_(True),
                models.PromotionCampaign.archived.is_(False), models.PromotionCampaign.starts_at < row.ends_at,
                models.PromotionCampaign.ends_at > row.starts_at).first()
        if overlapping:
            raise HTTPException(409, 'Las campañas habilitadas no pueden superponerse.')


@router.get('/campaigns')
def campaigns(db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    return [campaign_dto(row) for row in db.query(models.PromotionCampaign).order_by(models.PromotionCampaign.starts_at.desc()).all()]


@router.post('/campaigns', status_code=201)
def create_campaign(body: CampaignCreate, db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    lock_controls(db)
    row = models.PromotionCampaign(id=uuid.uuid4(), archived=False, **body.model_dump(exclude={'reason'}))
    validate_campaign(db, row)
    db.add(row)
    audit(db, admin, 'ADMIN_CAMPAIGN_CREATED', 'campaign', row.id, body.reason, after=campaign_dto(row))
    db.commit()
    return campaign_dto(row)


@router.patch('/campaigns/{campaign_id}')
def update_campaign(campaign_id: uuid.UUID, body: CampaignPatch, db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    lock_controls(db)
    row = db.get(models.PromotionCampaign, campaign_id)
    if not row:
        raise HTTPException(404, 'Campaña no encontrada.')
    before = campaign_dto(row)
    row.starts_at, row.ends_at = utc(row.starts_at), utc(row.ends_at)
    for key, value in body.model_dump(exclude={'reason'}, exclude_unset=True).items():
        if value is None:
            raise HTTPException(422, 'Los campos de una campaña no admiten valores nulos.')
        setattr(row, key, value)
    validate_campaign(db, row)
    audit(db, admin, 'ADMIN_CAMPAIGN_UPDATED', 'campaign', row.id, body.reason, before, campaign_dto(row))
    db.commit()
    return campaign_dto(row)


@router.delete('/campaigns/{campaign_id}')
def archive_campaign(campaign_id: uuid.UUID, body: Mutation, db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    lock_controls(db)
    row = db.get(models.PromotionCampaign, campaign_id)
    if not row:
        raise HTTPException(404, 'Campaña no encontrada.')
    before = campaign_dto(row)
    row.archived, row.enabled = True, False
    audit(db, admin, 'ADMIN_CAMPAIGN_ARCHIVED', 'campaign', row.id, body.reason, before, campaign_dto(row))
    db.commit()
    return campaign_dto(row)


@router.get('/settings')
def settings(db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    return settings_view(db)


@router.patch('/settings')
def update_settings(body: SettingsPatch, db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    row = lock_controls(db)
    before = settings_view(db)
    for key, value in body.model_dump(exclude={'reason'}, exclude_unset=True).items():
        if value is None:
            raise HTTPException(422, 'Los controles no admiten valores nulos.')
        setattr(row, key, value)
    audit(db, admin, 'ADMIN_SETTINGS_UPDATED', 'settings', 1, body.reason, before, settings_view(db))
    db.commit()
    return settings_view(db)


@router.get('/rewards')
def rewards(skip: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50,
            db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    rows = db.query(models.ReferralReward, models.User.email).join(models.User, models.User.id == models.ReferralReward.user_id).order_by(
        models.ReferralReward.earned_at.desc(), models.ReferralReward.user_id).offset(skip).limit(limit).all()
    return [dict(user_id=row.user_id, email=email, **reward_fields(row)) for row, email in rows]


@router.post('/rewards')
def grant(body: RewardGrant, db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    user = db.get(models.User, body.user_id)
    if not user:
        raise HTTPException(404, 'Usuario no encontrado.')
    # Serialize creation with other admin grants, then lock the lifetime reward.
    lock_controls(db)
    insert = pg_insert if db.bind.dialect.name == 'postgresql' else sqlite_insert
    db.execute(insert(models.ReferralReward).values(user_id=user.id, reward_kind='MANUAL',
        buyer_discount_rate=body.buyer_discount_rate, choice='BUY').on_conflict_do_nothing(index_elements=['user_id']))
    row = db.query(models.ReferralReward).filter_by(user_id=user.id).populate_existing().with_for_update().one()
    expire_hold(row)
    if reward_state(row) not in ('NOT_EARNED', 'AVAILABLE'):
        raise HTTPException(409, 'No se puede sustituir un beneficio usado, revocado o reservado.')
    before = reward_fields(row)
    row.reward_kind, row.campaign_id = 'MANUAL', None
    row.buyer_discount_rate, row.seller_commission_rate = body.buyer_discount_rate, body.seller_commission_rate
    row.choice = 'BUY' if body.seller_commission_rate is None else None
    row.pending_upgrade = None
    audit(db, admin, 'ADMIN_REWARD_GRANTED', 'reward', user.id, body.reason, before, reward_fields(row))
    db.commit()
    return dict(user_id=user.id, email=user.email, **reward_fields(row))


@router.delete('/rewards/{user_id}')
def revoke(user_id: uuid.UUID, body: Mutation, db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    row = db.query(models.ReferralReward).filter_by(user_id=user_id).populate_existing().with_for_update().first()
    expire_hold(row)
    if reward_state(row) != 'AVAILABLE':
        raise HTTPException(409, 'Solo se puede revocar un beneficio disponible y sin reservas.')
    before = reward_fields(row)
    row.revoked_at = datetime.now(timezone.utc)
    row.pending_upgrade = None
    audit(db, admin, 'ADMIN_REWARD_REVOKED', 'reward', user_id, body.reason, before, reward_fields(row))
    db.commit()
    return dict(user_id=user_id, **reward_fields(row))


@router.get('/audit')
def audit_logs(skip: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50,
               db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    rows = db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc(), models.AuditLog.id).offset(skip).limit(limit).all()
    return [{key: getattr(row, key) for key in ('id', 'action', 'entity_type', 'entity_id', 'reason', 'timestamp')} for row in rows]
