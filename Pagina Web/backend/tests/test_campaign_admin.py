"""Administrative controls and seller referral benefits use the actual API/ledger."""
import uuid
from decimal import Decimal
from unittest.mock import patch
import unittest

import test_api as fixtures
from backend import models
from backend.database import SessionLocal


class CampaignAdminTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.APITests(methodName='runTest')
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.client = self.f.client
        window = patch('backend.promotions.in_launch_window', return_value=True)
        window.start()
        self.addCleanup(window.stop)

    def invite_seller(self):
        code = self.client.get('/api/referrals', headers=self.f.auth()).json()['referral_code']
        with SessionLocal() as db:
            db.add(models.Referral(referred_user_id=self.f.ids['seller'], referrer_id=self.f.ids['buyer']))
            db.commit()
        return code

    def ticket(self):
        response = self.f.upload(price='100', data=fixtures.image_bytes('https://teleticket.com.pe/ticket/' + uuid.uuid4().hex))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def reward(self, role='buyer'):
        response = self.client.get('/api/referrals', headers=self.f.auth(role))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_campaigns_are_admin_only_and_archive_preserves_earned_reward(self):
        self.assertEqual(self.client.get('/api/admin/campaigns', headers=self.f.auth()).status_code, 403)
        campaigns = self.client.get('/api/admin/campaigns', headers=self.f.auth('admin'))
        self.assertEqual(campaigns.status_code, 200, campaigns.text)
        campaign = campaigns.json()[0]
        self.invite_seller()
        self.ticket()
        response = self.client.request('DELETE', '/api/admin/campaigns/' + campaign['id'],
            headers=self.f.auth('admin'), json={'reason': 'Finalizar campaña de prueba'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.client.get('/api/promotions').json()['active'])
        self.assertEqual(self.reward()['reward_status'], 'AVAILABLE')
        self.assertEqual(self.ticket()['commission_rate'], .10)

    def test_admin_patch_preflight_allows_the_configured_frontend_origin(self):
        response = self.client.options('/api/admin/settings', headers={
            'Origin': 'http://127.0.0.1:5173',
            'Access-Control-Request-Method': 'PATCH',
            'Access-Control-Request-Headers': 'content-type'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('PATCH', response.headers['access-control-allow-methods'])
        self.assertEqual(response.headers['access-control-allow-origin'], 'http://127.0.0.1:5173')
        rejected = self.client.options('/api/admin/settings', headers={
            'Origin': 'https://untrusted.invalid', 'Access-Control-Request-Method': 'PATCH'})
        self.assertEqual(rejected.status_code, 400)
        self.assertNotIn('access-control-allow-origin', rejected.headers)

    def test_first_valid_seller_publication_grants_choice_once(self):
        self.invite_seller()
        self.assertEqual(self.reward()['reward_status'], 'NOT_EARNED')
        self.assertEqual(self.f.upload(data=b'invalid').status_code, 400)
        self.assertEqual(self.reward()['reward_status'], 'NOT_EARNED')
        self.ticket()
        reward = self.reward()
        self.assertEqual((reward['discount_rate'], reward['seller_commission_rate'], reward['choice']), (.10, 0, None))
        self.assertEqual(reward['qualifying_seller_count'], 1)
        self.ticket()
        self.assertEqual(self.reward()['qualifying_seller_count'], 1)

    def test_buy_choice_charges_ninety_and_cannot_change_after_use(self):
        self.invite_seller()
        ticket = self.ticket()
        choice = self.client.post('/api/referrals/choice', headers=self.f.auth(), json={'choice': 'BUY'})
        self.assertEqual(choice.status_code, 200, choice.text)
        quote = self.f.reserve(ticket['id'])
        self.assertEqual(quote.status_code, 200, quote.text)
        self.assertEqual(quote.json()['amount_total_cents'], 9000)
        self.assertEqual(self.f.charge(ticket['id']).status_code, 200)
        self.assertEqual(self.client.post('/api/referrals/choice', headers=self.f.auth(), json={'choice': 'SELL'}).status_code, 409)
        with SessionLocal() as db:
            tx = db.query(models.Transaction).one()
            self.assertEqual((tx.amount_total, tx.amount_seller), (Decimal('90'), Decimal('95')))

    def test_settings_stop_new_actions_without_blocking_login_or_existing_purchases(self):
        response = self.client.patch('/api/admin/settings', headers=self.f.auth('admin'), json={
            'maintenance_mode': True, 'reason': 'Mantenimiento de prueba'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.f.upload().status_code, 503)
        self.assertEqual(self.client.post('/api/auth/register', json={
            'email': 'new@example.com', 'password': fixtures.PASSWORD, 'phone_number': '900000000'}).status_code, 503)
        self.assertEqual(self.client.get('/api/auth/me', headers=self.f.auth()).status_code, 200)
        self.assertEqual(self.client.get('/api/purchases', headers=self.f.auth()).status_code, 200)

    def choose(self, choice, role='buyer'):
        response = self.client.post('/api/referrals/choice', headers=self.f.auth(role), json={'choice': choice})
        self.assertEqual(response.status_code, 200, response.text)

    def grant_manual(self, role, rate='.10', seller_rate=0):
        response = self.client.post('/api/admin/rewards', headers=self.f.auth('admin'), json={
            'user_id': str(self.f.ids[role]), 'buyer_discount_rate': rate,
            'seller_commission_rate': seller_rate, 'reason': 'Beneficio manual de prueba'})
        self.assertEqual(response.status_code, 200, response.text)

    def test_buyer_and_seller_can_each_use_their_own_reward_on_one_sale(self):
        self.grant_manual('buyer')
        self.grant_manual('seller')
        self.choose('BUY')
        self.choose('SELL', 'seller')
        ticket = self.ticket()
        self.assertEqual(self.reward('seller')['reward_status'], 'AVAILABLE')  # Not consumed on publication.
        quote = self.f.reserve(ticket['id'])
        self.assertEqual(quote.status_code, 200, quote.text)
        self.assertEqual((quote.json()['amount_total_cents'], quote.json()['commission_rate']), (9000, 0))
        self.assertEqual(self.f.charge(ticket['id']).status_code, 200)
        self.assertEqual(self.reward()['reward_status'], 'USED')
        self.assertEqual(self.reward('seller')['reward_status'], 'USED')
        sale = self.client.get('/api/tickets/my-sales', headers=self.f.auth('seller')).json()[0]
        self.assertEqual((sale['estimated_seller_amount'], sale['commission_rate'], sale['listing_commission_rate']), (100, 0, .05))
        with SessionLocal() as db:
            tx = db.query(models.Transaction).one()
            self.assertEqual((tx.amount_total, tx.commission_platform, tx.amount_seller), (Decimal('90'), Decimal('0'), Decimal('100')))
        second = self.ticket()
        next_quote = self.f.reserve(second['id'])
        self.assertEqual((next_quote.json()['amount_total_cents'], next_quote.json()['commission_rate']), (10000, .05))

    def test_seller_referral_upgrades_an_unused_registration_reward(self):
        code = self.reward()['referral_code']
        self.assertEqual(self.client.post('/api/auth/register', json={
            'email': 'invite@example.com', 'password': fixtures.PASSWORD, 'phone_number': '900000000', 'referral_code': code}).status_code, 201)
        self.assertEqual(self.reward()['discount_rate'], .05)
        self.invite_seller()
        self.ticket()
        self.assertEqual((self.reward()['discount_rate'], self.reward()['choice']), (.10, None))

    def test_upgrade_waits_for_bound_payment_rejection_and_cannot_reprice_it(self):
        from backend.payment_provider import PaymentDeclined
        self.grant_manual('buyer', rate='.05', seller_rate=None)
        # Start with the same snapshot as an automatically earned registration benefit.
        with SessionLocal() as db:
            db.get(models.ReferralReward, self.f.ids['buyer']).reward_kind = 'REGISTRATION'
            db.commit()
        ticket = self.ticket()
        self.assertEqual(self.f.reserve(ticket['id']).json()['amount_total_cents'], 9500)
        self.invite_seller()
        # Existing seller has already published; use another new seller to qualify in-flight.
        with SessionLocal() as db:
            db.add(models.Referral(referred_user_id=self.f.ids['other'], referrer_id=self.f.ids['buyer']))
            db.commit()
        original = self.f.provider.create_charge
        def qualify_during_charge(*args):
            self.f.ids['seller'], previous = self.f.ids['other'], self.f.ids['seller']
            try:
                self.ticket()
            finally:
                self.f.ids['seller'] = previous
            self.assertEqual(self.reward()['discount_rate'], .05)
            self.assertTrue(self.reward()['pending_upgrade'])
            raise PaymentDeclined()
        self.f.provider.create_charge = qualify_during_charge
        rejection = self.f.charge(ticket['id'])
        self.assertEqual(rejection.status_code, 402, rejection.text)
        self.assertTrue(rejection.json()['reservation_released'])
        self.f.provider.create_charge = original
        self.assertEqual((self.reward()['discount_rate'], self.reward()['choice'], self.reward()['reward_status']), (.10, None, 'AVAILABLE'))
        self.choose('BUY')
        quote = self.f.reserve(ticket['id'])
        self.assertEqual(quote.status_code, 200, quote.text)
        self.assertEqual(quote.json()['amount_total_cents'], 9000)
        self.assertEqual(self.f.charge(ticket['id']).status_code, 200)
        self.assertEqual(self.reward()['reward_status'], 'USED')

    def test_manual_revoke_is_audited_and_never_rearms_automatically(self):
        self.grant_manual('buyer')
        response = self.client.request('DELETE', '/api/admin/rewards/' + str(self.f.ids['buyer']),
            headers=self.f.auth('admin'), json={'reason': 'Revocar beneficio de prueba'})
        self.assertEqual(response.status_code, 200, response.text)
        self.invite_seller()
        self.ticket()
        self.assertEqual(self.reward()['reward_status'], 'REVOKED')
        audit = self.client.get('/api/admin/audit', headers=self.f.auth('admin')).json()
        self.assertIn('ADMIN_REWARD_REVOKED', [row['action'] for row in audit])

    def test_admin_cannot_revoke_or_edit_a_reserved_reward(self):
        self.grant_manual('buyer', seller_rate=None)
        self.f.reserve(self.ticket()['id'])
        for method in ('DELETE', 'POST'):
            endpoint = '/api/admin/rewards' + ('/' + str(self.f.ids['buyer']) if method == 'DELETE' else '')
            body = {'reason': 'Intento de cambio en reserva'}
            if method == 'POST':
                body.update(user_id=str(self.f.ids['buyer']), buyer_discount_rate=.2)
            response = self.client.request(method, endpoint, headers=self.f.auth('admin'), json=body)
            self.assertEqual(response.status_code, 409, response.text)

    def test_campaign_mutation_validates_dates_rates_overlap_and_reason(self):
        campaign = self.client.get('/api/admin/campaigns', headers=self.f.auth('admin')).json()[0]
        endpoint = '/api/admin/campaigns/' + campaign['id']
        for body in ({'listing_commission_rate': -1}, {'listing_commission_rate': 1},
                     {'registration_discount_rate': .5001}, {'seller_buyer_discount_rate': .9999},
                     {'ends_at': '2020-01-01T00:00:00-05:00'}, {'starts_at': '2026-11-13T00:00:00'},
                     {'name': None}):
            response = self.client.patch(endpoint, headers=self.f.auth('admin'), json=dict(reason='Validación de prueba', **body))
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.patch(endpoint, headers=self.f.auth('admin'), json={'enabled': False, 'reason': '   '}).status_code, 422)
        new = {k: v for k, v in campaign.items() if k not in ('id', 'archived')}
        new['reason'] = 'Intento campaña superpuesta'
        self.assertEqual(self.client.post('/api/admin/campaigns', headers=self.f.auth('admin'), json=new).status_code, 409)

    def test_next_publication_does_not_qualify_when_first_was_outside_campaign(self):
        self.invite_seller()
        with patch('backend.promotions.in_launch_window', return_value=False):
            self.ticket()
        self.ticket()
        self.assertEqual(self.reward()['reward_status'], 'NOT_EARNED')

    def test_no_campaigns_uses_regular_accounting_and_grants_nothing(self):
        with SessionLocal() as db:
            db.query(models.PromotionCampaign).delete()
            db.commit()
        self.invite_seller()
        ticket = self.ticket()
        self.assertEqual(ticket['commission_rate'], .10)
        self.assertEqual(self.reward()['reward_status'], 'NOT_EARNED')
        self.assertEqual(self.f.reserve(ticket['id']).json()['amount_total_cents'], 10000)
        self.assertEqual(self.f.charge(ticket['id']).status_code, 200)

    def test_used_five_percent_cannot_be_upgraded_or_manually_reset(self):
        self.grant_manual('buyer', rate='.05', seller_rate=None)
        with SessionLocal() as db:
            db.get(models.ReferralReward, self.f.ids['buyer']).reward_kind = 'REGISTRATION'
            db.commit()
        ticket = self.ticket()
        self.assertEqual(self.f.reserve(ticket['id']).status_code, 200)
        self.assertEqual(self.f.charge(ticket['id']).status_code, 200)
        with SessionLocal() as db:
            db.add(models.Referral(referred_user_id=self.f.ids['other'], referrer_id=self.f.ids['buyer']))
            db.commit()
        self.f.ids['seller'] = self.f.ids['other']
        self.ticket()
        reward = self.reward()
        self.assertEqual((reward['reward_status'], reward['discount_rate'], reward['pending_upgrade']), ('USED', .05, False))
        response = self.client.post('/api/admin/rewards', headers=self.f.auth('admin'), json={
            'user_id': str(self.f.ids['buyer']), 'buyer_discount_rate': .10, 'reason': 'Intento de reinicio usado'})
        self.assertEqual(response.status_code, 409, response.text)

    def test_admin_can_stop_new_purchases_but_in_flight_receipt_still_settles(self):
        ticket = self.ticket()
        self.assertEqual(self.f.reserve(ticket['id']).status_code, 200)
        original = self.f.provider.create_charge
        def stop_during_charge(*args):
            stopped = self.client.patch('/api/admin/settings', headers=self.f.auth('admin'), json={
                'purchases_enabled': False, 'reason': 'Pausa mientras pasarela responde'})
            self.assertEqual(stopped.status_code, 200, stopped.text)
            return original(*args)
        self.f.provider.create_charge = stop_during_charge
        self.assertEqual(self.f.charge(ticket['id']).status_code, 200)
        second = self.ticket()
        self.assertEqual(self.f.reserve(second['id']).status_code, 503)
        purchase = self.client.get('/api/purchases', headers=self.f.auth()).json()[0]
        self.assertEqual(self.client.post('/api/purchases/' + purchase['purchase_id'] + '/confirm', headers=self.f.auth()).status_code, 200)


if __name__ == '__main__':
    unittest.main(verbosity=2)
