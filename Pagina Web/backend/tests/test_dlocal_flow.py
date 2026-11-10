"""Go payin/payout integration using FastAPI, DB, signatures and a gateway boundary."""
import hashlib
import hmac
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import httpx
import test_api as fixtures
from backend import models
from backend.database import SessionLocal


class GoFlowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.APITests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.client = self.fixture.client
        self.env = patch.dict(os.environ, {
            'PAYMENT_PROVIDER': 'dlocal_go', 'PAYMENT_ENABLED': 'true', 'SETTLEMENT_ENABLED': 'true',
            'DLOCAL_GO_ENV': 'sandbox', 'DLOCAL_GO_API_KEY': 'offline_api_key',
            'DLOCAL_GO_SECRET_KEY': 'offline_secret_key', 'DLOCAL_GO_PUBLIC_URL': 'https://tickia.example',
            'DLOCAL_GO_PAYIN_PERCENT': '3.53', 'DLOCAL_GO_PAYIN_FIXED_PEN': '0',
            'DLOCAL_GO_PAYOUT_PERCENT': '0', 'DLOCAL_GO_PAYOUT_FIXED_PEN': '1',
            'DLOCAL_GO_FEES_TAX_PERCENT': '0', 'DLOCAL_GO_MIN_PAYOUT_PEN': '5',
            'DLOCAL_GO_PAYOUT_PURPOSE': 'ENTERTAINMENT',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        from backend.dlocal_go import DLocalGoProvider
        from backend.routers import dlocal
        self.paid = False
        self.profile_status = 'PENDING'
        self.payout_status = 'PENDING'
        self.calls = []
        self.orders = {}
        self.payouts = {}
        self.refunds = {}
        self.gateway = DLocalGoProvider(transport=httpx.MockTransport(self.http))
        self.patch = patch.object(dlocal, 'get_go_provider', lambda: self.gateway)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def beneficiary(self):
        return {'id': 14, 'status': self.profile_status, 'flow_type': 'B2C', 'country': 'PE',
                'first_name': 'Ana', 'last_name': 'Perez', 'document_type': 'DNI',
                'document': '87654321', 'email': 'seller@example.com', 'bank_accounts': [
                    {'id': 17, 'country': 'PE', 'currency': 'PEN', 'bank_code': '002',
                     'bank_account': '00200000000000000001', 'account_type': 'SAVINGS', 'preferred': True}]}

    def http(self, req):
        body = json.loads(req.content) if req.content else None
        self.calls.append((req.method, req.url.path, body, req.headers.get('Idempotency-Key')))
        path = req.url.path
        if path == '/v2/beneficiaries' and req.method == 'POST':
            return httpx.Response(201, json=self.beneficiary())
        if path == '/v2/beneficiaries' and req.method == 'GET':
            return httpx.Response(200, json=[self.beneficiary()])
        if path == '/v2/beneficiaries/14':
            return httpx.Response(200, json=self.beneficiary())
        if path.endswith('/validation-link'):
            return httpx.Response(200, json={'validation_link': 'https://verify.legaltalent.ai/s/test'})
        if path == '/v1/payments' and req.method == 'POST':
            self.orders['DP-1'] = body
            return httpx.Response(200, json={'id': 'DP-1', 'redirect_url': 'https://checkout-sbx.dlocalgo.com/validate/test'})
        if path == '/v1/payments/DP-1':
            return httpx.Response(200, json={**self.orders['DP-1'], 'id': 'DP-1',
                'status': 'PAID' if self.paid else 'PENDING',
                'approved_date': (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
                'balance_fee': 4.36, 'balance_amount': 119.09, 'balance_currency': 'PEN'})
        if path == '/v2/payouts':
            key = req.headers['Idempotency-Key']
            if key not in self.payouts:
                self.payouts[key] = {**body, 'payout_id': 'PO-' + str(len(self.payouts) + 1), 'amount': body['transfer_amount'],
                                    'currency_to_pay': 'PEN', 'status': self.payout_status}
            return httpx.Response(201, json=self.payouts[key])
        if path.startswith('/v1/payouts/PO-'):
            match = next(x for x in self.payouts.values() if x['payout_id'] == path.rsplit('/', 1)[1])
            return httpx.Response(200, json={**match, 'status': self.payout_status})
        if path == '/v1/refunds' and req.method == 'POST':
            self.refunds['REF-1'] = {**body, 'id': 'REF-1', 'currency': 'PEN', 'status': 'PENDING'}
            return httpx.Response(200, json=self.refunds['REF-1'])
        if path == '/v1/refunds/REF-1':
            return httpx.Response(200, json=self.refunds['REF-1'])
        if path == '/v1/refunds':
            return httpx.Response(200, json={'data': list(self.refunds.values()), 'totalPages': 1})
        return httpx.Response(404, json={'code': 404})

    def profile(self, ready=True):
        from backend.go_fees import fee_terms
        response = self.client.post('/api/payments/payout-profile', headers=self.fixture.auth('seller'), json={
            'first_name': 'Ana', 'last_name': 'Perez', 'document_type': 'DNI', 'document': '87654321',
            'bank_code': '002', 'account_number': '00200000000000000001',
            'account_type': 'SAVINGS', 'accept_fees': True, 'fee_terms_hash': fee_terms()['hash']})
        self.assertEqual(response.status_code, 200, response.text)
        if ready:
            self.profile_status = 'VERIFIED'
            response = self.client.get('/api/payments/payout-profile', headers=self.fixture.auth('seller'))
            self.assertTrue(response.json()['can_sell'], response.text)
        return response

    def checkout(self, paid=True):
        self.profile()
        ticket = self.fixture.upload()
        self.assertEqual(ticket.status_code, 200, ticket.text)
        self.ticket_id = ticket.json()['id']
        self.assertEqual(self.fixture.reserve(self.ticket_id).status_code, 200)
        response = self.client.post('/api/payments/checkout', headers=self.fixture.auth(), json={'ticket_id': self.ticket_id})
        self.assertEqual(response.status_code, 200, response.text)
        self.tx_id = response.json()['transaction_id']
        if paid:
            self.paid = True
            self.notify({'payment_id': 'DP-1'})
        return response

    def notify(self, payload):
        raw = json.dumps(payload, separators=(',', ':')).encode()
        digest = hmac.new(b'offline_secret_key', b'offline_api_key' + raw, hashlib.sha256).hexdigest()
        response = self.client.post('/api/payments/webhooks/dlocal-go', content=raw,
            headers={'Content-Type': 'application/json', 'Authorization': 'V2-HMAC-SHA256, Signature: ' + digest})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_profile_requires_real_provider_verification(self):
        response = self.profile(False)
        self.assertFalse(response.json()['can_sell'])
        self.assertNotIn('00200000000000000001', response.text)
        self.assertEqual(response.json()['bank_account_last4'], '0001')

    def test_payin_is_not_completed_by_checkout_creation(self):
        self.checkout(paid=False)
        self.assertEqual(self.client.get('/api/purchases', headers=self.fixture.auth()).json(), [])
        self.paid = True
        self.notify({'payment_id': 'DP-1'})
        self.notify({'payment_id': 'DP-1'})
        self.assertEqual(len(self.client.get('/api/purchases', headers=self.fixture.auth()).json()), 1)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Transaction).one().status, 'SUCCEEDED')

    def test_confirmation_creates_one_payout_and_rewards_only_when_completed(self):
        self.checkout()
        row = self.client.get('/api/purchases', headers=self.fixture.auth()).json()[0]
        response = self.client.post('/api/purchases/' + row['purchase_id'] + '/confirm', headers=self.fixture.auth())
        self.assertEqual(response.status_code, 200)
        from backend.go_settlements import process_go_settlements
        with SessionLocal() as db:
            process_go_settlements(db, self.gateway)
            process_go_settlements(db, self.gateway)
            self.assertEqual(db.get(models.User, self.fixture.ids['seller']).rating, Decimal('4'))
        self.assertEqual(len([c for c in self.calls if c[0:2] == ('POST', '/v2/payouts')]), 1)
        self.payout_status = 'COMPLETED'
        self.notify({'payout_id': 'PO-1'})
        self.notify({'payout_id': 'PO-1'})
        with SessionLocal() as db:
            self.assertEqual(db.query(models.PurchaseReview).one().settlement_state, 'SUCCEEDED')
            self.assertEqual(db.get(models.User, self.fixture.ids['seller']).rating, Decimal('4.25'))
            self.assertEqual(db.get(models.User, self.fixture.ids['buyer']).rating, Decimal('4.25'))

    def test_unsigned_notification_cannot_release_ticket(self):
        self.checkout(paid=False)
        response = self.client.post('/api/payments/webhooks/dlocal-go', json={'payment_id': 'DP-1'})
        self.assertEqual(response.status_code, 401)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Transaction).one().status, 'PROCESSING')

    def test_other_buyer_cannot_see_checkout_result(self):
        self.checkout(False)
        self.assertEqual(self.client.get('/api/payments/transactions/' + self.tx_id,
                                        headers=self.fixture.auth('other')).status_code, 404)

    def run_worker(self):
        from backend.go_settlements import process_go_settlements
        with SessionLocal() as db:
            process_go_settlements(db, self.gateway)

    def review(self):
        return self.client.get('/api/purchases', headers=self.fixture.auth()).json()[0]

    def confirm(self):
        return self.client.post('/api/purchases/' + self.review()['purchase_id'] + '/confirm', headers=self.fixture.auth())

    def test_resume_checkout_does_not_create_second_payment(self):
        self.checkout(False)
        response = self.client.post('/api/payments/checkout', headers=self.fixture.auth(), json={'ticket_id': self.ticket_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['transaction_id'], self.tx_id)
        self.assertEqual(len([c for c in self.calls if c[:2] == ('POST', '/v1/payments')]), 1)

    def test_wrong_amount_notification_is_not_fulfilled(self):
        self.checkout(False)
        self.paid = True
        self.orders['DP-1']['amount'] = 0.01
        raw = b'{"payment_id":"DP-1"}'
        digest = hmac.new(b'offline_secret_key', b'offline_api_key' + raw, hashlib.sha256).hexdigest()
        response = self.client.post('/api/payments/webhooks/dlocal-go', content=raw,
            headers={'Authorization': 'V2-HMAC-SHA256, Signature: ' + digest})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get('/api/purchases', headers=self.fixture.auth()).json(), [])

    def test_fee_change_requires_seller_reacceptance(self):
        self.profile()
        with patch.dict(os.environ, {'DLOCAL_GO_PAYOUT_FIXED_PEN': '2'}):
            response = self.client.get('/api/payments/payout-profile', headers=self.fixture.auth('seller'))
            self.assertFalse(response.json()['can_sell'])
            self.assertFalse(response.json()['fee_terms_accepted'])
            self.assertEqual(self.fixture.upload().status_code, 409)

    def test_dispute_prevents_payout_and_valid_claim_refunds_once(self):
        from backend.routers import purchases
        self.checkout()
        review = self.review()
        with patch.object(purchases, 'upload_encrypted_qr', self.fixture.store):
            response = self.client.post('/api/purchases/' + review['purchase_id'] + '/dispute', headers=self.fixture.auth(),
                data={'description': 'La entrada no fue aceptada en el acceso.'},
                files={'file': ('evidence.png', fixtures.image_bytes('evidence'), 'image/png')})
        self.assertEqual(response.status_code, 200, response.text)
        self.run_worker()
        self.assertFalse(self.payouts)
        response = self.client.post('/api/purchases/admin/' + review['purchase_id'] + '/resolve',
            headers=self.fixture.auth('admin'), json={'valid': True, 'reason': 'Evidencia concluyente del rechazo.'})
        self.assertEqual(response.status_code, 200)
        self.run_worker()
        self.run_worker()
        self.assertEqual(len([c for c in self.calls if c[:2] == ('POST', '/v1/refunds')]), 1)
        self.refunds['REF-1']['status'] = 'SUCCESS'
        self.notify({'refund_id': 'REF-1'})
        self.notify({'refund_id': 'REF-1'})
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Transaction).one().status, 'REFUNDED')
            self.assertEqual(db.get(models.User, self.fixture.ids['buyer']).rating, Decimal('4.25'))
            self.assertEqual(db.get(models.User, self.fixture.ids['seller']).warning_count, 1)

    def test_silence_only_rewards_seller(self):
        from backend.post_purchase import close_expired_reviews
        self.checkout()
        with SessionLocal() as db:
            db.query(models.PurchaseReview).one().closes_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            close_expired_reviews(db)
        self.run_worker()
        self.payout_status = 'DELIVERED'
        self.notify({'payout_id': 'PO-1'})
        with SessionLocal() as db:
            self.assertEqual(db.get(models.User, self.fixture.ids['buyer']).rating, Decimal('4'))
            self.assertEqual(db.get(models.User, self.fixture.ids['seller']).rating, Decimal('4.25'))

    def test_timeout_after_payout_acceptance_recovers_same_idempotency_key(self):
        self.checkout()
        self.confirm()
        def network(req):
            response = self.http(req)
            if req.method == 'POST' and req.url.path == '/v2/payouts':
                raise httpx.ReadTimeout('Accepted but HTTP response lost', request=req)
            return response
        from backend.dlocal_go import DLocalGoProvider
        from backend.go_settlements import process_go_settlements
        failing = DLocalGoProvider(transport=httpx.MockTransport(network))
        with SessionLocal() as db:
            process_go_settlements(db, failing)
            operation = db.query(models.FinancialOperation).one()
            self.assertEqual(operation.status, 'UNKNOWN')
            operation.next_check_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            process_go_settlements(db, self.gateway)
        sent = [c for c in self.calls if c[:2] == ('POST', '/v2/payouts')]
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0][2:], sent[1][2:])
        self.assertEqual(len(self.payouts), 1)

    def test_seller_receives_exact_net_and_all_costs_are_deducted_once(self):
        self.checkout()
        self.confirm()
        self.run_worker()
        sent = next(c[2] for c in self.calls if c[:2] == ('POST', '/v2/payouts'))
        self.assertEqual(sent['transfer_amount'], 105.74)  # 123.45 - 12.35 - 4.36 - 1.00
        with SessionLocal() as db:
            tx = db.query(models.Transaction).one()
            self.assertEqual(tx.provider_fee, Decimal('5.36'))
            self.assertEqual(tx.amount_total, Decimal('123.45'))

    def test_available_balance_deadline_blocks_early_payout(self):
        self.checkout()
        self.confirm()
        with SessionLocal() as db:
            db.query(models.Transaction).one().available_after = datetime.now(timezone.utc) + timedelta(days=7)
            db.commit()
        self.run_worker()
        self.assertFalse(self.payouts)
        self.assertEqual(self.review()['settlement_state'], 'BLOCKED')

    def test_provider_kyc_revocation_blocks_payout(self):
        self.checkout()
        self.confirm()
        self.profile_status = 'BLOCKED'
        self.run_worker()
        self.assertFalse(self.payouts)
        self.assertEqual(self.review()['settlement_state'], 'BLOCKED')

    def test_both_payout_and_payin_have_to_be_enabled_before_collecting(self):
        self.profile()
        ticket = self.fixture.upload().json()['id']
        self.fixture.reserve(ticket)
        with patch.dict(os.environ, {'SETTLEMENT_ENABLED': 'false'}):
            response = self.client.post('/api/payments/checkout', headers=self.fixture.auth(), json={'ticket_id': ticket})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.orders)

    def test_missing_fee_is_reconciled_after_the_payment_was_already_delivered(self):
        from backend.go_payments import reconcile_go_payments
        self.checkout()
        with SessionLocal() as db:
            tx = db.query(models.Transaction).one()
            tx.provider_fee = tx.seller_net_amount = None
            db.commit()
            reconcile_go_payments(db, self.gateway)
            self.assertEqual(db.query(models.Transaction).one().seller_net_amount, Decimal('105.74'))

    def test_event_started_before_checkout_does_not_charge(self):
        self.profile()
        ticket = self.fixture.upload().json()['id']
        self.fixture.reserve(ticket)
        with SessionLocal() as db:
            db.get(models.Ticket, uuid.UUID(ticket)).event_date = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        response = self.client.post('/api/payments/checkout', headers=self.fixture.auth(), json={'ticket_id': ticket})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.orders)

    def test_reservation_expiring_during_kyc_lookup_does_not_charge(self):
        from backend.routers import dlocal
        from backend.go_profiles import refresh_profile
        self.profile()
        ticket = self.fixture.upload().json()['id']
        self.fixture.reserve(ticket)
        def expire(db, profile, provider):
            result = refresh_profile(db, profile, provider)
            db.get(models.Ticket, uuid.UUID(ticket)).reserved_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            return result
        with patch.object(dlocal, 'refresh_profile', expire):
            response = self.client.post('/api/payments/checkout', headers=self.fixture.auth(), json={'ticket_id': ticket})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.orders)

    def test_unsupported_purpose_cannot_enable_collection(self):
        from backend.go_fees import fee_terms
        from backend.payment_provider import PaymentUnavailable
        with patch.dict(os.environ, {'DLOCAL_GO_PAYOUT_PURPOSE': 'SERVICES'}):
            with self.assertRaises(PaymentUnavailable):
                fee_terms()

    def test_confirmed_payout_rejection_requires_admin_retry_with_new_intent(self):
        self.checkout()
        self.confirm()
        self.payout_status = 'REJECTED'
        self.run_worker()
        self.run_worker()
        self.assertEqual(len(self.payouts), 1)
        items = self.client.get('/api/payments/admin/operations', headers=self.fixture.auth('admin'))
        self.assertEqual(items.status_code, 200, items.text)
        operation = items.json()[0]
        self.assertTrue(operation['can_retry'])
        path = '/api/payments/admin/operations/' + operation['operation_id'] + '/retry'
        body = {'reason': 'Se revisaron los datos y el saldo disponible.'}
        self.assertEqual(self.client.post(path, headers=self.fixture.auth(), json=body).status_code, 403)
        self.payout_status = 'PENDING'
        self.assertEqual(self.client.post(path, headers=self.fixture.auth('admin'), json=body).status_code, 409)
        self.payout_status = 'REJECTED'
        self.assertEqual(self.client.post(path, headers=self.fixture.auth('admin'), json=body).status_code, 200)
        self.assertEqual(self.client.post(path, headers=self.fixture.auth('admin'), json=body).status_code, 409)
        self.payout_status = 'COMPLETED'
        self.run_worker()
        self.assertEqual(len(self.payouts), 2)
        self.assertEqual(self.review()['settlement_state'], 'SUCCEEDED')

    def test_go_payin_rejected_before_creation_is_not_stuck_unknown(self):
        from backend.routers import dlocal
        from backend.payment_provider import PaymentDeclined
        self.profile()
        ticket = self.fixture.upload().json()['id']
        self.fixture.reserve(ticket)
        with patch.object(self.gateway, 'create_checkout', side_effect=PaymentDeclined('invalid', http_status=422)):
            response = self.client.post('/api/payments/checkout', headers=self.fixture.auth(), json={'ticket_id': ticket})
        self.assertEqual(response.status_code, 402)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Transaction).one().status, 'FAILED')

    def test_refund_timeout_recovers_by_lookup_without_second_refund(self):
        from backend.routers import purchases
        from backend.dlocal_go import DLocalGoProvider
        from backend.go_settlements import process_go_settlements
        self.checkout()
        review = self.review()
        with patch.object(purchases, 'upload_encrypted_qr', self.fixture.store):
            response = self.client.post('/api/purchases/' + review['purchase_id'] + '/dispute',
                headers=self.fixture.auth(), data={'description': 'La entrada no permite ingresar.'},
                files={'file': ('evidence.png', fixtures.image_bytes('refund-timeout'), 'image/png')})
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/api/purchases/admin/' + review['purchase_id'] + '/resolve',
            headers=self.fixture.auth('admin'), json={'valid': True, 'reason': 'Se verificó la evidencia del acceso rechazado.'})
        self.assertEqual(response.status_code, 200)
        def network(req):
            response = self.http(req)
            if req.method == 'POST' and req.url.path == '/v1/refunds':
                raise httpx.ReadTimeout('Refund accepted, response lost', request=req)
            return response
        failing = DLocalGoProvider(transport=httpx.MockTransport(network))
        with SessionLocal() as db:
            process_go_settlements(db, failing)
            operation = db.query(models.FinancialOperation).one()
            self.assertEqual(operation.status, 'UNKNOWN')
            self.assertIsNone(operation.provider_id)
            operation.next_check_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            self.refunds['REF-1']['status'] = 'SUCCESS'
            process_go_settlements(db, self.gateway)
        self.assertEqual(len([c for c in self.calls if c[:2] == ('POST', '/v1/refunds')]), 1)
        self.assertEqual(self.review()['settlement_state'], 'SUCCEEDED')

    def test_uncertain_checkout_returns_trackable_order_without_second_post(self):
        from backend.payment_provider import PaymentUncertain
        self.profile()
        ticket = self.fixture.upload().json()['id']
        self.fixture.reserve(ticket)
        with patch.object(self.gateway, 'create_checkout', side_effect=PaymentUncertain('Response lost')) as create:
            response = self.client.post('/api/payments/checkout', headers=self.fixture.auth(), json={'ticket_id': ticket})
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.json()['status'], 'UNKNOWN')
            transaction = response.json()['transaction_id']
            again = self.client.post('/api/payments/checkout', headers=self.fixture.auth(), json={'ticket_id': ticket})
            self.assertEqual(again.json()['transaction_id'], transaction)
            self.assertEqual(create.call_count, 1)
        result = self.client.get('/api/payments/transactions/' + transaction, headers=self.fixture.auth())
        self.assertEqual(result.json()['status'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
