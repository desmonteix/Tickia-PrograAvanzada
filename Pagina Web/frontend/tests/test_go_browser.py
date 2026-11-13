"""Browser integration for the production bundle with isolated API/provider fixtures.

Run after npm run build: python tests/test_go_browser.py
Requires Playwright + Chromium; never calls a provider or a real database.
"""
import functools
import base64
import json
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

TX = 'b2d8c790-22a4-4c81-8ef2-5c073dac3f81'
TICKET = '6add9209-d755-4ec1-8918-fb30c814e714'
USER = '58d3ff6a-d709-4a33-80fe-6ac31344eac0'
CAMPAIGN = '06661d9c-aa21-46e9-8c20-1d9dd10d7484'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


class GoBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle = Path(__file__).resolve().parents[1] / 'dist'
        if not (bundle / 'index.html').exists():
            raise RuntimeError('Build the frontend first: npm run build')
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(bundle)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception:
            cls.pw.stop()
            cls.server.shutdown()
            cls.server.server_close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 390, 'height': 844})
        self.page = self.context.new_page()
        self.page.set_default_timeout(8000)
        self.calls, self.external, self.console_errors = [], [], []
        self.page.on('pageerror', lambda err: self.console_errors.append(str(err)))
        self.authenticated, self.expire_transaction = True, False
        self.statuses = ['UNKNOWN']
        self.payouts_enabled = True
        self.checkout_url = 'https://checkout-sbx.dlocalgo.com/fixture'
        self.checkout_status = 'PROCESSING'
        self.checkout_fail_next, self.checkout_released = False, False
        self.reservation_count = 0
        self.preview_reward = 'NOT_EARNED'
        self.preview_choice, self.preview_rate = 'BUY', .05
        self.reward_kind, self.seller_commission_rate = 'REGISTRATION', None
        self.pending_upgrade, self.reject_choice = False, False
        self.commission_rate = .05
        self.is_admin, self.reject_admin = False, False
        self.campaigns, self.rewards, self.claims = [], [], []
        self.reserved_discount = 0
        self.campaign = {'starts_at': '2026-11-13T05:00:00Z', 'ends_at': '2026-12-13T05:00:00Z',
            'timezone': 'America/Lima', 'active': True, 'current_commission_rate': .05,
            'regular_commission_rate': .10, 'launch_commission_rate': .05,
            'referral_discount_rate': .05, 'referral_reward_expires': False}
        self.campaign.update(seller_referral_discount_rate=.10, seller_referral_commission_rate=0,
            settings={'registrations_enabled': True, 'publications_enabled': True, 'purchases_enabled': True,
                      'maintenance_mode': False, 'announcement': ''})
        self.fail_profile = False
        self.profile = {
            'required': True, 'status': 'NOT_CONFIGURED', 'bank_account_last4': None,
            'validation_url': None, 'can_sell': False, 'fee_terms_accepted': False,
            'fee_terms': {'payin_percent': '3.53', 'payin_fixed': '1', 'payout_percent': '0',
                          'payout_fixed': '2', 'tax_rate': '18', 'hash': 'fixture-terms'},
            'error': None,
        }
        self.ticket = {'id': TICKET, 'price': 200, 'estado': 'DISPONIBLE', 'event_name': 'Evento de prueba Go',
                       'event_date': '2027-12-01T20:00:00-05:00', 'zone': 'General', 'ticket_type': 'no_nominada',
                       'is_renominated': False, 'seller_rating': 4}
        self.page.route('**/*', self.route)

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.console_errors, [])

    def route(self, route):
        request = route.request
        parsed = urlsplit(request.url)
        if parsed.netloc != urlsplit(self.origin).netloc:
            self.external.append(request.url)
            route.fulfill(status=200, content_type='text/html', body='<p>Isolated checkout fixture</p>')
            return
        if not parsed.path.startswith('/api/'):
            route.continue_()
            return
        path = parsed.path.removeprefix('/api')
        body = request.post_data_json if request.post_data and request.headers.get('content-type', '').startswith('application/json') else None
        self.calls.append((request.method, path, body))
        status, result = 200, {}
        if path == '/auth/login':
            self.authenticated = True
        elif path == '/auth/me':
            status, result = (200, {'id': USER, 'email': 'seller@example.test', 'is_admin': self.is_admin, 'rating': 4}) if self.authenticated else (401, {'detail': 'Sesión vencida'})
        elif path == '/tickets':
            result = [self.ticket]
        elif path == '/promotions':
            result = self.campaign
        elif path == '/referrals':
            result = {'referral_code': 'Invite_123', 'invite_path': '/?ref=Invite_123#login',
                'qualifying_referral_count': 1 if self.preview_reward != 'NOT_EARNED' else 0,
                'reward_status': self.preview_reward,
                'reward_kind': self.reward_kind, 'choice': self.preview_choice, 'discount_rate': self.preview_rate,
                'seller_commission_rate': self.seller_commission_rate, 'qualifying_seller_count': 1,
                'pending_upgrade': self.pending_upgrade,
                'reserved_ticket_id': None, 'reserved_until': None, 'campaign': self.campaign}
        elif path == '/referrals/choice':
            if self.reject_choice:
                self.preview_reward = 'RESERVED'
                status, result = 409, {'detail': 'El beneficio está reservado; no puedes cambiarlo.'}
            else:
                self.preview_choice = body['choice']
                result = {}
        elif path == '/admin/metrics':
            result = {'total_users': 1, 'total_tickets': 1, 'total_transactions': 0, 'total_revenue': 0}
        elif path == '/admin/users':
            result = [{'id': USER, 'email': 'seller@example.test', 'rating': 4, 'warning_count': 0, 'is_admin': True}]
        elif path == '/purchases/admin/cases':
            result = self.claims
        elif path == '/payments/admin/operations':
            result = []
        elif path == '/admin/campaigns':
            if request.method == 'POST':
                self.campaigns.append({**{k: v for k, v in body.items() if k != 'reason'}, 'id': CAMPAIGN, 'archived': False})
            result = self.campaigns
        elif path == '/admin/campaigns/' + CAMPAIGN:
            if request.method == 'DELETE':
                self.campaigns[0]['archived'] = True
            else:
                self.campaigns[0].update({k: v for k, v in body.items() if k != 'reason'})
            result = self.campaigns[0]
        elif path == '/admin/settings':
            if request.method == 'PATCH':
                self.campaign['settings'].update({k: v for k, v in body.items() if k != 'reason'})
            result = self.campaign['settings']
        elif path == '/admin/rewards':
            if request.method == 'POST':
                if self.reject_admin:
                    status, result = 409, {'detail': 'El beneficio ya está en uso y no puede reemplazarse.'}
                else:
                    self.rewards = [{'user_id': body['user_id'], 'email': 'seller@example.test', 'reward_kind': 'MANUAL',
                        'choice': None, 'discount_rate': body['buyer_discount_rate'], 'seller_commission_rate': body['seller_commission_rate'],
                        'reward_status': 'AVAILABLE', 'pending_upgrade': False}]
                    result = self.rewards[0]
            else:
                result = self.rewards
        elif path == '/admin/rewards/' + USER:
            self.rewards[0]['reward_status'] = 'REVOKED'
            result = self.rewards[0]
        elif path == '/admin/audit':
            result = [{'id': TX, 'action': 'CAMPAIGN_CREATED', 'entity_type': 'campaign', 'entity_id': CAMPAIGN,
                'reason': '<b>Motivo registrado</b>', 'timestamp': '2027-01-01T05:00:00Z'}]
        elif path.startswith('/purchases/evidence/'):
            route.fulfill(status=200, content_type='image/png', body=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aSFEAAAAASUVORK5CYII='))
            return
        elif path == '/payments/status':
            result = {'enabled': True, 'provider': 'dlocal_go', 'payouts_enabled': self.payouts_enabled}
        elif path.endswith('/buy'):
            self.reservation_count += 1
            rid = TX if self.reservation_count == 1 else 'cdb12f73-183f-442b-854d-2cecb6c7df8c'
            result = {'reservation_id': rid, 'listed_amount': 200, 'buyer_discount': self.reserved_discount,
                'amount_total': 200 - self.reserved_discount, 'amount_total_cents': 20000 - self.reserved_discount * 100,
                'buyer_discount_rate': self.reserved_discount / 200,
                'commission_rate': self.commission_rate, 'reserved_until': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
        elif path == '/payments/checkout':
            if self.checkout_fail_next:
                self.checkout_fail_next = False
                if self.checkout_released:
                    self.preview_reward, self.preview_choice, self.preview_rate = 'AVAILABLE', None, .10
                    self.reward_kind, self.seller_commission_rate = 'SELLER_REFERRAL', 0
                    self.reserved_discount = 20
                route.fulfill(status=402, content_type='application/json', body=json.dumps({
                    'detail': 'El proveedor rechazó el pago.', 'reservation_released': self.checkout_released}))
                return
            result = {'transaction_id': TX, 'redirect_url': self.checkout_url, 'status': self.checkout_status, 'amount_total': 200 - self.reserved_discount}
        elif path == f'/payments/transactions/{TX}':
            if self.expire_transaction:
                self.expire_transaction = False
                self.authenticated = False
                status, result = 401, {'detail': 'Sesión vencida'}
            else:
                value = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
                if value == 'SUCCEEDED':
                    self.preview_reward = 'USED'
                elif value == 'FAILED':
                    self.preview_reward, self.preview_choice, self.preview_rate = 'AVAILABLE', None, .10
                    self.reward_kind, self.seller_commission_rate, self.pending_upgrade = 'SELLER_REFERRAL', 0, False
                result = {'transaction_id': TX, 'ticket_id': TICKET, 'status': value, 'provider': 'dlocal_go'}
        elif path == '/payments/payout-profile':
            if request.method == 'POST':
                if body.get('fee_terms_hash') != self.profile['fee_terms']['hash']:
                    route.fulfill(status=409, content_type='application/json', body=json.dumps({'detail': 'Los costos han cambiado. Revisa y acepta la nueva tarifa.'}))
                    return
                if self.fail_profile:
                    self.profile['status'] = 'UNKNOWN'
                    route.abort('failed')
                    return
                self.profile.update(status='PENDING', bank_account_last4='0000', fee_terms_accepted=True,
                                    validation_url='https://verify.legaltalent.ai/s/fixture')
            result = self.profile
        elif path == '/payments/payout-profile/accept-fees':
            if body.get('fee_terms_hash') != self.profile['fee_terms']['hash']:
                route.fulfill(status=409, content_type='application/json', body=json.dumps({'detail': 'Los costos han cambiado.'}))
                return
            self.profile.update(fee_terms_accepted=True, can_sell=True)
            result = self.profile
        elif path == '/tickets/my-sales':
            result = [{**self.ticket, 'estado': 'VENDIDA', 'settlement_state': 'QUEUED', 'settlement_error': None,
                       'settlement_reference': None, 'provider_fee': None, 'seller_net_amount': None, 'total': 200}]
        elif path == '/purchases':
            result = []
        else:
            status, result = 404, {'detail': 'Unknown fixture endpoint'}
        route.fulfill(status=status, content_type='application/json', body=json.dumps(result))

    def visit(self, suffix=''):
        self.page.goto(self.origin + '/' + suffix)

    def fill_profile(self):
        for label, value in [('Nombres', 'Ana'), ('Apellidos', 'Pérez'), ('Número de documento', '12345678'),
                             ('Código del banco (3 dígitos)', '002'), ('CCI de tu cuenta en soles (20 dígitos)', '00200000000000000000')]:
            self.page.get_by_label(label, exact=True).fill(value)
        self.page.get_by_role('checkbox', name='Acepto la comisión').check()

    def test_checkout_uses_go_without_loading_culqi(self):
        self.visit()
        self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
        self.page.get_by_role('button', name='Continuar al pago').click()
        self.page.wait_for_url(self.checkout_url)
        self.assertEqual(self.external, [self.checkout_url])
        self.assertEqual(sum(path == '/payments/checkout' for _, path, _ in self.calls), 1)

    def test_referral_discount_is_reserved_and_sent_with_the_real_payable_amount(self):
        self.preview_reward, self.reserved_discount = 'AVAILABLE', 10
        self.visit()
        expect(self.page.get_by_text('Tienes un 5 % de descuento disponible', exact=False)).to_be_visible()
        expect(self.page.get_by_label('Tu enlace de invitación')).to_have_value(self.origin + '/?ref=Invite_123#login')
        self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
        expect(self.page.get_by_role('dialog')).to_contain_text('190.00')
        self.page.get_by_role('button', name='Continuar al pago').click()
        self.page.wait_for_url(self.checkout_url)
        body = next(body for _, path, body in self.calls if path == '/payments/checkout')
        self.assertEqual(body['reservation_id'], TX)

    def test_lost_reward_requires_a_new_confirmation_without_reserving_twice(self):
        self.preview_reward = 'AVAILABLE'
        self.visit()
        expect(self.page.get_by_text('Tienes un 5 % de descuento disponible', exact=False)).to_be_visible()
        self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
        expect(self.page.get_by_role('dialog')).to_contain_text('190.00')
        self.page.get_by_role('button', name='Continuar al pago').click()
        expect(self.page.get_by_role('dialog').get_by_role('status')).to_contain_text('El importe cambió')
        self.assertFalse(any(path == '/payments/checkout' for _, path, _ in self.calls))
        self.assertEqual(self.external, [])
        self.page.get_by_role('button', name='Confirmar y pagar', exact=False).click()
        self.page.wait_for_url(self.checkout_url)
        self.assertEqual(sum(path.endswith('/buy') for _, path, _ in self.calls), 1)

    def test_seller_reward_choice_applies_ten_percent_only_after_choosing_buy(self):
        self.preview_reward, self.preview_choice, self.preview_rate = 'AVAILABLE', None, .10
        self.reward_kind, self.seller_commission_rate = 'SELLER_REFERRAL', 0
        self.reserved_discount, self.commission_rate = 20, 0
        self.visit()
        self.page.get_by_role('button', name='Usar 0 % de comisión Tickia en mi próxima venta').click()
        expect(self.page.get_by_text('Tu próxima venta elegible tendrá 0 %', exact=False)).to_be_visible()
        self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
        expect(self.page.get_by_role('dialog')).to_contain_text('Total a pagar: S/ 200.00')
        self.page.get_by_role('button', name='Volver', exact=True).click()
        self.page.get_by_role('button', name='Usar 10 % en mi próxima compra').click()
        expect(self.page.get_by_text('Tienes un 10 % de descuento disponible', exact=False)).to_be_visible()
        self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
        expect(self.page.get_by_role('dialog')).to_contain_text('180.00')
        self.page.get_by_role('button', name='Continuar al pago').click()
        self.page.wait_for_url(self.checkout_url)
        self.assertEqual([body['choice'] for method, path, body in self.calls if path == '/referrals/choice'], ['SELL', 'BUY'])

    def test_choice_conflict_and_pending_upgrade_never_change_a_reserved_reward(self):
        self.preview_reward, self.preview_choice, self.preview_rate = 'AVAILABLE', None, .10
        self.seller_commission_rate, self.reject_choice, self.pending_upgrade = 0, True, True
        self.visit()
        self.page.get_by_role('button', name='Usar 10 % en mi próxima compra').click()
        expect(self.page.get_by_role('alert')).to_contain_text('El beneficio está reservado')
        expect(self.page.get_by_text('Hay una mejora pendiente.', exact=False)).to_be_visible()
        expect(self.page.get_by_role('button', name='Usar 10 % en mi próxima compra')).to_have_count(0)

    def test_earned_reward_survives_absent_campaign_without_inventing_a_seller_offer(self):
        self.campaign.update(active=False, starts_at=None, ends_at=None, launch_commission_rate=None,
            seller_referral_commission_rate=None)
        self.preview_reward, self.preview_choice, self.preview_rate = 'AVAILABLE', 'BUY', .10
        self.reward_kind, self.reserved_discount = 'MANUAL', 20
        self.visit()
        expect(self.page.get_by_text('Tienes un 10 % de descuento disponible', exact=False)).to_be_visible()
        self.assertNotIn('NaN', self.page.locator('body').inner_text())
        expect(self.page.get_by_role('button', name='Usar 0 % de comisión Tickia en mi próxima venta')).to_have_count(0)
        self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
        expect(self.page.get_by_role('dialog')).to_contain_text('180.00')
        self.page.get_by_role('button', name='Continuar al pago').click()
        self.page.wait_for_url(self.checkout_url)

    def test_released_failed_quote_requires_new_choice_and_new_reservation_for_same_ticket(self):
        self.preview_reward, self.reserved_discount = 'AVAILABLE', 10
        self.checkout_fail_next, self.checkout_released = True, True
        self.visit()
        expect(self.page.get_by_text('Tienes un 5 % de descuento disponible', exact=False)).to_be_visible()
        self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
        self.page.get_by_role('button', name='Continuar al pago').click()
        expect(self.page.get_by_role('dialog')).not_to_be_visible()
        expect(self.page.get_by_text('La reserva anterior se cerró.', exact=False)).to_be_visible()
        self.assertEqual(self.external, [])
        self.page.get_by_role('button', name='Usar 10 % en mi próxima compra').click()
        expect(self.page.get_by_text('Tienes un 10 % de descuento disponible', exact=False)).to_be_visible()
        self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
        expect(self.page.get_by_role('dialog')).to_contain_text('180.00')
        self.page.get_by_role('button', name='Continuar al pago').click()
        self.page.wait_for_url(self.checkout_url)
        checkouts = [body for _, path, body in self.calls if path == '/payments/checkout']
        self.assertEqual(len(checkouts), 2)
        self.assertNotEqual(checkouts[0]['reservation_id'], checkouts[1]['reservation_id'])
        self.assertEqual(self.reservation_count, 2)

    def test_failed_provider_callback_refreshes_the_pending_upgrade_without_claiming_success(self):
        self.preview_reward, self.pending_upgrade = 'RESERVED', True
        self.statuses = ['FAILED']
        self.visit(f'?payment_transaction={TX}#wallet')
        expect(self.page.get_by_role('status').filter(has_text='El proveedor informa que el pago no se completó.')).to_be_visible()
        expect(self.page.get_by_role('button', name='Usar 10 % en mi próxima compra')).to_be_visible()
        expect(self.page.get_by_text('Hay una mejora pendiente.', exact=False)).to_have_count(0)
        expect(self.page.get_by_text('Pago confirmado por el proveedor.', exact=False)).to_have_count(0)

    def test_maintenance_blocks_new_purchases_but_preserves_payment_tracking(self):
        self.campaign['settings'].update(maintenance_mode=True, announcement='Aviso de mantenimiento')
        self.visit()
        expect(self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go')).to_be_disabled()
        self.statuses = ['SUCCEEDED']
        self.visit(f'?payment_transaction={TX}#wallet')
        expect(self.page.get_by_role('status').filter(has_text='Pago confirmado por el proveedor')).to_be_visible()
        self.assertFalse(any(path.endswith('/buy') for _, path, _ in self.calls))

    def test_admin_creates_edits_and_archives_campaign_with_reasons_and_peru_dates(self):
        self.is_admin = True
        self.visit('#admin')
        self.page.get_by_role('button', name='Campañas', exact=True).click()
        self.page.get_by_role('button', name='Crear campaña', exact=True).click()
        for label, value in [('Nombre de campaña', 'Campaña configurable'), ('Inicio (hora de Perú)', '2027-01-01T00:00'),
            ('Final (hora de Perú)', '2027-02-01T00:00'), ('Comisión por publicación (%)', '7.5'),
            ('Descuento por registro referido (%)', '6'), ('Descuento por vendedor referido (%)', '12'),
            ('Comisión de la venta beneficiada (%)', '0'), ('Motivo del cambio', 'Campaña autorizada para prueba.')]:
            self.page.get_by_label(label, exact=True).fill(value)
        self.page.get_by_role('checkbox', name='Campaña habilitada').check()
        self.page.get_by_role('button', name='Guardar campaña', exact=True).click()
        expect(self.page.get_by_role('status').filter(has_text='Campaña guardada')).to_be_visible()
        self.page.get_by_role('button', name='Editar Campaña configurable', exact=True).click()
        self.page.get_by_label('Comisión por publicación (%)', exact=True).fill('8')
        self.page.get_by_label('Motivo del cambio', exact=True).fill('Ajuste autorizado de la comisión.')
        self.page.get_by_role('button', name='Guardar campaña', exact=True).click()
        expect(self.page.get_by_role('button', name='Cancelar edición')).to_have_count(0)
        self.page.get_by_role('button', name='Archivar Campaña configurable', exact=True).click()
        self.page.get_by_label('Motivo del archivo', exact=True).fill('Finalización autorizada de campaña.')
        self.page.get_by_role('button', name='Confirmar archivo', exact=True).click()
        expect(self.page.get_by_text('Archivada', exact=True)).to_be_visible()
        created = next(body for method, path, body in self.calls if method == 'POST' and path == '/admin/campaigns')
        self.assertEqual((created['listing_commission_rate'], created['starts_at']), (.075, '2027-01-01T00:00:00-05:00'))
        self.assertTrue(all(body.get('reason') for method, path, body in self.calls if path.startswith('/admin/campaigns') and method != 'GET'))

    def test_admin_updates_operational_settings_without_provider_controls(self):
        self.is_admin = True
        self.visit('#admin')
        self.page.get_by_role('button', name='Operación', exact=True).click()
        self.page.get_by_role('checkbox', name='Permitir nuevas compras').uncheck()
        self.page.get_by_label('Aviso público', exact=True).fill('<b>Aviso sin HTML</b>')
        self.page.get_by_label('Motivo de los ajustes', exact=True).fill('Pausa operativa autorizada para prueba.')
        self.page.get_by_role('button', name='Guardar ajustes operativos', exact=True).click()
        expect(self.page.get_by_role('status').filter(has_text='Ajustes guardados')).to_be_visible()
        expect(self.page.locator('p.notice').filter(has_text='<b>Aviso sin HTML</b>')).to_be_visible()
        expect(self.page.get_by_label('Aviso público', exact=True)).to_have_value('<b>Aviso sin HTML</b>')
        self.assertEqual(self.page.locator('b').count(), 0)
        sent = next(body for method, path, body in self.calls if method == 'PATCH' and path == '/admin/settings')
        self.assertFalse(sent['purchases_enabled'])
        self.assertNotIn('PAYMENT_ENABLED', sent)

    def test_admin_grants_and_revokes_without_resetting_history(self):
        self.is_admin = True
        self.visit('#admin')
        self.page.get_by_role('button', name='Beneficios', exact=True).click()
        self.page.get_by_label('Usuario beneficiario', exact=True).select_option(USER)
        self.page.get_by_label('Descuento de compra (%)', exact=True).fill('10')
        self.page.get_by_label('Comisión para próxima venta (%) — opcional', exact=True).fill('0')
        self.page.get_by_label('Motivo del beneficio', exact=True).fill('Beneficio autorizado para prueba.')
        self.page.get_by_role('button', name='Guardar beneficio', exact=True).click()
        expect(self.page.get_by_role('button', name='Revocar seller@example.test')).to_be_visible()
        self.page.get_by_role('button', name='Revocar seller@example.test').click()
        self.page.get_by_label('Motivo de la revocación', exact=True).fill('Revocación autorizada para prueba.')
        self.page.get_by_role('button', name='Confirmar revocación', exact=True).click()
        expect(self.page.get_by_text('REVOKED', exact=True)).to_be_visible()
        expect(self.page.get_by_role('button', name='Guardar beneficio', exact=True)).to_be_disabled()

    def test_admin_conflict_does_not_display_a_successful_manual_grant(self):
        self.is_admin, self.reject_admin = True, True
        self.visit('#admin')
        self.page.get_by_role('button', name='Beneficios', exact=True).click()
        self.page.get_by_label('Usuario beneficiario', exact=True).select_option(USER)
        self.page.get_by_label('Descuento de compra (%)', exact=True).fill('10')
        self.page.get_by_label('Motivo del beneficio', exact=True).fill('Revisión autorizada para prueba.')
        self.page.get_by_role('button', name='Guardar beneficio', exact=True).click()
        expect(self.page.get_by_role('alert')).to_contain_text('ya está en uso')
        expect(self.page.get_by_role('status').filter(has_text='Beneficio guardado')).to_have_count(0)

    def test_admin_claim_filters_preview_private_evidence_and_preserve_decision_buttons(self):
        self.is_admin = True
        self.claims = [{**self.ticket, 'purchase_id': TX, 'review_state': 'DISPUTED', 'settlement_state': 'NONE',
            'decision': None, 'description': 'No permite ingresar al evento.', 'evidence': [{'id': TX, 'media_type': 'image/png'}]}]
        self.visit('#admin')
        self.page.get_by_label('Buscar reclamos', exact=True).fill('No existe')
        expect(self.page.get_by_text('No hay casos que coincidan con estos filtros.')).to_be_visible()
        self.page.get_by_label('Buscar reclamos', exact=True).fill('No permite')
        self.page.get_by_role('button', name='Ver evidencia 1').click()
        expect(self.page.get_by_role('dialog', name='Vista de evidencia')).to_be_visible()
        expect(self.page.get_by_alt_text('Imagen aportada como evidencia del reclamo')).to_be_visible()
        self.page.get_by_role('button', name='Cerrar evidencia').click()
        expect(self.page.get_by_role('button', name='Evidencia concluyente · Reembolsar')).to_be_visible()
        self.assertFalse(any(method == 'POST' and path.endswith('/resolve') for method, path, _ in self.calls))

    def test_admin_control_sections_are_accessible_on_mobile_without_filtering_axe_rules(self):
        self.is_admin = True
        self.page.set_viewport_size({'width': 360, 'height': 900})
        self.page.emulate_media(reduced_motion='reduce')
        self.visit('#admin')
        script = Path(__file__).resolve().parents[1] / 'node_modules/axe-core/axe.min.js'
        self.page.add_script_tag(path=str(script))
        for section in ['Campañas', 'Operación', 'Beneficios', 'Auditoría']:
            with self.subTest(section=section):
                self.page.get_by_role('button', name=section, exact=True).click()
                if section == 'Campañas':
                    expect(self.page.get_by_text('No hay campañas configuradas.', exact=True)).to_be_visible()
                    self.page.get_by_role('button', name='Crear campaña', exact=True).click()
                elif section == 'Operación':
                    expect(self.page.get_by_role('button', name='Guardar ajustes operativos', exact=True)).to_be_enabled()
                elif section == 'Beneficios':
                    expect(self.page.get_by_text('No hay beneficios en esta página.', exact=True)).to_be_visible()
                    expect(self.page.get_by_role('button', name='Guardar beneficio', exact=True)).to_be_enabled()
                else:
                    expect(self.page.get_by_text('<b>Motivo registrado</b>', exact=True)).to_be_visible()
                violations = self.page.evaluate("async () => (await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})).violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))")
                self.assertEqual(violations, [])
                self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > window.innerWidth'))

    def test_invalid_redirect_never_leaves_tickia(self):
        self.checkout_url = 'https://checkout.dlocalgo.com.attacker.test/pay'
        self.visit()
        self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
        self.page.get_by_role('button', name='Continuar al pago').click()
        expect(self.page.get_by_role('alert').first).to_contain_text('No vuelvas a pagar')
        self.assertTrue(self.page.url.startswith(self.origin))
        self.assertEqual(self.external, [])

    def test_uncertain_checkout_has_visible_order_tracking(self):
        self.checkout_status = 'UNKNOWN'
        self.checkout_url = None
        self.statuses = ['UNKNOWN']
        self.visit()
        self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
        self.page.get_by_role('button', name='Continuar al pago').click()
        expect(self.page.get_by_role('heading', name='Estado de tu pago')).to_be_visible()
        expect(self.page.get_by_role('status').filter(has_text='Estamos verificando el pago')).to_be_visible()
        self.assertIn('payment_transaction=' + TX, self.page.url)
        self.assertEqual(self.external, [])
        self.assertEqual(sum(path == '/payments/checkout' for _, path, _ in self.calls), 1)

    def test_already_paid_checkout_returns_to_wallet_without_reopening_provider(self):
        for value, message in [('SUCCEEDED', 'Pago confirmado por el proveedor'),
                               ('REFUNDED', 'Reembolso confirmado por el proveedor'),
                               ('REFUND_PENDING', 'La devolución está pendiente de confirmación')]:
            with self.subTest(status=value):
                self.checkout_status = value
                self.checkout_url = None if value == 'SUCCEEDED' else 'https://checkout-sbx.dlocalgo.com/old-order'
                self.statuses = [value]
                self.visit()
                self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
                self.page.get_by_role('button', name='Continuar al pago').click()
                expect(self.page.get_by_role('heading', name='Mis compras')).to_be_visible()
                expect(self.page.get_by_role('status').filter(has_text=message)).to_be_visible()
                self.assertIn(f'payment_transaction={TX}', self.page.url)
                self.assertEqual(self.external, [])

    def test_disabled_payouts_prevent_reserving(self):
        self.payouts_enabled = False
        self.visit()
        self.page.get_by_role('button', name='Comprar entrada para Evento de prueba Go').click()
        self.page.get_by_role('button', name='Continuar al pago').click()
        expect(self.page.get_by_role('alert').first).to_contain_text('no están disponibles')
        self.assertFalse(any(path.endswith('/buy') for _, path, _ in self.calls))

    def test_return_queries_provider_instead_of_trusting_success_parameter(self):
        self.visit(f'?payment_transaction={TX}&status=success#wallet')
        expect(self.page.get_by_role('status').filter(has_text='Estamos verificando el pago')).to_be_visible()
        expect(self.page.get_by_text('Pago confirmado por el proveedor.', exact=False)).to_have_count(0)
        self.assertFalse(any(path == '/payments/checkout' for _, path, _ in self.calls))

    def test_expired_session_preserves_return_and_recovers_after_login(self):
        self.expire_transaction = True
        self.statuses = ['SUCCEEDED']
        self.visit(f'?payment_transaction={TX}#wallet')
        self.page.get_by_label('Correo electrónico').fill('buyer@example.test')
        self.page.get_by_label('Contraseña', exact=True).fill('isolated-password')
        self.page.get_by_role('button', name='Iniciar sesión', exact=True).click()
        expect(self.page.get_by_role('heading', name='Mis compras')).to_be_visible()
        expect(self.page.get_by_role('status').filter(has_text='Pago confirmado por el proveedor')).to_be_visible()
        self.assertIn(f'payment_transaction={TX}', self.page.url)
        self.assertTrue(self.page.url.endswith('#wallet'))

    def test_profile_registration_and_verification_gate_publication(self):
        self.visit('#seller')
        expect(self.page.get_by_role('button', name='Publicar mi entrada')).to_be_disabled()
        self.fill_profile()
        self.page.get_by_role('button', name='Registrar cuenta y comenzar verificación').click()
        expect(self.page.get_by_role('link', name='Verificar mi identidad')).to_have_attribute('href', 'https://verify.legaltalent.ai/s/fixture')
        expect(self.page.get_by_role('button', name='Publicar mi entrada')).to_be_disabled()
        sent = next(body for method, path, body in self.calls if method == 'POST' and path == '/payments/payout-profile')
        self.assertEqual(sent['account_number'], '00200000000000000000')
        self.assertTrue(sent['accept_fees'])
        self.assertEqual(sent['fee_terms_hash'], 'fixture-terms')
        self.profile.update(status='VERIFIED', can_sell=True)
        self.page.get_by_role('button', name='Consultar verificación').click()
        expect(self.page.get_by_role('button', name='Publicar mi entrada')).to_be_enabled()

    def test_profile_timeout_does_not_offer_duplicate_creation(self):
        self.fail_profile = True
        self.visit('#seller')
        self.fill_profile()
        self.page.get_by_role('button', name='Registrar cuenta y comenzar verificación').click()
        expect(self.page.get_by_role('alert')).to_be_visible()
        expect(self.page.get_by_role('button', name='Registrar cuenta y comenzar verificación')).to_have_count(0)
        self.page.get_by_role('button', name='Consultar verificación').click()
        expect(self.page.get_by_text('Estamos comprobando el registro.', exact=False)).to_be_visible()
        self.assertEqual(sum(method == 'POST' and path == '/payments/payout-profile' for method, path, _ in self.calls), 1)

    def test_changed_fees_need_explicit_reacceptance(self):
        self.profile.update(status='VERIFIED', bank_account_last4='0000', fee_terms_accepted=False)
        self.visit('#seller')
        expect(self.page.get_by_role('button', name='Publicar mi entrada')).to_be_disabled()
        self.page.get_by_role('checkbox', name='Acepto los costos actuales').check()
        self.page.get_by_role('button', name='Confirmar costos actuales').click()
        expect(self.page.get_by_role('button', name='Publicar mi entrada')).to_be_enabled()

    def test_polling_refreshes_the_wallet_only_after_api_success(self):
        self.statuses = ['PROCESSING', 'SUCCEEDED']
        self.visit(f'?payment_transaction={TX}#wallet')
        expect(self.page.get_by_role('status').filter(has_text='El pago sigue en proceso')).to_be_visible()
        expect(self.page.get_by_role('status').filter(has_text='Pago confirmado por el proveedor')).to_be_visible()
        self.assertGreaterEqual(sum(path == '/purchases' for _, path, _ in self.calls), 2)
        expect(self.page.get_by_text('Ya usaste tu descuento por referidos.', exact=False)).to_be_visible()

    def test_fee_change_during_registration_requires_a_new_acceptance(self):
        self.visit('#seller')
        self.fill_profile()
        self.profile['fee_terms'].update(hash='new-fees', payin_percent='4.5')
        self.page.get_by_role('button', name='Registrar cuenta y comenzar verificación').click()
        expect(self.page.get_by_role('alert')).to_contain_text('Los costos han cambiado')
        expect(self.page.get_by_text('Procesamiento: 4.5 %', exact=False)).to_be_visible()
        expect(self.page.get_by_role('checkbox', name='Acepto la comisión')).not_to_be_checked()
        self.assertFalse(self.profile['can_sell'])

    def test_seller_mobile_layout_and_pending_sale_are_honest(self):
        self.page.set_viewport_size({'width': 320, 'height': 850})
        self.visit('#seller')
        expect(self.page.get_by_role('button', name='Registrar cuenta y comenzar verificación')).to_be_visible()
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 320)
        self.page.get_by_role('button', name='Mis ventas', exact=True).click()
        expect(self.page.get_by_text('Abono o devolución pendiente de ejecución.')).to_be_visible()
        expect(self.page.get_by_text('Operación financiera confirmada.')).to_have_count(0)
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 320)


if __name__ == '__main__':
    unittest.main(verbosity=2)
