"""Go's concurrency and additive migration tested in an isolated PostgreSQL schema."""
import json
import os
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import test_postgres as pg
from backend import models
from backend.go_fees import fee_terms
from backend.go_profiles import identity_hash, account_hash


@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'), 'Dedicated PostgreSQL is required')
class GoPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.PostgreSQLConcurrencyTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        pg.PostgreSQLConcurrencyTests.tearDownClass.__func__(cls)

    def setUp(self):
        pg.PostgreSQLConcurrencyTests.setUp(self)
        self.addCleanup(pg.PostgreSQLConcurrencyTests.tearDown, self)
        self.env = patch.dict(os.environ, {'PAYMENT_PROVIDER': 'dlocal_go', 'SETTLEMENT_ENABLED': 'true',
            'DLOCAL_GO_PAYIN_PERCENT': '3.53', 'DLOCAL_GO_PAYIN_FIXED_PEN': '0',
            'DLOCAL_GO_PAYOUT_PERCENT': '0', 'DLOCAL_GO_PAYOUT_FIXED_PEN': '1',
            'DLOCAL_GO_FEES_TAX_PERCENT': '0', 'DLOCAL_GO_MIN_PAYOUT_PEN': '5',
            'DLOCAL_GO_PAYOUT_PURPOSE': 'ENTERTAINMENT'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls = []
        self.guard = threading.Lock()
        with self.Session() as db:
            email = db.get(models.User, self.users['seller']).email
            beneficiary_id = uuid.uuid4().int % 1000000000 + 1
            bank_id = uuid.uuid4().int % 1000000000 + 1
            self.beneficiary = {'id': beneficiary_id, 'status': 'VERIFIED', 'flow_type': 'B2C', 'country': 'PE',
                'document_type': 'DNI', 'document': f'{uuid.uuid4().int % 100000000:08d}', 'email': email,
                'bank_accounts': [{'id': bank_id, 'country': 'PE', 'currency': 'PEN', 'bank_code': '002',
                                   'bank_account': '00200000000000000001', 'account_type': 'SAVINGS'}]}
            db.add(models.PayoutProfile(user_id=self.users['seller'], beneficiary_id=str(beneficiary_id), bank_account_id=bank_id,
                status='VERIFIED', account_last4='0001', identity_hash=identity_hash(self.beneficiary),
                account_hash=account_hash(self.beneficiary['bank_accounts'][0]), fee_terms_hash=fee_terms()['hash']))
            db.get(models.Ticket, self.ticket_id).event_end_date = datetime.now(timezone.utc) + timedelta(days=4)
            db.commit()

    def tearDown(self):
        pass  # addCleanup also runs when setUp fails, restoring env and DB overrides.

    post = pg.PostgreSQLConcurrencyTests.post
    parallel = pg.PostgreSQLConcurrencyTests.parallel

    def provider(self):
        case = self
        class Provider:
            def configured(self): return True
            def enabled(self): return True
            def payouts_enabled(self): return True
            def notification_url(self): return 'https://tickia.example/api/payments/webhooks/dlocal-go'
            def retrieve_beneficiary(self, ref): return case.beneficiary
            def create_checkout(self, order, amount, email):
                with case.guard: case.calls.append(order)
                return {'id': 'DP-' + order, 'redirect_url': 'https://checkout-sbx.dlocalgo.com/validate/test'}
            def submit_payout(self, body, key):
                with case.guard: case.calls.append(key)
                self.body = body
                return {'payout_id': 'PO-' + key, 'amount': body['transfer_amount'], 'currency_to_pay': 'PEN', 'status': 'PENDING'}
            def retrieve_payout(self, ref):
                return {**self.body, 'payout_id': ref, 'amount': self.body['transfer_amount'],
                        'currency_to_pay': 'PEN', 'status': 'COMPLETED'}
        return Provider()

    def test_two_go_checkout_requests_create_one_provider_order(self):
        from backend.routers import dlocal
        self.assertEqual(self.post('/api/tickets/' + str(self.ticket_id) + '/buy').status_code, 200)
        with patch.object(dlocal, 'get_go_provider', lambda: self.provider()):
            responses = self.parallel(lambda i: self.post('/api/payments/checkout', body={'ticket_id': str(self.ticket_id)}))
        self.assertTrue(all(r.status_code in (200, 409) for r in responses), [r.text for r in responses])
        self.assertEqual(len(self.calls), 1)

    def test_two_go_workers_transfer_and_reward_once(self):
        from backend.go_settlements import process_go_settlements
        review_id = pg.PostgreSQLConcurrencyTests.paid_review(self, resolved=True)
        with self.Session() as db:
            row = db.get(models.PurchaseReview, review_id)
            tx = db.get(models.Transaction, row.transaction_id)
            tx.payment_provider = 'dlocal_go'
            tx.provider_payment_id = 'DP-' + str(tx.id)
            tx.available_after = datetime.now(timezone.utc) - timedelta(days=1)
            tx.payout_terms = json.dumps(fee_terms())
            db.commit()
        provider = self.provider()
        def run(index):
            with self.Session() as db: process_go_settlements(db, provider)
        self.parallel(run)
        self.assertEqual(len(self.calls), 1)
        with self.Session() as db:
            self.assertEqual(db.query(models.FinancialOperation).filter_by(review_id=review_id).count(), 1)
            self.assertEqual(db.get(models.PurchaseReview, review_id).settlement_state, 'SUCCEEDED')
            self.assertEqual(db.get(models.User, self.users['seller']).rating, Decimal('4.25'))

    def test_go_migration_is_repeatable_and_preserves_legacy_charge(self):
        review_id = pg.PostgreSQLConcurrencyTests.paid_review(self, resolved=False)
        with self.Session() as db:
            tx_id = db.get(models.PurchaseReview, review_id).transaction_id
            original = db.get(models.Transaction, tx_id).culqi_charge_id
        sql = (Path(__file__).parents[1] / 'migrations/dlocal_go.sql').read_text(encoding='utf-8')
        with self.raw_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
            con.exec_driver_sql('SET search_path TO "' + self.schema + '"')
            try:
                # Simulate permissive hosted-database defaults before migration.
                con.exec_driver_sql('GRANT ALL ON payout_profiles, financial_operations TO PUBLIC')
                con.exec_driver_sql(sql)
                con.exec_driver_sql(sql)
                rows = con.exec_driver_sql("SELECT relname, relrowsecurity FROM pg_class "
                    "WHERE relnamespace = current_schema()::regnamespace "
                    "AND relname IN ('payout_profiles','financial_operations')").all()
                self.assertEqual(dict(rows), {'payout_profiles': True, 'financial_operations': True})
                public_grants = con.exec_driver_sql("SELECT count(*) FROM information_schema.table_privileges "
                    "WHERE table_schema = current_schema() AND grantee = 'PUBLIC' "
                    "AND table_name IN ('payout_profiles','financial_operations')").scalar()
                self.assertEqual(public_grants, 0)
            finally:
                con.exec_driver_sql('ROLLBACK')
                con.exec_driver_sql('RESET search_path')
        with self.Session() as db:
            self.assertEqual(db.get(models.Transaction, tx_id).culqi_charge_id, original)
            self.assertEqual(db.get(models.Transaction, tx_id).payment_provider, 'culqi')
