"""Offline API regressions using real FastAPI, SQLAlchemy, bcrypt and QR decoder."""
import os
import sys
import unittest
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.update({
    "TICKIA_LOAD_ENV": "0", "ENVIRONMENT": "test", "DATABASE_URL": "sqlite://",
    "SECRET_KEY": "offline-unit-tests-only-not-for-production",
    "QR_ENCRYPTION_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    "PAYMENT_ENABLED": "false",
})
sys.path.insert(0, str(Path(__file__).parents[2]))
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import Base, engine, SessionLocal
from backend import models
from backend.auth_utils import get_password_hash, create_access_token
from backend.routers import tickets, payments, download
from backend.payment_provider import PaymentDeclined, PaymentUncertain, CulqiProvider
from backend.jobs import release_expired_reservations, check_renomination_deadlines
from test_qr import image_bytes

PASSWORD = "TestPassword123!"
PASSWORD_HASH = get_password_hash(PASSWORD)


class FakeProvider:
    def __init__(self):
        self.charges = {}
        self.mode = "ok"
        self.calls = 0

    def enabled(self):
        return self.mode != "disabled"

    def create_charge(self, token, amount_cents, email, metadata):
        self.calls += 1
        if self.mode == "declined":
            raise PaymentDeclined()
        if self.mode == "timeout":
            raise PaymentUncertain()
        charge = {
            "object": "charge", "id": "chr_test_" + uuid.uuid4().hex, "amount": amount_cents,
            "currency_code": "PEN", "paid": False, "capture": True,
            "outcome": {"type": "venta_exitosa"},
            "amount_refunded": 0, "metadata": metadata,
        }
        if self.mode == "wrong_amount":
            charge["amount"] += 1
        self.charges[charge["id"]] = charge
        return charge

    def retrieve_charge(self, charge_id):
        if charge_id not in self.charges:
            raise PaymentUncertain()
        return self.charges[charge_id]


class APITests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        self.client = TestClient(app)
        app.state.limiter.enabled = False
        self.files = {}
        self.provider = FakeProvider()
        self.patches = [
            patch('backend.promotions.in_launch_window', return_value=False),
            patch.object(tickets, "upload_encrypted_qr", self.store),
            patch.object(tickets, "delete_qr_file", lambda key: self.files.pop(key, None)),
            patch.object(download, "download_encrypted_qr", lambda key: self.files[key]),
            patch.object(payments, "get_payment_provider", lambda: self.provider),
            patch.object(tickets, "get_payment_provider", lambda: self.provider),
        ]
        for item in self.patches:
            item.start()
        self.ids = {}
        with SessionLocal() as db:
            from backend.campaigns import default_campaign
            db.add(default_campaign())
            for role in ("seller", "buyer", "other", "admin"):
                user = models.User(
                    email=role + "@example.com", hashed_password=PASSWORD_HASH,
                    phone_number="999999999", is_admin=role == "admin",
                    full_name="Verified Test Buyer" if role == "buyer" else None,
                    dni="12345678" if role == "buyer" else None, is_kyc_verified=role == "buyer",
                )
                db.add(user)
                db.flush()
                self.ids[role] = user.id
            db.commit()

    @classmethod
    def tearDownClass(cls):
        engine.dispose()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.client.close()

    def store(self, path, data):
        self.files[path] = data
        return path

    def auth(self, role="buyer"):
        return {"Authorization": "Bearer " + create_access_token({"user_id": str(self.ids[role])})}

    def upload(self, nominated=False, event_date=None, data=None, **overrides):
        fields = {
            "price": "123.45", "event_name": "Concierto de prueba", "zone": "General",
            "is_nominated": str(nominated).lower(), "is_renominated": "false",
            "event_date": event_date or (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "event_end_date": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
            "ticketing_company": "teleticket",
        }
        fields.update(overrides)
        return self.client.post(
            "/api/tickets/upload", headers=self.auth("seller"), data=fields,
            files={"file": ("ticket.png", data if data is not None else image_bytes("https://teleticket.com.pe/ticket/fixture"), "image/png")},
        )

    def reserve(self, ticket_id, role="buyer"):
        return self.client.post("/api/tickets/" + ticket_id + "/buy", headers=self.auth(role))

    def charge(self, ticket_id, token=None):
        return self.client.post("/api/payments/charge", headers=self.auth(), json={
            "ticket_id": ticket_id, "culqi_token": token or "tkn_test_" + uuid.uuid4().hex,
        })

    def purchased_ticket(self, nominated=False):
        response = self.upload(nominated=nominated)
        self.assertEqual(response.status_code, 200, response.text)
        ticket_id = response.json()["id"]
        self.assertEqual(self.reserve(ticket_id).status_code, 200)
        self.assertEqual(self.charge(ticket_id).status_code, 200)
        return ticket_id

    def test_registration_is_open_and_normalizes_email(self):
        response = self.client.post("/api/auth/register", json={
            "email": "NEW@EXAMPLE.COM", "password": PASSWORD, "phone_number": "999999999",
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["email"], "new@example.com")
        self.assertNotIn("has_access", response.json())
        self.assertEqual(self.client.get("/api/auth/waitlist/status", headers=self.auth()).status_code, 404)

    def test_duplicate_registration_returns_controlled_error(self):
        response = self.client.post("/api/auth/register", json={
            "email": "BUYER@example.com", "password": PASSWORD, "phone_number": "999999999",
        })
        self.assertEqual(response.status_code, 400)

    def test_unicode_bcrypt_length_is_validated(self):
        response = self.client.post("/api/auth/register", json={
            "email": "unicode@example.com", "password": chr(0x1F600) * 25, "phone_number": "999999999",
        })
        self.assertEqual(response.status_code, 422)

    def test_login_cookie_and_logout(self):
        response = self.client.post("/api/auth/login", data={"username": "BUYER@EXAMPLE.COM", "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_invalid_login_and_long_password_never_crash(self):
        for password in ("wrong", "x" * 200):
            response = self.client.post("/api/auth/login", data={"username": "buyer@example.com", "password": password})
            self.assertEqual(response.status_code, 401)

    def test_ban_invalidates_existing_session(self):
        with SessionLocal() as db:
            user = db.get(models.User, self.ids["buyer"])
            user.banned_until = datetime.now(timezone.utc) + timedelta(days=1)
            db.commit()
        self.assertEqual(self.client.get("/api/auth/me", headers=self.auth()).status_code, 403)

    def test_invalid_subject_expiry_and_algorithm_are_unauthorized(self):
        token = create_access_token({"user_id": ["invalid"]})
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).status_code, 401)
        import jwt
        from backend.auth_utils import SECRET_KEY
        expired = create_access_token({"user_id": str(self.ids["buyer"])}, expires_delta=timedelta(seconds=-1))
        no_expiry = jwt.encode({"user_id": str(self.ids["buyer"])}, SECRET_KEY, algorithm="HS256")
        wrong_algorithm = jwt.encode({"user_id": str(self.ids["buyer"]), "exp": datetime.now(timezone.utc) + timedelta(minutes=1)}, SECRET_KEY, algorithm="HS384")
        for invalid in (expired, no_expiry, wrong_algorithm):
            self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + invalid}).status_code, 401)

    def test_admin_access_and_input_validation(self):
        self.assertEqual(self.client.get("/api/admin/users", headers=self.auth()).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/users", headers=self.auth("admin")).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/users?limit=-1", headers=self.auth("admin")).status_code, 422)
        self.assertEqual(self.client.post("/api/admin/users/not-a-uuid/ban", headers=self.auth("admin")).status_code, 422)
        response = self.client.post("/api/admin/users/" + str(self.ids["buyer"]) + "/ban?days=-1", headers=self.auth("admin"))
        self.assertEqual(response.status_code, 422)

    def test_cross_origin_mutation_is_rejected(self):
        self.assertEqual(self.client.post("/api/auth/logout", headers={"Origin": "https://attacker.invalid"}).status_code, 403)

    def test_health_readiness_and_security_headers(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_upload_and_catalog_hide_qr_details(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("qr_hash_sha256", response.json())
        self.assertNotIn("qr_image_url_encrypted", response.json())
        self.assertIn("is_renominated", response.json())
        self.assertTrue(response.json()["event_date"].endswith("Z"))
        self.assertTrue(response.json()["created_at"].endswith("Z"))
        self.assertEqual(len(self.client.get("/api/tickets").json()), 1)

    def test_upload_rejects_missing_qr_and_invalid_file(self):
        self.assertEqual(self.upload(data=image_bytes()).status_code, 400)
        self.assertEqual(self.upload(data=b"bad").status_code, 400)
        self.assertEqual(self.upload(data=b"x" * (5 * 1024 * 1024 + 1)).status_code, 413)

    def test_upload_requires_actual_future_date_and_valid_price(self):
        self.assertEqual(self.upload(event_date="2020-01-01T00:00:00Z").status_code, 422)
        self.assertEqual(self.upload(event_date="2099-01-01T00:00:00").status_code, 422)
        for price in ("0", "-1", "1", "2.99", "5001", "123.456", "nan", "inf"):
            self.assertEqual(self.upload(price=price).status_code, 422)
        self.assertEqual(self.upload(price="3").status_code, 200)

    def test_contact_info_is_rejected_without_automatic_account_ban(self):
        self.assertEqual(self.upload(event_name="Evento whatsapp wa.me/51999999999").status_code, 422)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.auth("seller")).status_code, 200)

    def test_duplicate_qr_is_rejected(self):
        data = image_bytes("https://joinnus.com/ticket/fixed")
        self.assertEqual(self.upload(data=data).status_code, 200)
        self.assertEqual(self.upload(data=data).status_code, 409)
        self.assertEqual(len(self.files), 1)

    def test_storage_outage_does_not_publish_ticket(self):
        with patch.object(tickets, "upload_encrypted_qr", side_effect=RuntimeError("offline")):
            self.assertEqual(self.upload().status_code, 503)
        self.assertEqual(self.client.get("/api/tickets").json(), [])

    def test_chunked_upload_is_bounded(self):
        response = self.client.post("/api/auth/register", content=(b"x" * (7 * 1024 * 1024) for _ in range(1)), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)

    def test_catalog_pagination_is_bounded(self):
        self.assertEqual(self.client.get("/api/tickets?skip=-1").status_code, 422)
        self.assertEqual(self.client.get("/api/tickets?limit=101").status_code, 422)

    def test_reservation_ownership_and_conflicts(self):
        ticket_id = self.upload().json()["id"]
        self.assertEqual(self.reserve(ticket_id, "seller").status_code, 400)
        self.assertEqual(self.client.post("/api/tickets/" + ticket_id + "/buy").status_code, 401)
        response = self.reserve(ticket_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["amount_total_cents"], 12345)
        self.assertEqual(self.reserve(ticket_id, "other").status_code, 409)

    def test_nominated_ticket_requires_verified_identity(self):
        ticket_id = self.upload(nominated=True).json()["id"]
        self.assertEqual(self.reserve(ticket_id, "other").status_code, 403)

    def test_disabled_payments_do_not_reserve_inventory(self):
        ticket_id = self.upload().json()["id"]
        self.provider.mode = "disabled"
        self.assertEqual(self.reserve(ticket_id).status_code, 503)
        with SessionLocal() as db:
            self.assertEqual(db.get(models.Ticket, uuid.UUID(ticket_id)).estado, models.TicketState.DISPONIBLE)

    def test_charge_disabled_does_not_create_transaction(self):
        ticket_id = self.upload().json()["id"]
        self.reserve(ticket_id)
        self.provider.mode = "disabled"
        self.assertFalse(self.client.get("/api/payments/status").json()["enabled"])
        self.assertEqual(self.charge(ticket_id).status_code, 503)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Transaction).count(), 0)

    def test_expired_reservation_cannot_be_charged(self):
        ticket_id = self.upload().json()["id"]
        self.reserve(ticket_id)
        with SessionLocal() as db:
            db.get(models.Ticket, uuid.UUID(ticket_id)).reserved_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.charge(ticket_id).status_code, 409)
        self.assertEqual(self.provider.calls, 0)

    def test_seller_amount_is_estimated_until_provider_fees_are_verified(self):
        self.purchased_ticket()
        sale = self.client.get("/api/tickets/my-sales", headers=self.auth("seller")).json()[0]
        self.assertEqual(sale["estimated_seller_amount"], 111.10)
        self.assertIsNone(sale["provider_fee"])
        self.assertIsNone(sale["seller_net_amount"])

    def test_charge_success_has_no_buyer_surcharge_and_cannot_repeat(self):
        ticket_id = self.purchased_ticket()
        with SessionLocal() as db:
            tx = db.query(models.Transaction).one()
            self.assertEqual(float(tx.amount_total), 123.45)
            self.assertEqual(float(tx.commission_platform), 12.35)
            self.assertEqual(float(tx.amount_seller), 111.10)
        self.assertEqual(self.charge(ticket_id).status_code, 409)
        self.assertEqual(self.provider.calls, 1)

    def test_declined_payment_does_not_sell_ticket(self):
        ticket_id = self.upload().json()["id"]
        self.reserve(ticket_id)
        self.provider.mode = "declined"
        self.assertEqual(self.charge(ticket_id).status_code, 402)
        with SessionLocal() as db:
            self.assertEqual(db.get(models.Ticket, uuid.UUID(ticket_id)).estado, models.TicketState.RESERVADA)
            self.assertEqual(db.query(models.Transaction).one().status, "FAILED")

    def test_uncertain_payment_blocks_retry_and_cleanup(self):
        ticket_id = self.upload().json()["id"]
        self.reserve(ticket_id)
        self.provider.mode = "timeout"
        self.assertEqual(self.charge(ticket_id).status_code, 502)
        self.assertEqual(self.charge(ticket_id).status_code, 409)
        with SessionLocal() as db:
            ticket = db.get(models.Ticket, uuid.UUID(ticket_id))
            ticket.reserved_until = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
            release_expired_reservations(db)
            self.assertEqual(ticket.estado, models.TicketState.RESERVADA)

    def test_wrong_provider_amount_never_marks_paid(self):
        ticket_id = self.upload().json()["id"]
        self.reserve(ticket_id)
        self.provider.mode = "wrong_amount"
        self.assertEqual(self.charge(ticket_id).status_code, 502)
        self.assertEqual(self.client.get("/api/tickets/me", headers=self.auth()).json(), [])

    def test_cleanup_releases_at_ten_minutes_not_twenty(self):
        ticket_id = self.upload().json()["id"]
        self.reserve(ticket_id)
        with SessionLocal() as db:
            ticket = db.get(models.Ticket, uuid.UUID(ticket_id))
            ticket.reserved_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            release_expired_reservations(db)
            self.assertEqual(ticket.estado, models.TicketState.DISPONIBLE)
            self.assertIsNone(ticket.buyer_id)

    def test_nominated_payment_waits_for_new_qr(self):
        ticket_id = self.purchased_ticket(nominated=True)
        response = self.client.get("/api/tickets/me", headers=self.auth())
        self.assertEqual(response.json()[0]["estado"], "PENDIENTE_RENOMINACION")
        self.assertEqual(self.client.get("/api/tickets/" + ticket_id + "/qr", headers=self.auth()).status_code, 404)
        response = self.client.post("/api/tickets/" + ticket_id + "/renominate", headers=self.auth("seller"), files={
            "file": ("new.png", image_bytes("https://teleticket.com.pe/new/fixture"), "image/png"),
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get("/api/tickets/" + ticket_id + "/qr", headers=self.auth()).status_code, 200)

    def test_missed_nomination_never_pretends_refund(self):
        ticket_id = self.purchased_ticket(nominated=True)
        with SessionLocal() as db:
            ticket = db.get(models.Ticket, uuid.UUID(ticket_id))
            ticket.renomination_deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            check_renomination_deadlines(db)
            self.assertEqual(ticket.estado, models.TicketState.PENDIENTE_RENOMINACION)
            self.assertEqual(db.query(models.Transaction).one().status, "REFUND_PENDING")

    def test_qr_download_owner_single_use_and_revocation(self):
        ticket_id = self.purchased_ticket()
        response = self.client.get("/api/tickets/" + ticket_id + "/qr", headers=self.auth())
        url = response.json()["qr_image_url"]
        self.assertNotIn("hash", response.json())
        self.assertEqual(self.client.get(url, headers=self.auth("other")).status_code, 403)
        downloaded = self.client.get(url, headers=self.auth())
        self.assertEqual(downloaded.status_code, 200)
        self.assertTrue(downloaded.content.startswith(b"\x89PNG"))
        self.assertIn("no-store", downloaded.headers["cache-control"])
        self.assertEqual(self.client.get(url, headers=self.auth()).status_code, 410)
        new_url = self.client.get("/api/tickets/" + ticket_id + "/qr", headers=self.auth()).json()["qr_image_url"]
        with SessionLocal() as db:
            db.query(models.Transaction).one().status = "REFUND_PENDING"
            db.commit()
        self.assertEqual(self.client.get(new_url, headers=self.auth()).status_code, 403)

    def test_webhook_requires_provider_verification(self):
        response = self.client.post("/api/payments/webhook/culqi", json={
            "type": "charge.succeeded", "data": {"id": "chr_test_forgedcharge"},
        })
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.client.post("/api/payments/webhook/culqi", content=b"{bad").status_code, 400)

    def test_download_outage_preserves_single_use_token(self):
        ticket_id = self.purchased_ticket()
        url = self.client.get("/api/tickets/" + ticket_id + "/qr", headers=self.auth()).json()["qr_image_url"]
        with patch.object(download, "download_encrypted_qr", side_effect=RuntimeError("offline")):
            self.assertEqual(self.client.get(url, headers=self.auth()).status_code, 503)
        self.assertEqual(self.client.get(url, headers=self.auth()).status_code, 200)

    def test_expired_download_token_is_rejected(self):
        ticket_id = self.purchased_ticket()
        url = self.client.get("/api/tickets/" + ticket_id + "/qr", headers=self.auth()).json()["qr_image_url"]
        with SessionLocal() as db:
            db.query(models.Transaction).one().download_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.get(url, headers=self.auth()).status_code, 410)

    def test_database_unique_qr_guard_survives_application_bypass(self):
        from sqlalchemy.exc import IntegrityError
        ticket_id = self.upload().json()["id"]
        with SessionLocal() as db:
            original = db.get(models.Ticket, uuid.UUID(ticket_id))
            duplicate = models.Ticket(
                seller_id=original.seller_id, event_name=original.event_name, event_date=original.event_date,
                zone=original.zone, ticketing_company=original.ticketing_company, ticket_type=original.ticket_type,
                price=original.price, qr_hash_sha256=original.qr_hash_sha256,
                qr_image_url_encrypted="fixture.enc", hash_estado=models.HashState.ACTIVO,
            )
            db.add(duplicate)
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

    def test_verified_webhook_is_idempotent(self):
        self.purchased_ticket()
        charge_id = next(iter(self.provider.charges))
        for _ in range(2):
            response = self.client.post("/api/payments/webhook/culqi", json={
                "type": "charge.creation.succeeded", "data": {"id": charge_id},
            })
            self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Transaction).count(), 1)


class ProviderTests(unittest.TestCase):
    def test_charge_request_uses_exact_amount_and_merchant_key(self):
        import httpx
        provider = CulqiProvider()
        with patch.dict(os.environ, {"PAYMENT_ENABLED": "true", "CULQI_PRIVATE_KEY": "sk_test_offline_fixture_key"}):
            with patch("httpx.request", return_value=httpx.Response(201, json={"object": "charge"})) as request:
                self.assertEqual(provider.create_charge("tkn_test_fixture", 10000, "buyer@example.com", {})["object"], "charge")
                self.assertEqual(request.call_args.kwargs["json"]["amount"], 10000)
                self.assertTrue(request.call_args.kwargs["json"]["capture"])
                self.assertEqual(request.call_args.kwargs["timeout"], 15.0)

    def test_provider_decline_timeout_invalid_json_and_3ds_fail_closed(self):
        import httpx
        with patch.dict(os.environ, {"PAYMENT_ENABLED": "true", "CULQI_PRIVATE_KEY": "sk_test_offline_fixture_key"}):
            cases = [
                (httpx.Response(402, json={}), PaymentDeclined),
                (httpx.Response(503, json={}), PaymentUncertain),
                (httpx.Response(201, content=b"not json"), PaymentUncertain),
                (httpx.Response(200, json={"action_code": "3ds"}), PaymentUncertain),
            ]
            for response, error_type in cases:
                with self.subTest(status=response.status_code), patch("httpx.request", return_value=response):
                    with self.assertRaises(error_type):
                        CulqiProvider().create_charge("tkn_test_fixture", 1000, "buyer@example.com", {})
            with patch("httpx.request", side_effect=httpx.ReadTimeout("offline")):
                with self.assertRaises(PaymentUncertain):
                    CulqiProvider().create_charge("tkn_test_fixture", 1000, "buyer@example.com", {})

    def test_production_rejects_test_private_key(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "PAYMENT_ENABLED": "true", "CULQI_PRIVATE_KEY": "sk_test_offline_fixture_key"}):
            self.assertFalse(CulqiProvider().enabled())

    def test_unconfigured_provider_does_not_make_network_calls(self):
        with patch.dict(os.environ, {"PAYMENT_ENABLED": "false"}), patch("httpx.request") as request:
            self.assertFalse(CulqiProvider().enabled())
            from backend.payment_provider import PaymentUnavailable
            with self.assertRaises(PaymentUnavailable):
                CulqiProvider().create_charge("tkn_test_fixture", 1000, "test@example.com", {})
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
