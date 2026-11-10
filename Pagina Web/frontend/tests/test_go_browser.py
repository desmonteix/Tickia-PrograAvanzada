"""Browser integration for the production bundle with isolated API/provider fixtures.

Run after npm run build: python tests/test_go_browser.py
Requires Playwright + Chromium; never calls a provider or a real database.
"""
import functools
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
            status, result = (200, {'id': 'fixture-user', 'email': 'seller@example.test', 'is_admin': False, 'rating': 4}) if self.authenticated else (401, {'detail': 'Sesión vencida'})
        elif path == '/tickets':
            result = [self.ticket]
        elif path == '/payments/status':
            result = {'enabled': True, 'provider': 'dlocal_go', 'payouts_enabled': self.payouts_enabled}
        elif path.endswith('/buy'):
            result = {'amount_total_cents': 20000, 'reserved_until': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
        elif path == '/payments/checkout':
            result = {'transaction_id': TX, 'redirect_url': self.checkout_url, 'status': self.checkout_status, 'amount_total': 200}
        elif path == f'/payments/transactions/{TX}':
            if self.expire_transaction:
                self.expire_transaction = False
                self.authenticated = False
                status, result = 401, {'detail': 'Sesión vencida'}
            else:
                value = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
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
