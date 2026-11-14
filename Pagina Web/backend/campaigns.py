"""Optional campaigns and operational switches; checkout uses immutable snapshots."""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from fastapi import HTTPException

from . import models

REGULAR_COMMISSION = Decimal('.10')
SETTING_FIELDS = ('registrations_enabled', 'publications_enabled', 'purchases_enabled', 'maintenance_mode', 'announcement')


def settings_view(db):
    row = db.get(models.SiteSettings, 1)
    defaults = dict(registrations_enabled=True, publications_enabled=True, purchases_enabled=True,
                    maintenance_mode=False, announcement='')
    return {key: getattr(row, key) for key in SETTING_FIELDS} if row else defaults


def require_operation(db, operation):
    settings = settings_view(db)
    if settings['maintenance_mode'] or not settings[operation + '_enabled']:
        raise HTTPException(503, 'Esta operación está temporalmente pausada. Tus compras y reclamos siguen disponibles.')


def active_campaign(db, instant=None):
    from .promotions import in_launch_window
    instant = instant or datetime.now(timezone.utc)
    rows = db.query(models.PromotionCampaign).filter_by(enabled=True, archived=False).order_by(
        models.PromotionCampaign.starts_at.desc(), models.PromotionCampaign.id).all()
    return next((row for row in rows if in_launch_window(instant, row.starts_at, row.ends_at)), None)


def default_campaign():
    """Migration/test seed only: production never silently re-creates a stopped campaign."""
    return models.PromotionCampaign(id=uuid.UUID('aa000000-0000-4000-8000-000000000001'), name='Lanzamiento Tickia 2026',
        starts_at=datetime(2026, 11, 13, 5, tzinfo=timezone.utc),
        ends_at=datetime(2026, 12, 13, 5, tzinfo=timezone.utc), enabled=True, archived=False,
        listing_commission_rate=Decimal('.05'), registration_discount_rate=Decimal('.05'),
        seller_buyer_discount_rate=Decimal('.10'), seller_commission_rate=Decimal('0'))
