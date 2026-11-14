"""Campaign dates, immutable prices and one-use rewards; no external services."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest
import uuid
from unittest.mock import patch

import test_api as fixtures
from backend import models
from backend.database import SessionLocal
from backend.money import amounts


class CampaignPolicyTests(unittest.TestCase):
    def test_campaign_has_exact_peru_midnight_boundaries(self):
        from backend.promotions import in_launch_window
        start = datetime(2026, 11, 13, 5, tzinfo=timezone.utc)
        end = datetime(2026, 12, 13, 5, tzinfo=timezone.utc)
        self.assertEqual(end - start, timedelta(days=30))
        for instant, expected in [(start - timedelta(microseconds=1), False),
                                  (start, True), (end - timedelta(microseconds=1), True), (end, False)]:
            with self.subTest(instant=instant):
                self.assertEqual(in_launch_window(instant), expected)

    def test_discount_is_funded_by_tickia_and_does_not_reduce_seller_base(self):
        self.assertEqual(amounts('100', Decimal('.05'), Decimal('5')),
                         (Decimal('95.00'), Decimal('5.00'), Decimal('95.00')))
        self.assertEqual(amounts('100', Decimal('.10'), Decimal('5')),
                         (Decimal('95.00'), Decimal('10.00'), Decimal('90.00')))

    def test_rounding_is_in_cents_and_invalid_discounts_are_rejected(self):
        self.assertEqual(amounts('100.10', Decimal('.05'), Decimal('5.01')),
                         (Decimal('95.09'), Decimal('5.01'), Decimal('95.09')))
        for discount in ('-1', '101', 'NaN'):
            with self.subTest(discount=discount), self.assertRaises(ValueError):
                amounts('100', Decimal('.05'), Decimal(discount))


class PromotionAPITests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.APITests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.client = self.fixture.client
        self.window = patch('backend.promotions.in_launch_window', return_value=True)
        self.window.start()
        self.addCleanup(self.window.stop)

    def dashboard(self):
        response = self.client.get('/api/referrals', headers=self.fixture.auth())
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def invite(self):
        code = self.dashboard()['referral_code']
        return self.client.post('/api/auth/register', json={
            'email': 'invited-' + uuid.uuid4().hex + '@example.com',
            'password': fixtures.PASSWORD, 'phone_number': '900000001', 'referral_code': code})

    def grant(self):
        self.assertEqual(self.invite().status_code, 201)
        self.assertEqual(self.dashboard()['reward_status'], 'AVAILABLE')

    def ticket(self, price='100'):
        response = self.fixture.upload(price=price,
            event_date='2099-12-01T20:00:00-05:00', event_end_date='2099-12-02T01:00:00-05:00',
            data=fixtures.image_bytes('https://teleticket.com.pe/ticket/' + uuid.uuid4().hex))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def reserve(self, ticket):
        response = self.fixture.reserve(ticket['id'])
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_publication_keeps_five_percent_after_campaign_ends(self):
        ticket = self.ticket()
        self.assertEqual(ticket['commission_rate'], .05)
        with patch('backend.promotions.in_launch_window', return_value=False):
            self.reserve(ticket)
            self.assertEqual(self.fixture.charge(ticket['id']).status_code, 200)
        with SessionLocal() as db:
            tx = db.query(models.Transaction).one()
            self.assertEqual((tx.amount_total, tx.commission_platform, tx.amount_seller),
                             (Decimal('100'), Decimal('5'), Decimal('95')))
            self.assertEqual(tx.commission_rate, Decimal('.05'))

    def test_outside_campaign_publication_uses_ten_percent(self):
        with patch('backend.promotions.in_launch_window', return_value=False):
            self.assertEqual(self.ticket()['commission_rate'], .10)

    def test_two_registrations_grant_one_reward_only_to_inviter(self):
        self.grant()
        self.assertEqual(self.invite().status_code, 201)
        self.assertEqual(self.dashboard()['qualifying_referral_count'], 2)
        with SessionLocal() as db:
            rewards = db.query(models.ReferralReward).all()
            self.assertEqual(len(rewards), 1)
            self.assertEqual(rewards[0].user_id, self.fixture.ids['buyer'])

    def test_registration_outside_campaign_does_not_grant_reward(self):
        with patch('backend.promotions.in_launch_window', return_value=False):
            self.assertEqual(self.invite().status_code, 201)
        self.assertEqual(self.dashboard()['reward_status'], 'NOT_EARNED')

    def test_invalid_referral_does_not_partially_create_account(self):
        email = 'bad-invite@example.com'
        response = self.client.post('/api/auth/register', json={
            'email': email, 'password': fixtures.PASSWORD, 'phone_number': '900000002',
            'referral_code': 'unknown-referral-code'})
        self.assertEqual(response.status_code, 422)
        with SessionLocal() as db:
            self.assertIsNone(db.query(models.User).filter_by(email=email).first())

    def test_existing_account_cannot_register_again_to_qualify(self):
        code = self.dashboard()['referral_code']
        response = self.client.post('/api/auth/register', json={
            'email': 'buyer@example.com', 'password': fixtures.PASSWORD,
            'phone_number': '900000003', 'referral_code': code})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.dashboard()['reward_status'], 'NOT_EARNED')

    def test_first_discounted_payment_and_duplicate_webhook_consume_once(self):
        self.grant()
        ticket = self.ticket()
        quote = self.reserve(ticket)
        self.assertEqual((quote['amount_total_cents'], quote['buyer_discount']), (9500, 5))
        self.assertEqual(self.dashboard()['reward_status'], 'RESERVED')
        response = self.client.post('/api/payments/charge', headers=self.fixture.auth(), json={
            'ticket_id': ticket['id'], 'culqi_token': 'tkn_test_' + uuid.uuid4().hex,
            'reservation_id': quote['reservation_id'], 'amount_total': 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.dashboard()['reward_status'], 'USED')
        charge = next(iter(self.fixture.provider.charges.values()))
        self.assertEqual(charge['amount'], 9500)
        metrics = self.client.get('/api/admin/metrics', headers=self.fixture.auth('admin')).json()
        self.assertEqual((metrics['total_revenue'], metrics['total_buyer_discounts'], metrics['platform_after_discounts']),
                         (5, 5, 0))
        for _ in range(2):
            event = self.client.post('/api/payments/webhook/culqi', json={
                'type': 'charge.creation.succeeded', 'data': {'id': charge['id']}})
            self.assertEqual(event.status_code, 200, event.text)
        self.assertEqual(self.invite().status_code, 201)
        self.assertEqual(self.dashboard()['reward_status'], 'USED')
        with SessionLocal() as db:
            tx = db.query(models.Transaction).one()
            self.assertEqual((tx.listed_amount, tx.buyer_discount, tx.amount_seller),
                             (Decimal('100'), Decimal('5'), Decimal('95')))
            reward = db.get(models.ReferralReward, self.fixture.ids['buyer'])
            self.assertEqual(reward.used_transaction_id, tx.id)
            self.assertIsNone(reward.reserved_transaction_id)
        next_ticket = self.ticket()
        self.assertEqual(self.reserve(next_ticket)['amount_total_cents'], 10000)

    def test_reward_does_not_expire_with_the_campaign(self):
        self.grant()
        with patch('backend.promotions.in_launch_window', return_value=False):
            ticket = self.ticket()
            self.assertEqual(self.reserve(ticket)['amount_total_cents'], 9500)
            self.assertEqual(self.fixture.charge(ticket['id']).status_code, 200)
        with SessionLocal() as db:
            tx = db.query(models.Transaction).one()
            self.assertEqual(tx.commission_platform, Decimal('10'))
            self.assertEqual(tx.amount_seller, Decimal('90'))

    def test_second_concurrent_reservation_cannot_claim_same_reward(self):
        self.grant()
        first, second = self.ticket(), self.ticket()
        self.reserve(first)
        response = self.fixture.reserve(second['id'])
        self.assertEqual(response.status_code, 409, response.text)
        with SessionLocal() as db:
            self.assertEqual(db.get(models.Ticket, uuid.UUID(second['id'])).estado, models.TicketState.DISPONIBLE)

    def test_definitive_decline_releases_reward_but_uncertain_payment_does_not(self):
        self.grant()
        first = self.ticket()
        self.reserve(first)
        self.fixture.provider.mode = 'declined'
        self.assertEqual(self.fixture.charge(first['id']).status_code, 402)
        self.assertEqual(self.dashboard()['reward_status'], 'AVAILABLE')
        second = self.ticket()
        self.reserve(second)
        self.fixture.provider.mode = 'timeout'
        self.assertEqual(self.fixture.charge(second['id']).status_code, 502)
        with SessionLocal() as db:
            reward = db.get(models.ReferralReward, self.fixture.ids['buyer'])
            reward.reserved_until = datetime.now(timezone.utc) - timedelta(days=1)
            db.commit()
        self.assertEqual(self.dashboard()['reward_status'], 'RESERVED')

    def test_definitive_decline_can_retry_the_same_ticket_and_quote(self):
        self.grant()
        ticket = self.ticket()
        quote = self.reserve(ticket)
        self.fixture.provider.mode = 'declined'
        self.assertEqual(self.fixture.charge(ticket['id']).status_code, 402)
        self.fixture.provider.mode = 'ok'
        response = self.client.post('/api/payments/charge', headers=self.fixture.auth(), json={
            'ticket_id': ticket['id'], 'reservation_id': quote['reservation_id'],
            'culqi_token': 'tkn_test_' + uuid.uuid4().hex})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.dashboard()['reward_status'], 'USED')

    def test_expired_hold_without_transaction_is_available_again(self):
        self.grant()
        self.reserve(self.ticket())
        with SessionLocal() as db:
            reward = db.get(models.ReferralReward, self.fixture.ids['buyer'])
            reward.reserved_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.dashboard()['reward_status'], 'AVAILABLE')
        self.assertEqual(self.reserve(self.ticket())['amount_total_cents'], 9500)

    def test_low_discounted_total_does_not_send_invalid_culqi_charge(self):
        self.grant()
        ticket = self.ticket(price='3')
        response = self.fixture.reserve(ticket['id'])
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.fixture.provider.calls, 0)
        self.assertEqual(self.dashboard()['reward_status'], 'AVAILABLE')

    def test_stale_quote_is_rejected_before_contacting_provider(self):
        self.grant()
        ticket = self.ticket()
        self.reserve(ticket)
        response = self.client.post('/api/payments/charge', headers=self.fixture.auth(), json={
            'ticket_id': ticket['id'], 'reservation_id': str(uuid.uuid4()),
            'culqi_token': 'tkn_test_' + uuid.uuid4().hex})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.fixture.provider.calls, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
