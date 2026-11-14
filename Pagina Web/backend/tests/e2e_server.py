"""Offline fixture API for browser tests ONLY.

Run from Pagina Web: backend/venv/Scripts/python.exe -m backend.tests.e2e_server
A temporary SQLite file and in-memory encrypted storage isolate every run.
"""
import os
import tempfile
from pathlib import Path

_fixture_dir = tempfile.TemporaryDirectory(prefix="tickia-e2e-")
os.environ.update({
    "TICKIA_LOAD_ENV": "0", "ENVIRONMENT": "test",
    "DATABASE_URL": "sqlite:///" + str(Path(_fixture_dir.name) / "fixture.db"),
    "SECRET_KEY": "offline-e2e-only-never-a-production-secret",
    "QR_ENCRYPTION_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    "PAYMENT_ENABLED": "false",
    "SETTLEMENT_ENABLED": "false",
    "CULQI_PRIVATE_KEY": "",
})
from ..database import Base, engine, SessionLocal
from .. import models
from .. import promotions
# Legacy journeys retain their regular prices regardless of the calendar date.
# Campaign-specific fixtures override this policy in their own isolated process.
promotions.in_launch_window = lambda *_args: False
from ..auth_utils import get_password_hash
from ..main import app
from ..routers import tickets, download, payments, purchases

STORED_FILES = {}


def store(path, data):
    STORED_FILES[path] = data
    return path


class OfflineProvider:
    def enabled(self):
        return True

    def create_charge(self, token, amount_cents, email, metadata):
        if "declined" in token:
            from ..payment_provider import PaymentDeclined
            raise PaymentDeclined()
        return {
            "object": "charge", "id": "chr_test_" + metadata["transaction_id"].replace("-", ""),
            "amount": amount_cents, "currency_code": "PEN", "paid": False, "capture": True,
            "outcome": {"type": "venta_exitosa"},
            "amount_refunded": 0, "metadata": metadata,
        }

    def release_funds_to_seller(self, charge_id, amount_cents, operation_id, seller_id):
        return {'operation_id':operation_id,'reference':'offline-payout-'+operation_id,'amount_cents':amount_cents,'status':'SUCCEEDED'}

    def refund_buyer(self, charge_id, amount_cents, operation_id):
        return {'operation_id':operation_id,'reference':'offline-refund-'+operation_id,'amount_cents':amount_cents,'status':'SUCCEEDED'}


tickets.upload_encrypted_qr = store
tickets.delete_qr_file = lambda path: STORED_FILES.pop(path, None)
download.download_encrypted_qr = lambda path: STORED_FILES[path]
payments.get_payment_provider = OfflineProvider
tickets.get_payment_provider = OfflineProvider
purchases.upload_encrypted_qr = store
purchases.download_encrypted_qr = lambda path: STORED_FILES[path]
purchases.delete_qr_file = lambda path: STORED_FILES.pop(path, None)
from .. import post_purchase
post_purchase.get_payment_provider = OfflineProvider
app.state.limiter.enabled = False

Base.metadata.create_all(engine)
with SessionLocal() as db:
    from ..campaigns import default_campaign
    db.add(default_campaign())
    for email, is_admin in (
        ("seller@example.com", False), ("buyer@example.com", False),
        ("other@example.com", False), ("admin@example.com", True),
    ):
        db.add(models.User(
            email=email, hashed_password=get_password_hash("TestPassword123!"),
            phone_number="999999999", full_name=email.split("@")[0],
            dni="12345678" if email == "buyer@example.com" else None,
            is_kyc_verified=email == "buyer@example.com",
            is_admin=is_admin, has_access=True,
        ))
    db.commit()

# Fixture-only endpoint. This module is excluded from the production image and
# binds loopback. It runs the real worker with synthetic fees and receipts.
@app.post('/api/_test/settle')
def settle_test():
    from unittest.mock import patch
    from decimal import Decimal
    with SessionLocal() as db, patch.dict(os.environ, {'SETTLEMENT_ENABLED':'true'}):
        for tx in db.query(models.Transaction).filter_by(status='SUCCEEDED').all():
            tx.provider_fee = Decimal('0')
            tx.seller_net_amount = tx.amount_seller
        db.commit()
        post_purchase.process_settlements(db,OfflineProvider())
    return {'fixture_only':True}

@app.post('/api/_test/expire/{purchase_id}')
def expire_test(purchase_id: str):
    import uuid
    from datetime import datetime, timedelta, timezone
    with SessionLocal() as db:
        row = db.get(models.PurchaseReview, uuid.UUID(purchase_id))
        row.closes_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        post_purchase.close_expired_reviews(db)
    return {'fixture_only':True}

if __name__ == "__main__":
    import uvicorn
    # Loopback only: this fixture server must never be internet-accessible.
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("E2E_API_PORT", "8001")))
