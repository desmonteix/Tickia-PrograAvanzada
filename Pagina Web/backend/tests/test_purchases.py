import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import test_api as fixtures
from backend import models
from backend.database import SessionLocal


class PurchaseFlowTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        fixtures.engine.dispose()

    def setUp(self):
        self.fixture = fixtures.APITests(methodName='runTest')
        self.fixture.setUp()
        self.client = self.fixture.client
        self.ticket_id = self.fixture.purchased_ticket()
        from backend.routers import purchases
        self.evidence_patches = [patch.object(purchases, 'upload_encrypted_qr', self.fixture.store),
            patch.object(purchases, 'download_encrypted_qr', lambda key: self.fixture.files[key]),
            patch.object(purchases, 'delete_qr_file', lambda key: self.fixture.files.pop(key, None))]
        for item in self.evidence_patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.evidence_patches):
            item.stop()
        self.fixture.tearDown()

    def review(self):
        response = self.client.get('/api/purchases', headers=self.fixture.auth())
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()[0]

    def confirm(self):
        return self.client.post('/api/purchases/' + self.review()['purchase_id'] + '/confirm', headers=self.fixture.auth())

    def dispute(self):
        return self.client.post('/api/purchases/' + self.review()['purchase_id'] + '/dispute', headers=self.fixture.auth(),
            data={'description': 'No aceptaron la entrada en el acceso.'},
            files={'file': ('evidencia.png', fixtures.image_bytes('evidence'), 'image/png')})

    def execute(self, refund=False):
        from backend.post_purchase import process_settlements
        class Provider:
            def release_funds_to_seller(self, charge_id, amount_cents, operation_id, seller_id):
                return {'operation_id': operation_id, 'reference': 'payout_' + operation_id, 'amount_cents': amount_cents, 'status': 'SUCCEEDED'}
            def refund_buyer(self, charge_id, amount_cents, operation_id):
                return {'operation_id': operation_id, 'reference': 'refund_' + operation_id, 'amount_cents': amount_cents, 'status': 'SUCCEEDED'}
        with SessionLocal() as db, patch.dict('os.environ', {'SETTLEMENT_ENABLED': 'true'}):
            tx = db.query(models.Transaction).one()
            tx.provider_fee = Decimal('0.00')
            tx.seller_net_amount = tx.amount_seller
            db.commit()
            process_settlements(db, Provider())

    def ratings(self):
        with SessionLocal() as db:
            return [db.get(models.User, self.fixture.ids[role]).rating for role in ('buyer', 'seller')]

    def test_confirmation_available_on_delivery_and_applied_once_after_payout(self):
        self.assertTrue(self.review()['can_confirm'])
        self.assertEqual(self.confirm().status_code, 200)
        self.assertEqual(self.confirm().status_code, 409)
        self.assertEqual(self.ratings(), [Decimal('4'), Decimal('4')])
        self.execute()
        self.execute()
        self.assertEqual(self.ratings(), [Decimal('4.25'), Decimal('4.25')])

    def test_silence_only_rewards_seller(self):
        from backend.post_purchase import close_expired_reviews
        with SessionLocal() as db:
            row = db.query(models.PurchaseReview).one()
            row.closes_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            close_expired_reviews(db)
        self.execute()
        self.assertEqual(self.ratings(), [Decimal('4'), Decimal('4.25')])

    def test_valid_claim_freezes_funds_then_refunds_and_warns_seller(self):
        from backend.post_purchase import close_expired_reviews
        self.assertEqual(self.dispute().status_code, 200)
        purchase = self.review()
        with SessionLocal() as db:
            row = db.query(models.PurchaseReview).one()
            row.closes_at = datetime.now(timezone.utc) - timedelta(days=2)
            db.commit()
            close_expired_reviews(db)
            self.assertEqual(row.review_state, 'DISPUTED')
            self.assertEqual(row.settlement_state, 'NONE')
        result = self.client.post('/api/purchases/admin/' + purchase['purchase_id'] + '/resolve', headers=self.fixture.auth('admin'), json={'valid': True, 'reason': 'La evidencia del acceso acredita el rechazo.'})
        self.assertEqual(result.status_code, 200, result.text)
        self.execute(refund=True)
        self.assertEqual(self.ratings(), [Decimal('4.25'), Decimal('4')])
        with SessionLocal() as db:
            self.assertEqual(db.get(models.User, self.fixture.ids['seller']).warning_count, 1)
            self.assertEqual(db.query(models.Transaction).one().status, 'REFUNDED')

    def test_rejected_claim_pays_seller_and_deducts_buyer(self):
        self.assertEqual(self.dispute().status_code, 200)
        result = self.client.post('/api/purchases/admin/' + self.review()['purchase_id'] + '/resolve', headers=self.fixture.auth('admin'), json={'valid': False, 'reason': 'El material no acredita un problema con la entrada.'})
        self.assertEqual(result.status_code, 200, result.text)
        self.execute()
        self.assertEqual(self.ratings(), [Decimal('3.75'), Decimal('4.25')])

    def test_evidence_required_and_private(self):
        purchase_id = self.review()['purchase_id']
        self.assertEqual(self.client.post('/api/purchases/' + purchase_id + '/dispute', headers=self.fixture.auth(), data={'description': 'Fallo en el acceso.'}).status_code, 422)
        self.assertEqual(self.dispute().status_code, 200)
        cases = self.client.get('/api/purchases/admin/cases', headers=self.fixture.auth('admin')).json()
        evidence_id = cases[0]['evidence'][0]['id']
        self.assertEqual(self.client.get('/api/purchases/evidence/' + evidence_id, headers=self.fixture.auth('seller')).status_code, 403)
        self.assertEqual(self.client.get('/api/purchases/evidence/' + evidence_id, headers=self.fixture.auth('admin')).status_code, 200)

    def test_closed_deadline_rejects_dispute_and_missing_end_never_auto_pays(self):
        from backend.post_purchase import close_expired_reviews
        with SessionLocal() as db:
            row = db.query(models.PurchaseReview).one()
            row.closes_at = None
            db.commit()
            close_expired_reviews(db)
            self.assertEqual(row.settlement_state, 'NONE')
            row.closes_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.dispute().status_code, 409)

    def test_rating_is_capped_at_five(self):
        self.assertEqual(self.confirm().status_code, 200)
        with SessionLocal() as db:
            for role in ('buyer', 'seller'):
                db.get(models.User, self.fixture.ids[role]).rating = Decimal('5')
            db.commit()
        self.execute()
        self.assertEqual(self.ratings(), [Decimal('5'), Decimal('5')])

    def test_uncertain_payout_is_not_repeated_or_rewarded(self):
        from backend.post_purchase import process_settlements
        from backend.payment_provider import PaymentUncertain
        self.assertEqual(self.confirm().status_code, 200)
        calls = []
        class Provider:
            def release_funds_to_seller(self, *args):
                calls.append(args)
                raise PaymentUncertain('offline')
        with SessionLocal() as db, patch.dict('os.environ', {'SETTLEMENT_ENABLED': 'true'}):
            tx = db.query(models.Transaction).one()
            tx.provider_fee, tx.seller_net_amount = Decimal('0'), tx.amount_seller
            db.commit()
            process_settlements(db, Provider())
            process_settlements(db, Provider())
            self.assertEqual(db.query(models.PurchaseReview).one().settlement_state, 'UNKNOWN')
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.ratings(), [Decimal('4'), Decimal('4')])

    def test_catalog_seller_rating_has_priority_over_boost(self):
        with SessionLocal() as db:
            high = models.User(email='high@example.com', hashed_password='fixture', rating=Decimal('5'))
            db.add(high); db.flush()
            source = db.get(models.Ticket, uuid.UUID(self.ticket_id))
            for seller, rating_name in ((high.id, 'Mayor rating'), (source.seller_id, 'Menor rating')):
                db.add(models.Ticket(seller_id=seller, event_name=rating_name, event_date=source.event_date,
                    event_end_date=source.event_end_date, zone='General', ticketing_company='teleticket',
                    ticket_type='no_nominada', price=100, qr_hash_sha256=uuid.uuid4().hex,
                    qr_image_url_encrypted='fixture.enc', boosted_until=(datetime.now(timezone.utc) + timedelta(days=1)) if seller == source.seller_id else None))
            db.commit()
        rows = self.client.get('/api/tickets').json()
        self.assertEqual([row['event_name'] for row in rows], ['Mayor rating', 'Menor rating'])
        self.assertEqual(rows[0]['seller_rating'], 5)

    def test_registration_starts_at_four_and_nomination_is_not_delivery(self):
        response = self.client.post('/api/auth/register', json={'email':'rating@example.com','password':'StrongPassword123!','phone_number':'999999999'})
        self.assertEqual(response.json()['rating'], 4)
        from backend.post_purchase import close_expired_reviews
        with SessionLocal() as db:
            row = db.query(models.PurchaseReview).one()
            ticket = db.get(models.Ticket, row.ticket_id)
            ticket.estado = models.TicketState.PENDIENTE_RENOMINACION
            row.delivered_at = None
            row.closes_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            close_expired_reviews(db)
            self.assertEqual(row.settlement_state, 'NONE')

    def test_refund_protocol_requires_provider_confirmation(self):
        import httpx
        from backend.payment_provider import CulqiProvider, PaymentUncertain
        with patch.dict('os.environ', {'SETTLEMENT_ENABLED':'true','CULQI_PRIVATE_KEY':'sk_test_offline_refund_key'}):
            complete = {'object':'refund','id':'ref_test_123456','charge_id':'chr_test_fixture','amount':1000,'status':'Completa'}
            with patch('httpx.post', return_value=httpx.Response(201,json=complete)) as request:
                receipt = CulqiProvider().refund_buyer('chr_test_fixture',1000,'operation')
                self.assertEqual(receipt['status'], 'SUCCEEDED')
                self.assertEqual(request.call_args.kwargs['json']['amount'],1000)
            with patch('httpx.post', return_value=httpx.Response(201,json={**complete,'status':'Pendiente'})):
                with self.assertRaises(PaymentUncertain):
                    CulqiProvider().refund_buyer('chr_test_fixture',1000,'operation')

    def test_uncertain_refund_is_reconciled_without_sending_it_twice(self):
        from backend.post_purchase import process_settlements, reconcile_refunds
        from backend.payment_provider import PaymentUncertain
        self.assertEqual(self.dispute().status_code, 200)
        self.client.post('/api/purchases/admin/' + self.review()['purchase_id'] + '/resolve', headers=self.fixture.auth('admin'), json={'valid':True,'reason':'La evidencia acredita el rechazo en el acceso.'})
        calls=[]
        class Provider:
            def refund_buyer(self,*args):
                calls.append(args)
                raise PaymentUncertain('offline')
            def refund_is_complete(self,charge_id,amount):
                return True
        with SessionLocal() as db, patch.dict('os.environ', {'SETTLEMENT_ENABLED':'true'}):
            provider=Provider()
            process_settlements(db,provider)
            reconcile_refunds(db,provider)
            reconcile_refunds(db,provider)
            self.assertEqual(db.query(models.PurchaseReview).one().settlement_state,'SUCCEEDED')
        self.assertEqual(len(calls),1)
        self.assertEqual(self.ratings(),[Decimal('4.25'),Decimal('4')])

    def test_other_buyer_cannot_confirm_or_resolve(self):
        purchase_id = self.review()['purchase_id']
        self.assertEqual(self.client.post('/api/purchases/' + purchase_id + '/confirm', headers=self.fixture.auth('other')).status_code, 404)
        self.assertEqual(self.client.get('/api/purchases/admin/cases', headers=self.fixture.auth()).status_code, 403)

    def test_legacy_without_end_allows_explicit_response_but_no_automatic_payout(self):
        from backend.post_purchase import close_expired_reviews
        with SessionLocal() as db:
            row = db.query(models.PurchaseReview).one()
            row.closes_at = None
            db.commit()
            close_expired_reviews(db)
            self.assertEqual(row.settlement_state, 'NONE')
        self.assertTrue(self.review()['can_report'])
        self.assertEqual(self.confirm().status_code, 200)

    def test_extreme_event_end_is_rejected_before_publication_or_charge(self):
        response = self.fixture.upload(event_end_date='9999-12-31T23:59:59-05:00')
        self.assertEqual(response.status_code, 422)
        response = self.fixture.upload(data=fixtures.image_bytes('extreme-date'))
        ticket_id = response.json()['id']
        self.assertEqual(self.fixture.reserve(ticket_id).status_code, 200)
        with SessionLocal() as db:
            db.get(models.Ticket, uuid.UUID(ticket_id)).event_end_date = datetime.max.replace(tzinfo=timezone.utc)
            db.commit()
        calls = self.fixture.provider.calls
        self.assertEqual(self.fixture.charge(ticket_id).status_code, 422)
        self.assertEqual(self.fixture.provider.calls, calls)

    def test_rating_never_goes_below_zero(self):
        self.assertEqual(self.dispute().status_code, 200)
        self.client.post('/api/purchases/admin/' + self.review()['purchase_id'] + '/resolve', headers=self.fixture.auth('admin'), json={'valid':False,'reason':'La evidencia no acredita el rechazo en el acceso.'})
        with SessionLocal() as db:
            db.get(models.User, self.fixture.ids['buyer']).rating = Decimal('0')
            db.commit()
        self.execute()
        self.assertEqual(self.ratings(), [Decimal('0'), Decimal('4.25')])

    def test_reconciliation_wins_over_late_transport_error(self):
        from backend.post_purchase import process_settlements, reconcile_refunds
        from backend.payment_provider import PaymentUncertain
        self.assertEqual(self.dispute().status_code, 200)
        self.client.post('/api/purchases/admin/' + self.review()['purchase_id'] + '/resolve', headers=self.fixture.auth('admin'), json={'valid':True,'reason':'La evidencia acredita el rechazo en el acceso.'})
        class Provider:
            def refund_buyer(self, *args):
                with SessionLocal() as other:
                    reconcile_refunds(other, self)
                raise PaymentUncertain('Late network failure after reconciliation')
            def refund_is_complete(self, charge_id, amount):
                return True
        with SessionLocal() as db, patch.dict('os.environ', {'SETTLEMENT_ENABLED':'true'}):
            process_settlements(db, Provider())
            self.assertEqual(db.query(models.PurchaseReview).one().settlement_state, 'SUCCEEDED')
        self.assertEqual(self.ratings(), [Decimal('4.25'), Decimal('4')])

    def test_evidence_failure_keeps_review_open_and_allows_retry(self):
        from backend.routers import purchases
        with patch.object(purchases, 'upload_encrypted_qr', side_effect=RuntimeError('offline')):
            self.assertEqual(self.dispute().status_code, 503)
        self.assertEqual(self.review()['review_state'], 'HELD')
        self.assertEqual(self.dispute().status_code, 200)

    def test_admin_cannot_reverse_a_final_decision(self):
        self.assertEqual(self.dispute().status_code, 200)
        url = '/api/purchases/admin/' + self.review()['purchase_id'] + '/resolve'
        body = {'valid':True, 'reason':'La evidencia acredita el rechazo en el acceso.'}
        self.assertEqual(self.client.post(url, headers=self.fixture.auth('admin'), json=body).status_code, 200)
        self.assertEqual(self.client.post(url, headers=self.fixture.auth('admin'), json={**body,'valid':False}).status_code, 409)
        self.assertEqual(self.review()['decision'], 'VALID_CLAIM')

    def test_review_deadline_is_exactly_24_hours_after_end(self):
        with SessionLocal() as db:
            row = db.query(models.PurchaseReview).one()
            end = db.get(models.Ticket, row.ticket_id).event_end_date
            self.assertEqual(row.closes_at - end, timedelta(hours=24))

    def test_late_charge_error_cannot_overwrite_verified_refund(self):
        from backend.routers.payments import settle_verified_charge
        from backend.post_purchase import decide, finish_settlement
        from backend.payment_provider import PaymentUncertain
        response = self.fixture.upload(data=fixtures.image_bytes('late-charge-refund'))
        ticket_id = response.json()['id']
        self.assertEqual(self.fixture.reserve(ticket_id).status_code, 200)
        create_charge = self.fixture.provider.create_charge
        def charge_with_late_error(*args):
            charge = create_charge(*args)
            # The webhook and an independently confirmed refund finish before
            # the original checkout request observes its transport error.
            with SessionLocal() as db:
                ticket = db.get(models.Ticket, uuid.UUID(ticket_id))
                tx = db.query(models.Transaction).filter_by(ticket_id=ticket.id).one()
                settle_verified_charge(db, tx, ticket, charge)
                db.flush()
                row = db.query(models.PurchaseReview).filter_by(ticket_id=ticket.id).one()
                decide(db, row, tx, ticket, 'VALID_CLAIM')
                row.settlement_state = 'PROCESSING'
                finish_settlement(db, row, tx, ticket, 'ref_test_late_charge')
            raise PaymentUncertain('Original request timed out after webhook and refund')
        with patch.object(self.fixture.provider, 'create_charge', charge_with_late_error):
            self.assertEqual(self.fixture.charge(ticket_id).status_code, 502)
        with SessionLocal() as db:
            tx = db.query(models.Transaction).filter_by(ticket_id=uuid.UUID(ticket_id)).one()
            self.assertEqual(tx.status, 'REFUNDED')
