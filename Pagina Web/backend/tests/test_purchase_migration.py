"""No-delivery regressions and an optional, isolated PostgreSQL backfill check.

Terminal legacy records preserve history; they never replay money movement,
award ratings, deduct ratings, or add warnings retroactively.
"""
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import test_api as fixtures
from backend import models
from backend.database import SessionLocal
from backend.jobs import check_renomination_deadlines
from backend.payment_provider import PaymentUnavailable
from backend.post_purchase import process_settlements


class NoDeliveryRefundTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        fixtures.engine.dispose()

    def setUp(self):
        self.fixture = fixtures.APITests(methodName='runTest')
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def nomination(self, status='SUCCEEDED', existing_review=False):
        with SessionLocal() as db:
            ticket = models.Ticket(
                seller_id=self.fixture.ids['seller'], buyer_id=self.fixture.ids['buyer'],
                event_name='Pending delivery fixture',
                event_date=datetime.now(timezone.utc) + timedelta(days=3),
                event_end_date=datetime.now(timezone.utc) + timedelta(days=4),
                zone='General', ticketing_company='teleticket', ticket_type='nominada',
                price=100, estado=models.TicketState.PENDIENTE_RENOMINACION,
                renomination_deadline=datetime.now(timezone.utc) - timedelta(minutes=1),
                qr_hash_sha256=uuid.uuid4().hex, qr_image_url_encrypted='fixture.enc',
            )
            db.add(ticket)
            db.flush()
            tx = models.Transaction(
                ticket_id=ticket.id, buyer_id=self.fixture.ids['buyer'],
                culqi_charge_id='chr_test_' + uuid.uuid4().hex, status=status,
                amount_total=100, commission_platform=10, amount_seller=90,
                download_token=uuid.uuid4().hex,
            )
            db.add(tx)
            db.flush()
            if existing_review:
                db.add(models.PurchaseReview(transaction_id=tx.id, ticket_id=ticket.id))
            db.commit()
            return ticket.id, tx.id

    def test_expired_nomination_is_visible_and_queued_without_claiming_a_refund(self):
        ticket_id, tx_id = self.nomination()
        with SessionLocal() as db:
            check_renomination_deadlines(db)
            row = db.query(models.PurchaseReview).one()
            self.assertEqual((row.review_state, row.decision, row.settlement_state),
                             ('RESOLVED', 'VALID_CLAIM', 'QUEUED'))
            self.assertIsNone(row.delivered_at)
            self.assertIsNone(row.settlement_reference)
            self.assertFalse(row.reputation_applied)
            self.assertIn('Renominaci', row.decision_reason)
            self.assertEqual(db.get(models.Transaction, tx_id).status, 'REFUND_PENDING')
            self.assertIsNone(db.get(models.Transaction, tx_id).download_token)
            self.assertEqual(db.get(models.Ticket, ticket_id).estado,
                             models.TicketState.PENDIENTE_RENOMINACION)
            for role in ('buyer', 'seller'):
                self.assertEqual(db.get(models.User, self.fixture.ids[role]).rating, Decimal('4'))
            self.assertEqual(db.get(models.User, self.fixture.ids['seller']).warning_count, 0)
        response = self.fixture.client.get('/api/purchases/admin/cases',
                                           headers=self.fixture.auth('admin'))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]['settlement_state'], 'QUEUED')

    def test_verified_no_delivery_refund_moves_money_state_and_reputation_once(self):
        ticket_id, tx_id = self.nomination(existing_review=True)
        calls = []

        class Provider:
            def refund_buyer(self, charge_id, amount_cents, operation_id):
                calls.append((charge_id, amount_cents, operation_id))
                return {'operation_id': operation_id, 'reference': 'ref_test_verified',
                        'amount_cents': amount_cents, 'status': 'SUCCEEDED'}

        with SessionLocal() as db, patch.dict(os.environ, {'SETTLEMENT_ENABLED': 'true'}):
            check_renomination_deadlines(db)
            check_renomination_deadlines(db)
            self.assertEqual(db.query(models.AuditLog).filter_by(action='PURCHASE_VALID_CLAIM').count(), 1)
            process_settlements(db, Provider())
            check_renomination_deadlines(db)
            process_settlements(db, Provider())
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1], 10000)
            self.assertEqual(db.get(models.Transaction, tx_id).status, 'REFUNDED')
            self.assertEqual(db.get(models.Ticket, ticket_id).estado, models.TicketState.REEMBOLSADA)
            self.assertEqual(db.get(models.User, self.fixture.ids['buyer']).rating, Decimal('4.25'))
            self.assertEqual(db.get(models.User, self.fixture.ids['seller']).rating, Decimal('4'))
            self.assertEqual(db.get(models.User, self.fixture.ids['seller']).warning_count, 1)

    def test_unavailable_refund_does_not_award_ratings_or_pretend_success(self):
        self.nomination()

        class Provider:
            def refund_buyer(self, *args):
                raise PaymentUnavailable('Provider unavailable in offline regression.')

        with SessionLocal() as db, patch.dict(os.environ, {'SETTLEMENT_ENABLED': 'true'}):
            check_renomination_deadlines(db)
            process_settlements(db, Provider())
            row = db.query(models.PurchaseReview).one()
            self.assertEqual(row.settlement_state, 'BLOCKED')
            self.assertIsNone(row.settlement_reference)
            self.assertFalse(row.reputation_applied)
            self.assertEqual(db.query(models.Transaction).one().status, 'REFUND_PENDING')
            self.assertEqual(db.get(models.User, self.fixture.ids['buyer']).rating, Decimal('4'))
            self.assertEqual(db.get(models.User, self.fixture.ids['seller']).warning_count, 0)

    def test_old_pending_flag_is_reconciled_instead_of_resent_or_repenalized(self):
        self.nomination(status='REFUND_PENDING', existing_review=True)

        class NeverSend:
            def refund_buyer(self, *args):
                raise AssertionError('A historical pending flag must not resend a refund.')

        with SessionLocal() as db, patch.dict(os.environ, {'SETTLEMENT_ENABLED': 'true'}):
            check_renomination_deadlines(db)
            check_renomination_deadlines(db)
            row = db.query(models.PurchaseReview).one()
            self.assertEqual((row.review_state, row.decision, row.settlement_state),
                             ('RESOLVED', 'VALID_CLAIM', 'UNKNOWN'))
            self.assertIsNone(db.get(models.User, self.fixture.ids['seller']).banned_until)
            self.assertEqual(db.query(models.AuditLog).filter_by(action='PURCHASE_VALID_CLAIM').count(), 1)
            process_settlements(db, NeverSend())
            self.assertEqual(row.settlement_state, 'UNKNOWN')


@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'), 'Dedicated PostgreSQL fixture required for migration SQL')
class PurchaseMigrationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_postgres as postgres_fixtures
        postgres_fixtures.PostgreSQLConcurrencyTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        import test_postgres as postgres_fixtures
        postgres_fixtures.PostgreSQLConcurrencyTests.tearDownClass.__func__(cls)

    def setUp(self):
        import test_postgres as postgres_fixtures
        postgres_fixtures.PostgreSQLConcurrencyTests.setUp(self)

    def tearDown(self):
        import test_postgres as postgres_fixtures
        postgres_fixtures.PostgreSQLConcurrencyTests.tearDown(self)

    def migrate(self):
        migration_dir = Path(__file__).parents[1] / 'migrations'
        script = (migration_dir / 'purchase_reviews.sql').read_text(encoding='utf-8')
        go_script = (migration_dir / 'dlocal_go.sql').read_text(encoding='utf-8')
        # Existing fixture validates this internally generated schema before cleanup.
        with self.raw_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.exec_driver_sql('SET search_path TO "' + self.schema + '"')
            try:
                connection.exec_driver_sql(script)
                connection.exec_driver_sql(go_script)
            finally:
                # The script owns BEGIN/COMMIT; a failed statement must not hide
                # its real error behind RESET running in an aborted transaction.
                connection.exec_driver_sql('ROLLBACK')
                connection.exec_driver_sql('RESET search_path')

    def legacy_transaction(self, state, status):
        with self.Session() as db:
            ticket = models.Ticket(
                seller_id=self.users['seller'], buyer_id=self.users['buyer'],
                event_name='Historical purchase', event_date=datetime.now(timezone.utc) - timedelta(days=3),
                event_end_date=None, zone='General', ticketing_company='teleticket',
                ticket_type='no_nominada', price=100, estado=state,
                qr_hash_sha256=uuid.uuid4().hex, qr_image_url_encrypted='legacy.enc',
            )
            db.add(ticket)
            db.flush()
            tx = models.Transaction(
                ticket_id=ticket.id, buyer_id=self.users['buyer'], status=status,
                culqi_charge_id='chr_test_' + uuid.uuid4().hex,
                amount_total=100, commission_platform=10, amount_seller=90,
            )
            db.add(tx)
            db.commit()
            return tx.id

    def test_migration_adds_missing_tables_and_columns_to_legacy_schema(self):
        tx_id = self.legacy_transaction(models.TicketState.VENDIDA, 'SUCCEEDED')
        # Recreate the pre-feature shape only inside this fixture's private schema.
        with self.raw_engine.begin() as connection:
            connection.exec_driver_sql('SET LOCAL search_path TO "' + self.schema + '"')
            connection.exec_driver_sql('DROP TABLE dispute_evidence')
            connection.exec_driver_sql('DROP TABLE financial_operations')
            connection.exec_driver_sql('DROP TABLE purchase_reviews')
            connection.exec_driver_sql('ALTER TABLE users DROP COLUMN rating, DROP COLUMN warning_count')
            connection.exec_driver_sql('ALTER TABLE tickets DROP COLUMN event_end_date')
        self.migrate()
        self.migrate()
        with self.Session() as db:
            row = db.query(models.PurchaseReview).filter_by(transaction_id=tx_id).one()
            self.assertIsNotNone(row.id)
            self.assertIsNotNone(row.created_at)
            self.assertEqual(row.review_state, 'HELD')
            self.assertIsNone(row.closes_at)
            user = db.get(models.User, self.users['buyer'])
            self.assertEqual((user.rating, user.warning_count), (Decimal('4'), 0))

    def test_terminal_history_survives_two_migrations_without_reputation_or_money_replay(self):
        payout_id = self.legacy_transaction(models.TicketState.LIBERADA, 'SUCCEEDED')
        refund_id = self.legacy_transaction(models.TicketState.REEMBOLSADA, 'REFUNDED')
        with self.Session() as db:
            db.get(models.User, self.users['buyer']).rating = Decimal('4.50')
            db.get(models.User, self.users['seller']).rating = Decimal('3.25')
            db.get(models.User, self.users['seller']).warning_count = 2
            db.commit()
        self.migrate()
        self.migrate()

        class NeverSend:
            def release_funds_to_seller(self, *args):
                raise AssertionError('Migration must never resend historical payouts.')

            def refund_buyer(self, *args):
                raise AssertionError('Migration must never resend historical refunds.')

        with self.Session() as db, patch.dict(os.environ, {'SETTLEMENT_ENABLED': 'true'}):
            rows = db.query(models.PurchaseReview).filter(
                models.PurchaseReview.transaction_id.in_([payout_id, refund_id]),
            ).all()
            self.assertEqual(len(rows), 2)
            self.assertEqual({row.decision for row in rows}, {'LEGACY_PAYOUT', 'LEGACY_REFUND'})
            for row in rows:
                self.assertEqual((row.review_state, row.settlement_state), ('RESOLVED', 'SUCCEEDED'))
                self.assertTrue(row.reputation_applied)
                self.assertIsNone(row.settlement_reference)
            process_settlements(db, NeverSend())
            self.assertEqual(db.get(models.User, self.users['buyer']).rating, Decimal('4.50'))
            seller = db.get(models.User, self.users['seller'])
            self.assertEqual((seller.rating, seller.warning_count), (Decimal('3.25'), 2))

    def test_pending_legacy_refund_is_visible_but_not_automatically_resent(self):
        tx_id = self.legacy_transaction(models.TicketState.PENDIENTE_RENOMINACION, 'REFUND_PENDING')
        self.migrate()
        self.migrate()
        with self.Session() as db:
            rows = db.query(models.PurchaseReview).filter_by(transaction_id=tx_id).all()
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual((row.review_state, row.decision, row.settlement_state),
                             ('RESOLVED', 'VALID_CLAIM', 'UNKNOWN'))
            self.assertFalse(row.reputation_applied)
            self.assertIsNone(row.settlement_reference)
            self.assertIsNotNone(row.settlement_error)
