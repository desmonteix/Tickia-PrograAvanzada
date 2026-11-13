"""Discounted Go charges, verified seller amounts and actual-charge refunds."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import unittest
import uuid
from unittest.mock import patch

import httpx
import test_dlocal_flow as fixtures
from backend import models
from backend.database import SessionLocal
from backend.dlocal_go import DLocalGoProvider
from backend.go_settlements import process_go_settlements


class GoPromotionTests(unittest.TestCase):
    def setUp(self):
        self.go = fixtures.GoFlowTests(methodName='runTest')
        self.go.setUp()
        self.addCleanup(self.go.doCleanups)
        self.client = self.go.client
        window = patch('backend.promotions.in_launch_window', return_value=True)
        window.start()
        self.addCleanup(window.stop)
        original_http = self.go.http
        self.payin_status = None

        def http(request):
            response = original_http(request)
            if request.method == 'GET' and request.url.path == '/v1/payments/DP-1':
                value = response.json()
                if self.payin_status:
                    value['status'] = self.payin_status
                amount = Decimal(str(value['amount']))
                fee = (amount * Decimal('.0353')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                value.update(balance_fee=float(fee), balance_amount=float(amount - fee))
                return httpx.Response(200, json=value)
            return response
        self.go.gateway = DLocalGoProvider(transport=httpx.MockTransport(http))

    def auth(self, role='buyer'):
        return self.go.fixture.auth(role)

    def discounted_purchase(self, paid=True):
        response = self.client.get('/api/referrals', headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        registered = self.client.post('/api/auth/register', json={
            'email': 'go-referral-' + uuid.uuid4().hex + '@example.com',
            'password': fixtures.fixtures.PASSWORD, 'phone_number': '900000001',
            'referral_code': response.json()['referral_code']})
        self.assertEqual(registered.status_code, 201, registered.text)
        self.go.profile()
        ticket = self.go.fixture.upload(price='100')
        self.assertEqual(ticket.status_code, 200, ticket.text)
        self.ticket_id = ticket.json()['id']
        quote = self.go.fixture.reserve(self.ticket_id)
        self.assertEqual(quote.status_code, 200, quote.text)
        response = self.client.post('/api/payments/checkout', headers=self.auth(), json={
            'ticket_id': self.ticket_id, 'reservation_id': quote.json()['reservation_id']})
        self.assertEqual(response.status_code, 200, response.text)
        self.tx_id = response.json()['transaction_id']
        self.assertEqual(response.json()['amount_total'], 95)
        self.assertEqual(self.go.orders['DP-1']['amount'], 95)
        if paid:
            self.go.paid = True
            self.go.notify({'payment_id': 'DP-1'})
            return self.client.get('/api/purchases', headers=self.auth()).json()[0]
        return response.json()

    def test_discounted_payin_keeps_seller_base_and_fees_use_actual_charge(self):
        review = self.discounted_purchase()
        self.assertEqual((review['listed_amount'], review['amount_paid'], review['buyer_discount']), (100, 95, 5))
        confirmed = self.client.post('/api/purchases/' + review['purchase_id'] + '/confirm', headers=self.auth())
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        with SessionLocal() as db:
            tx = db.get(models.Transaction, uuid.UUID(self.tx_id))
            self.assertEqual((tx.commission_platform, tx.amount_seller), (Decimal('5'), Decimal('95')))
            self.assertEqual((tx.payin_fee, tx.payout_fee, tx.seller_net_amount),
                             (Decimal('3.35'), Decimal('1'), Decimal('90.65')))
            process_go_settlements(db, self.go.gateway)
            operation = db.query(models.FinancialOperation).one()
            self.assertEqual(operation.amount, Decimal('90.65'))
            operation.next_check_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            self.go.payout_status = 'COMPLETED'
            process_go_settlements(db, self.go.gateway)
            self.assertEqual(db.query(models.FinancialOperation).one().status, 'SUCCEEDED')

    def test_refund_returns_only_paid_amount_and_does_not_rearm_reward(self):
        review = self.discounted_purchase()
        from backend.post_purchase import decide, lock_review
        with SessionLocal() as db:
            row, tx, ticket = lock_review(db, uuid.UUID(review['purchase_id']))
            decide(db, row, tx, ticket, 'VALID_CLAIM', actor=self.go.fixture.ids['admin'],
                   reason='Evidencia verificada en el entorno aislado.')
            db.commit()
            process_go_settlements(db, self.go.gateway)
            self.assertEqual(db.query(models.FinancialOperation).one().amount, Decimal('95'))
            self.assertEqual(self.go.refunds['REF-1']['amount'], 95)
            self.go.refunds['REF-1']['status'] = 'SUCCESS'
            op = db.query(models.FinancialOperation).one()
            op.next_check_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            process_go_settlements(db, self.go.gateway)
        self.assertEqual(self.client.get('/api/referrals', headers=self.auth()).json()['reward_status'], 'USED')

    def test_duplicate_paid_notifications_do_not_reactivate_consumed_reward(self):
        self.discounted_purchase()
        with SessionLocal() as db:
            reward = db.get(models.ReferralReward, self.go.fixture.ids['buyer'])
            used = reward.used_transaction_id
        self.go.notify({'payment_id': 'DP-1'})
        with SessionLocal() as db:
            self.assertEqual(db.get(models.ReferralReward, self.go.fixture.ids['buyer']).used_transaction_id, used)
        self.assertEqual(self.client.get('/api/referrals', headers=self.auth()).json()['reward_status'], 'USED')

    def test_rejected_payin_restores_reward_without_another_checkout_post(self):
        self.discounted_purchase(paid=False)
        self.assertEqual(self.client.get('/api/referrals', headers=self.auth()).json()['reward_status'], 'RESERVED')
        self.payin_status = 'REJECTED'
        self.go.notify({'payment_id': 'DP-1'})
        self.assertEqual(self.client.get('/api/referrals', headers=self.auth()).json()['reward_status'], 'AVAILABLE')
        self.assertEqual(len([c for c in self.go.calls if c[:2] == ('POST', '/v1/payments')]), 1)

    def test_duplicate_rejection_does_not_touch_a_reassigned_upgraded_ticket(self):
        import json
        from backend.go_payments import reconcile_payment
        from backend.payment_provider import PaymentUncertain
        self.discounted_purchase(paid=False)
        with SessionLocal() as db:
            reward = db.get(models.ReferralReward, self.go.fixture.ids['buyer'])
            reward.pending_upgrade = json.dumps(dict(buyer_discount_rate='.10', seller_commission_rate='0'))
            db.commit()
        self.payin_status = 'REJECTED'
        self.go.notify({'payment_id': 'DP-1'})
        reassigned = self.go.fixture.reserve(self.ticket_id, role='other')
        self.assertEqual(reassigned.status_code, 200, reassigned.text)
        self.go.notify({'payment_id': 'DP-1'})
        with SessionLocal() as db:
            ticket = db.get(models.Ticket, uuid.UUID(self.ticket_id))
            self.assertEqual(ticket.buyer_id, self.go.fixture.ids['other'])
            self.assertEqual(ticket.estado, models.TicketState.RESERVADA)
            self.assertEqual(db.get(models.Transaction, uuid.UUID(self.tx_id)).status, 'FAILED')
            self.payin_status = 'PAID'
            canonical = self.go.gateway.retrieve_payment('DP-1')
            with self.assertRaises(PaymentUncertain):
                reconcile_payment(db, uuid.UUID(self.tx_id), canonical)
            db.rollback()
            self.assertEqual(db.get(models.Ticket, uuid.UUID(self.ticket_id)).buyer_id, self.go.fixture.ids['other'])

    def test_rejected_checkout_creation_can_retry_same_ticket_and_quote(self):
        from backend.payment_provider import PaymentDeclined
        code = self.client.get('/api/referrals', headers=self.auth()).json()['referral_code']
        self.assertEqual(self.client.post('/api/auth/register', json={
            'email': 'go-retry-' + uuid.uuid4().hex + '@example.com',
            'password': fixtures.fixtures.PASSWORD, 'phone_number': '900000004',
            'referral_code': code}).status_code, 201)
        self.go.profile()
        ticket = self.go.fixture.upload(price='100').json()['id']
        quote = self.go.fixture.reserve(ticket).json()
        body = {'ticket_id': ticket, 'reservation_id': quote['reservation_id']}
        with patch.object(self.go.gateway, 'create_checkout', side_effect=PaymentDeclined()):
            response = self.client.post('/api/payments/checkout', headers=self.auth(), json=body)
            self.assertEqual(response.status_code, 402, response.text)
        response = self.client.post('/api/payments/checkout', headers=self.auth(), json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['amount_total'], 95)
        self.go.paid = True
        self.go.notify({'payment_id': 'DP-1'})
        self.assertEqual(self.client.get('/api/referrals', headers=self.auth()).json()['reward_status'], 'USED')

    def double_reward_purchase(self):
        self.go.profile()
        with SessionLocal() as db:
            db.add(models.ReferralReward(user_id=self.go.fixture.ids['buyer'], reward_kind='SELLER_REFERRAL',
                buyer_discount_rate=Decimal('.10'), seller_commission_rate=Decimal('0'), choice='BUY'))
            db.add(models.ReferralReward(user_id=self.go.fixture.ids['seller'], reward_kind='SELLER_REFERRAL',
                buyer_discount_rate=Decimal('.10'), seller_commission_rate=Decimal('0'), choice='SELL'))
            db.commit()
        ticket = self.go.fixture.upload(price='100')
        self.assertEqual(ticket.status_code, 200, ticket.text)
        quote = self.go.fixture.reserve(ticket.json()['id'])
        self.assertEqual(quote.status_code, 200, quote.text)
        response = self.client.post('/api/payments/checkout', headers=self.auth(), json={
            'ticket_id': ticket.json()['id'], 'reservation_id': quote.json()['reservation_id']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.go.orders['DP-1']['amount'], 90)
        self.go.paid = True
        self.go.notify({'payment_id': 'DP-1'})
        return self.client.get('/api/purchases', headers=self.auth()).json()[0]

    def test_ten_percent_buyer_and_zero_commission_seller_preserve_external_fees(self):
        review = self.double_reward_purchase()
        self.assertEqual(self.client.post('/api/purchases/' + review['purchase_id'] + '/confirm', headers=self.auth()).status_code, 200)
        with SessionLocal() as db:
            tx = db.query(models.Transaction).one()
            self.assertEqual((tx.amount_total, tx.commission_platform, tx.amount_seller),
                             (Decimal('90'), Decimal('0'), Decimal('100')))
            self.assertEqual((tx.payin_fee, tx.payout_fee, tx.seller_net_amount),
                             (Decimal('3.18'), Decimal('1'), Decimal('95.82')))
            process_go_settlements(db, self.go.gateway)
            self.assertEqual(db.query(models.FinancialOperation).one().amount, Decimal('95.82'))
            self.assertTrue(all(r.used_transaction_id == tx.id for r in db.query(models.ReferralReward).all()))

    def test_ten_percent_refund_returns_ninety_without_rearming_either_reward(self):
        review = self.double_reward_purchase()
        from backend.post_purchase import decide, lock_review
        with SessionLocal() as db:
            row, tx, ticket = lock_review(db, uuid.UUID(review['purchase_id']))
            decide(db, row, tx, ticket, 'VALID_CLAIM', actor=self.go.fixture.ids['admin'], reason='Evidencia de prueba concluyente.')
            db.commit()
            process_go_settlements(db, self.go.gateway)
            self.assertEqual(db.query(models.FinancialOperation).one().amount, Decimal('90'))
            self.assertEqual(self.go.refunds['REF-1']['amount'], 90)
            self.assertTrue(all(r.used_transaction_id == tx.id for r in db.query(models.ReferralReward).all()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
