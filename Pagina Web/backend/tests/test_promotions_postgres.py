"""Real PostgreSQL promotion locks and repeatable migration in a private schema."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
import threading
import unittest
import uuid
from unittest.mock import patch

import test_postgres as pg
from backend import models
from backend.promotions import fail_transaction
from backend.routers import payments


@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'), 'Dedicated PostgreSQL is required')
class PromotionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.PostgreSQLConcurrencyTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        pg.PostgreSQLConcurrencyTests.tearDownClass.__func__(cls)

    def setUp(self):
        pg.PostgreSQLConcurrencyTests.setUp(self)
        self.addCleanup(pg.PostgreSQLConcurrencyTests.tearDown, self)
        self.calls, self.guard = [], threading.Lock()
        with self.Session() as db:
            from backend.campaigns import default_campaign
            campaign = default_campaign()
            if db.get(models.PromotionCampaign, campaign.id) is None:
                db.add(campaign)
            ticket = db.get(models.Ticket, self.ticket_id)
            ticket.commission_rate = Decimal('.05')
            db.add(models.ReferralReward(user_id=self.users['buyer']))
            db.commit()

    post = pg.PostgreSQLConcurrencyTests.post
    parallel = pg.PostgreSQLConcurrencyTests.parallel

    def other_ticket(self):
        with self.Session() as db:
            ticket = models.Ticket(seller_id=self.users['seller'], event_name='Another promotion ticket',
                event_date=datetime.now(timezone.utc) + timedelta(days=3), zone='General',
                ticketing_company='teleticket', ticket_type='no_nominada', price=100,
                commission_rate=Decimal('.05'), qr_hash_sha256=uuid.uuid4().hex,
                qr_image_url_encrypted='fixture.enc', hash_estado=models.HashState.ACTIVO,
                estado=models.TicketState.DISPONIBLE)
            db.add(ticket)
            db.flush()
            ticket_id = ticket.id
            db.commit()
            return ticket_id

    def provider(self, entered=None, release=None):
        case = self
        class Provider:
            def enabled(self):
                return True

            def create_charge(self, token, amount_cents, email, metadata):
                with case.guard:
                    case.calls.append(amount_cents)
                if entered is not None:
                    entered.set()
                    if not release.wait(timeout=15):
                        raise RuntimeError('Test synchronization timed out')
                return {'object': 'charge', 'id': 'chr_test_' + uuid.uuid4().hex,
                        'amount': amount_cents, 'currency_code': 'PEN', 'capture': True,
                        'outcome': {'type': 'venta_exitosa'}, 'amount_refunded': 0,
                        'dispute': False, 'metadata': metadata}
        return Provider()

    def charge(self, ticket_id, reservation_id):
        return self.post('/api/payments/charge', body={
            'ticket_id': str(ticket_id), 'reservation_id': reservation_id,
            'culqi_token': 'tkn_test_' + uuid.uuid4().hex})

    def test_two_tickets_competing_for_one_reward_have_one_discounted_reservation(self):
        identifiers = [self.ticket_id, self.other_ticket()]
        responses = self.parallel(lambda index: self.post('/api/tickets/' + str(identifiers[index]) + '/buy'))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409], [r.text for r in responses])
        winner = next(r.json() for r in responses if r.status_code == 200)
        self.assertEqual(winner['amount_total_cents'], 9500)
        with self.Session() as db:
            reward = db.get(models.ReferralReward, self.users['buyer'])
            self.assertEqual(str(reward.reserved_ticket_id), winner['ticket_id'])
            self.assertIsNone(reward.reserved_transaction_id)

    def test_expired_crossed_holds_lock_rewards_in_one_stable_order(self):
        second = self.other_ticket()
        with self.Session() as db:
            own = db.get(models.ReferralReward, self.users['buyer'])
            own.reserved_ticket_id = second
            own.reserved_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.add(models.ReferralReward(user_id=self.users['other'], reserved_ticket_id=self.ticket_id,
                reserved_until=datetime.now(timezone.utc) - timedelta(seconds=1)))
            db.commit()
        results = self.parallel(lambda index: self.post(
            '/api/tickets/' + str(self.ticket_id if index == 0 else second) + '/buy',
            role='buyer' if index == 0 else 'other'))
        self.assertEqual([r.status_code for r in results], [200, 200], [r.text for r in results])
        self.assertEqual([r.json()['amount_total_cents'] for r in results], [9500, 9500])

    def test_concurrent_charges_consume_reward_once(self):
        quote = self.post('/api/tickets/' + str(self.ticket_id) + '/buy').json()
        with patch.object(payments, 'get_payment_provider', self.provider):
            responses = self.parallel(lambda index: self.charge(self.ticket_id, quote['reservation_id']))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409], [r.text for r in responses])
        self.assertEqual(self.calls, [9500])
        with self.Session() as db:
            reward = db.get(models.ReferralReward, self.users['buyer'])
            tx = db.get(models.Transaction, reward.used_transaction_id)
            self.assertEqual((tx.status, tx.buyer_discount, tx.amount_seller),
                             ('SUCCEEDED', Decimal('5'), Decimal('95')))
            self.assertIsNone(reward.reserved_transaction_id)

    def test_two_buyers_compete_for_one_next_sale_waiver(self):
        second = self.other_ticket()
        with self.Session() as db:
            db.delete(db.get(models.ReferralReward, self.users['buyer']))
            db.add(models.ReferralReward(user_id=self.users['seller'], reward_kind='SELLER_REFERRAL',
                buyer_discount_rate=Decimal('.10'), seller_commission_rate=Decimal('0'), choice='SELL'))
            db.commit()
        results = self.parallel(lambda index: self.post('/api/tickets/' + str(self.ticket_id if index == 0 else second) + '/buy',
            role='buyer' if index == 0 else 'other'))
        self.assertEqual(sorted(r.status_code for r in results), [200, 409], [r.text for r in results])
        winner = next(r.json() for r in results if r.status_code == 200)
        self.assertEqual(winner['commission_rate'], 0)

    def test_simultaneous_first_listings_qualify_referred_seller_once(self):
        from backend.promotions import qualify_seller_referral
        with self.Session() as db:
            db.add(models.Referral(referred_user_id=self.users['other'], referrer_id=self.users['buyer'], qualified=True))
            db.commit()
        def publish(_):
            with self.Session() as db:
                ticket = models.Ticket(seller_id=self.users['other'], event_name='First concurrent listing',
                    event_date=datetime.now(timezone.utc) + timedelta(days=3), zone='General',
                    ticketing_company='teleticket', ticket_type='no_nominada', price=100,
                    commission_rate=Decimal('.05'), qr_hash_sha256=uuid.uuid4().hex, qr_image_url_encrypted='fixture.enc')
                db.add(ticket)
                db.flush()
                qualify_seller_referral(db, ticket)
                identifier = ticket.id
                db.commit()
                return identifier
        with patch('backend.promotions.in_launch_window', return_value=True):
            identifiers = self.parallel(publish)
        with self.Session() as db:
            referral = db.get(models.Referral, self.users['other'])
            self.assertIn(referral.seller_ticket_id, identifiers)
            self.assertIsNotNone(referral.seller_qualified_at)
            reward = db.get(models.ReferralReward, self.users['buyer'])
            self.assertEqual((reward.reward_kind, reward.buyer_discount_rate, reward.choice), ('SELLER_REFERRAL', Decimal('.10'), None))
            self.assertEqual(db.query(models.AuditLog).filter_by(user_id=self.users['buyer'], action='SELLER_REFERRAL_QUALIFIED').count(), 1)

    def test_two_distinct_rewards_on_one_payment_consume_atomically(self):
        with self.Session() as db:
            db.add(models.ReferralReward(user_id=self.users['seller'], reward_kind='SELLER_REFERRAL',
                buyer_discount_rate=Decimal('.10'), seller_commission_rate=Decimal('0'), choice='SELL'))
            db.commit()
        quote = self.post('/api/tickets/' + str(self.ticket_id) + '/buy').json()
        with patch.object(payments, 'get_payment_provider', self.provider):
            results = self.parallel(lambda _: self.charge(self.ticket_id, quote['reservation_id']))
        self.assertEqual(sorted(r.status_code for r in results), [200, 409], [r.text for r in results])
        self.assertEqual(self.calls, [9500])
        with self.Session() as db:
            rewards = db.query(models.ReferralReward).filter(models.ReferralReward.user_id.in_(
                [self.users['seller'], self.users['buyer']])).all()
            self.assertEqual(len({r.used_transaction_id for r in rewards}), 1)
            self.assertTrue(all(r.used_transaction_id for r in rewards))

    def test_expiry_during_provider_call_cannot_release_bound_reward(self):
        from backend.promotions import expire_hold
        quote = self.post('/api/tickets/' + str(self.ticket_id) + '/buy').json()
        entered, release = threading.Event(), threading.Event()
        with patch.object(payments, 'get_payment_provider', lambda: self.provider(entered, release)):
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(self.charge, self.ticket_id, quote['reservation_id'])
                try:
                    self.assertTrue(entered.wait(timeout=10))
                    with self.Session() as db:
                        reward = db.query(models.ReferralReward).filter_by(
                            user_id=self.users['buyer']).with_for_update().one()
                        self.assertIsNotNone(reward.reserved_transaction_id)
                        reward.reserved_until = datetime.now(timezone.utc) - timedelta(days=1)
                        expire_hold(reward)
                        self.assertEqual(reward.reserved_ticket_id, self.ticket_id)
                        db.commit()
                finally:
                    release.set()
                self.assertEqual(pending.result(timeout=15).status_code, 200)

    def test_registration_concurrent_with_consumption_never_rearms_reward(self):
        code = 'parallel-' + uuid.uuid4().hex
        with self.Session() as db:
            db.get(models.User, self.users['buyer']).referral_code = code
            db.commit()
        quote = self.post('/api/tickets/' + str(self.ticket_id) + '/buy').json()
        def action(index):
            if index == 0:
                return self.charge(self.ticket_id, quote['reservation_id'])
            with pg.TestClient(pg.app) as client:
                return client.post('/api/auth/register', json={
                    'email': 'concurrent-referral-' + uuid.uuid4().hex + '@example.com',
                    'password': 'TestPassword123!', 'phone_number': '900000005', 'referral_code': code})
        with patch.object(payments, 'get_payment_provider', self.provider), \
                patch('backend.promotions.in_launch_window', return_value=True):
            responses = self.parallel(action)
        self.assertEqual([r.status_code for r in responses], [200, 201], [r.text for r in responses])
        with self.Session() as db:
            reward = db.get(models.ReferralReward, self.users['buyer'])
            self.assertIsNotNone(reward.used_transaction_id)
            self.assertIsNone(reward.reserved_ticket_id)
            self.assertEqual(db.query(models.ReferralReward).filter_by(user_id=self.users['buyer']).count(), 1)

    def test_old_failed_transaction_cannot_release_a_reassigned_reward(self):
        second = self.other_ticket()
        with self.Session() as db:
            tx = models.Transaction(ticket_id=self.ticket_id, buyer_id=self.users['buyer'], status='FAILED',
                listed_amount=100, buyer_discount=5, buyer_discount_rate=Decimal('.05'), commission_rate=Decimal('.05'),
                amount_total=95, commission_platform=5, amount_seller=95,
                referral_reward_user_id=self.users['buyer'])
            db.add(tx)
            db.flush()
            old_id = tx.id
            db.commit()
        quote = self.post('/api/tickets/' + str(second) + '/buy').json()
        with self.Session() as db:
            fail_transaction(db, old_id)
            db.commit()
            reward = db.get(models.ReferralReward, self.users['buyer'])
            self.assertEqual(reward.reserved_ticket_id, second)
        with patch.object(payments, 'get_payment_provider', self.provider):
            response = self.charge(second, quote['reservation_id'])
        self.assertEqual(response.status_code, 200, response.text)

    def test_migration_backfills_tickets_but_never_reprices_history_or_grants_old_rewards(self):
        # Destructive simulation is confined to the internally generated schema.
        self.assertRegex(self.schema, r'^tickia_test_[a-f0-9]{32}$')
        first, last = self.other_ticket(), self.other_ticket()
        review_id = pg.PostgreSQLConcurrencyTests.paid_review(self, resolved=False)
        with self.Session() as db:
            db.get(models.Ticket, self.ticket_id).created_at = datetime(2026, 11, 13, 5, tzinfo=timezone.utc)
            db.get(models.Ticket, first).created_at = datetime(2026, 11, 13, 4, 59, 59, tzinfo=timezone.utc)
            db.get(models.Ticket, last).created_at = datetime(2026, 12, 13, 5, tzinfo=timezone.utc)
            tx_id = db.get(models.PurchaseReview, review_id).transaction_id
            buyer = db.get(models.User, self.users['buyer'])
            buyer.referral_count = 10
            buyer.referral_code = 'legacy-' + uuid.uuid4().hex
            code = buyer.referral_code
            db.commit()
        sql = (Path(__file__).parents[1] / 'migrations/launch_promotions.sql').read_text(encoding='utf-8')
        controls = (Path(__file__).parents[1] / 'migrations/campaign_controls.sql').read_text(encoding='utf-8')
        with self.raw_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as con:
            con.exec_driver_sql('SET search_path TO "' + self.schema + '"')
            try:
                con.exec_driver_sql('DROP TABLE referrals, referral_rewards')
                for column in ('commission_rate', 'reservation_id', 'reservation_total', 'reservation_discount'):
                    con.exec_driver_sql('ALTER TABLE tickets DROP COLUMN ' + column + ' CASCADE')
                for column in ('listed_amount', 'buyer_discount', 'commission_rate', 'referral_reward_user_id'):
                    con.exec_driver_sql('ALTER TABLE transactions DROP COLUMN ' + column + ' CASCADE')
                con.exec_driver_sql(sql)
                con.exec_driver_sql(sql)
                con.exec_driver_sql(controls)
                con.exec_driver_sql(controls)
                rls = dict(con.exec_driver_sql("SELECT relname, relrowsecurity FROM pg_class "
                    "WHERE relnamespace=current_schema()::regnamespace AND relname IN ('referrals','referral_rewards')").all())
                self.assertEqual(rls, {'referrals': True, 'referral_rewards': True})
                grants = con.exec_driver_sql("SELECT count(*) FROM information_schema.table_privileges WHERE "
                    "table_schema=current_schema() AND grantee='PUBLIC' AND table_name IN ('referrals','referral_rewards')").scalar()
                self.assertEqual(grants, 0)
            finally:
                con.exec_driver_sql('ROLLBACK')
                con.exec_driver_sql('RESET search_path')
        with self.Session() as db:
            self.assertEqual(db.get(models.Ticket, self.ticket_id).commission_rate, Decimal('.05'))
            self.assertEqual(db.get(models.Ticket, first).commission_rate, Decimal('.10'))
            self.assertEqual(db.get(models.Ticket, last).commission_rate, Decimal('.10'))
            tx = db.get(models.Transaction, tx_id)
            self.assertEqual((tx.amount_total, tx.commission_platform, tx.amount_seller, tx.status),
                             (Decimal('100'), Decimal('10'), Decimal('90'), 'SUCCEEDED'))
            self.assertEqual(tx.buyer_discount, 0)
            self.assertIsNone(tx.listed_amount)
            self.assertEqual(db.get(models.User, self.users['buyer']).referral_code, code)
            self.assertIsNone(db.get(models.ReferralReward, self.users['buyer']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
