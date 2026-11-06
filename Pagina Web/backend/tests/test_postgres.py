"""Real PostgreSQL concurrency checks in a disposable, private schema.

Set TEST_POSTGRES_URL to a dedicated test database. No production tables touched.
SQLite tests do not replace these checks; they are explicitly skipped otherwise.
"""
import os
import sys
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("TICKIA_LOAD_ENV", "0")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "offline-postgres-tests-not-a-production-key")
sys.path.insert(0, str(Path(__file__).parents[2]))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from backend.main import app
from backend.database import Base, get_db
from backend import models
from backend.auth_utils import create_access_token
from backend.routers import payments, tickets


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL absent; PostgreSQL concurrency not verified")
class PostgreSQLConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ["TEST_POSTGRES_URL"]
        if not url.startswith("postgresql"):
            raise RuntimeError("PostgreSQL URL required")
        cls.raw_engine = create_engine(url, pool_pre_ping=True)
        cls.schema = "tickia_test_" + uuid.uuid4().hex
        with cls.raw_engine.begin() as connection:
            connection.execute(text('CREATE SCHEMA "' + cls.schema + '"'))
        cls.engine = cls.raw_engine.execution_options(schema_translate_map={None: cls.schema})
        cls.Session = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(cls.engine)

    @classmethod
    def tearDownClass(cls):
        # Name is internally generated and checked before the destructive cleanup.
        import re
        if not re.fullmatch(r"tickia_test_[a-f0-9]{32}", cls.schema):
            raise RuntimeError("Invalid disposable schema")
        with cls.raw_engine.begin() as connection:
            connection.execute(text('DROP SCHEMA "' + cls.schema + '" CASCADE'))
        cls.raw_engine.dispose()

    def setUp(self):
        self.old_overrides = app.dependency_overrides.copy()
        from types import SimpleNamespace
        self.provider_patch = patch.object(tickets, "get_payment_provider", lambda: SimpleNamespace(enabled=lambda: True))
        self.provider_patch.start()
        self.old_limiter = app.state.limiter.enabled
        app.state.limiter.enabled = False

        def test_db():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = test_db
        self.users = {}
        with self.Session() as db:
            for role in ("seller", "buyer", "other"):
                user = models.User(email=role + uuid.uuid4().hex + "@example.com", hashed_password="unused-test-hash")
                db.add(user)
                db.flush()
                self.users[role] = user.id
            self.ticket_id = uuid.uuid4()
            db.add(models.Ticket(
                id=self.ticket_id, seller_id=self.users["seller"], event_name="Concurrency fixture",
                event_date=datetime.now(timezone.utc) + timedelta(days=3), zone="General",
                ticketing_company="teleticket", ticket_type="no_nominada", is_renominated=False,
                price=100, qr_hash_sha256=uuid.uuid4().hex, qr_image_url_encrypted="fixture.enc",
                hash_estado=models.HashState.ACTIVO, estado=models.TicketState.DISPONIBLE,
            ))
            db.commit()

    def tearDown(self):
        self.provider_patch.stop()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.old_overrides)
        app.state.limiter.enabled = self.old_limiter

    def post(self, path, role="buyer", body=None):
        token = create_access_token({"user_id": str(self.users[role])})
        client = TestClient(app)
        try:
            return client.post(path, headers={"Authorization": "Bearer " + token}, json=body)
        finally:
            client.close()

    def parallel(self, call):
        barrier = threading.Barrier(2)
        def invoke(index):
            barrier.wait(timeout=10)
            return call(index)
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(invoke, (0, 1)))

    def test_two_buyers_cannot_reserve_same_ticket(self):
        results = self.parallel(lambda index: self.post(
            "/api/tickets/" + str(self.ticket_id) + "/buy", "buyer" if index == 0 else "other",
        ))
        self.assertEqual(sorted(response.status_code for response in results), [200, 409])
        with self.Session() as db:
            ticket = db.get(models.Ticket, self.ticket_id)
            self.assertEqual(ticket.estado, models.TicketState.RESERVADA)
            self.assertIn(ticket.buyer_id, (self.users["buyer"], self.users["other"]))

    def test_simultaneous_charges_make_one_provider_call(self):
        response = self.post("/api/tickets/" + str(self.ticket_id) + "/buy")
        self.assertEqual(response.status_code, 200, response.text)
        calls = []
        guard = threading.Lock()

        class Provider:
            def enabled(self):
                return True

            def create_charge(self, token, amount_cents, email, metadata):
                with guard:
                    calls.append(token)
                return {
                    "object": "charge", "id": "chr_test_" + uuid.uuid4().hex,
                    "amount": amount_cents, "currency_code": "PEN", "capture": True,
                    "outcome": {"type": "venta_exitosa"}, "amount_refunded": 0,
                    "dispute": False, "metadata": metadata,
                }

        with patch.object(payments, "get_payment_provider", Provider):
            results = self.parallel(lambda index: self.post("/api/payments/charge", body={
                "ticket_id": str(self.ticket_id), "culqi_token": "tkn_test_" + uuid.uuid4().hex,
            }))
        self.assertEqual(sorted(response.status_code for response in results), [200, 409])
        self.assertEqual(len(calls), 1)
        with self.Session() as db:
            transactions = db.query(models.Transaction).filter(models.Transaction.ticket_id == self.ticket_id).all()
            self.assertEqual(len(transactions), 1)
            self.assertEqual(transactions[0].status, "SUCCEEDED")

    def test_active_qr_constraint_prevents_simultaneous_insert(self):
        qr_hash = uuid.uuid4().hex

        def insert(index):
            with self.Session() as db:
                db.add(models.Ticket(
                    seller_id=self.users["seller"], event_name="Duplicate fixture",
                    event_date=datetime.now(timezone.utc) + timedelta(days=3), zone="General",
                    ticketing_company="teleticket", ticket_type="no_nominada", price=100,
                    qr_hash_sha256=qr_hash, qr_image_url_encrypted="fixture.enc",
                    hash_estado=models.HashState.ACTIVO,
                ))
                try:
                    db.commit()
                    return "inserted"
                except IntegrityError:
                    db.rollback()
                    return "duplicate"

        self.assertEqual(sorted(self.parallel(insert)), ["duplicate", "inserted"])

    def paid_review(self, resolved=False):
        with self.Session() as db:
            ticket = db.get(models.Ticket, self.ticket_id)
            ticket.estado = models.TicketState.VENDIDA
            ticket.buyer_id = self.users['buyer']
            tx = models.Transaction(ticket_id=ticket.id, buyer_id=ticket.buyer_id,
                culqi_charge_id='chr_test_' + uuid.uuid4().hex, status='SUCCEEDED',
                amount_total=100, commission_platform=10, amount_seller=90,
                provider_fee=0, seller_net_amount=90)
            db.add(tx); db.flush()
            review = models.PurchaseReview(transaction_id=tx.id, ticket_id=ticket.id,
                delivered_at=datetime.now(timezone.utc), closes_at=datetime.now(timezone.utc)+timedelta(days=3),
                review_state='RESOLVED' if resolved else 'HELD', decision='CONFIRMED' if resolved else None,
                settlement_state='QUEUED' if resolved else 'NONE')
            db.add(review); db.commit()
            return review.id

    def test_confirm_and_dispute_are_mutually_exclusive(self):
        from backend.routers import purchases
        from test_qr import image_bytes
        review_id = self.paid_review()
        token = create_access_token({'user_id': str(self.users['buyer'])})
        def act(index):
            with TestClient(app) as client:
                if index == 0:
                    return client.post('/api/purchases/' + str(review_id) + '/confirm', headers={'Authorization':'Bearer '+token})
                return client.post('/api/purchases/' + str(review_id) + '/dispute', headers={'Authorization':'Bearer '+token},
                    data={'description':'La entrada fue rechazada al ingresar.'},
                    files={'file':('evidence.png',image_bytes('evidence'),'image/png')})
        with patch.object(purchases,'upload_encrypted_qr',lambda path,data:path):
            results = self.parallel(act)
        self.assertEqual(sorted(response.status_code for response in results), [200,409])

    def test_two_settlement_workers_send_once_and_reward_once(self):
        from backend.post_purchase import process_settlements
        from decimal import Decimal
        review_id = self.paid_review(resolved=True)
        calls=[]
        guard=threading.Lock()
        class Provider:
            def release_funds_to_seller(self, charge_id, amount_cents, operation_id, seller_id):
                with guard:
                    calls.append(operation_id)
                return {'operation_id':operation_id,'reference':'payout_'+operation_id,'amount_cents':amount_cents,'status':'SUCCEEDED'}
        def execute(index):
            with self.Session() as db:
                process_settlements(db,Provider())
        with patch.dict(os.environ,{'SETTLEMENT_ENABLED':'true'}):
            self.parallel(execute)
        self.assertEqual(calls.count(str(review_id)),1)
        self.assertEqual(len(calls),len(set(calls)))
        with self.Session() as db:
            self.assertEqual(db.get(models.PurchaseReview,review_id).settlement_state,'SUCCEEDED')
            self.assertEqual(db.get(models.User,self.users['buyer']).rating,Decimal('4.25'))
            self.assertEqual(db.get(models.User,self.users['seller']).rating,Decimal('4.25'))
