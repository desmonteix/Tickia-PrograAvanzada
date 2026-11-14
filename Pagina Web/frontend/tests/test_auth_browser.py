"""Production bundle + isolated HTTP API with real HttpOnly/Lax cookies.

Run after npm run build: python tests/test_auth_browser.py
No production services, accounts, credentials, SMS or emails are used.
"""
import functools
import json
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright


class AuthHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, status, value, cookie=None):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Closing the browser cancels outstanding catalog requests.

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/auth/me':
            valid = 'access_token=auth-browser-fixture' in self.headers.get('Cookie', '')
            if valid and self.server.fixture.fail_next_session:
                self.server.fixture.fail_next_session = False
                valid = False
            self.respond(200 if valid else 401, self.server.fixture.user if valid else {'detail': 'Sin sesión'})
        elif path == '/api/tickets':
            self.respond(200, [])
        elif path == '/api/payments/status':
            self.respond(200, {'enabled': False, 'provider': 'culqi'})
        elif path == '/api/promotions':
            self.respond(200, {'active': False, 'settings': self.server.fixture.settings})
        elif path == '/api/referrals':
            self.respond(200, {'referral_code': 'Invite_123', 'qualifying_referral_count': 0,
                'reward_status': 'NOT_EARNED', 'discount_rate': .05})
        else:
            super().do_GET()

    def do_POST(self):
        fixture = self.server.fixture
        path = urlsplit(self.path).path
        fixture.calls.append(path)
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if path == '/api/auth/register':
            value = json.loads(body)
            fixture.registration = value
            fixture.account = (value['email'], value['password'])
            fixture.user['email'] = value['email']
            self.respond(201, fixture.user)
        elif path == '/api/auth/login':
            if fixture.fail_next_login:
                fixture.fail_next_login = False
                return self.respond(503, {'detail': 'Inicio de sesión temporalmente no disponible.'})
            form = parse_qs(body.decode())
            if (form.get('username', [''])[0], form.get('password', [''])[0]) != fixture.account:
                return self.respond(401, {'detail': 'Credenciales incorrectas.'})
            self.respond(200, {'access_token': 'auth-browser-fixture', 'token_type': 'bearer'},
                'access_token=auth-browser-fixture; HttpOnly; SameSite=Lax; Path=/')
        elif path == '/api/auth/logout':
            self.respond(200, {}, 'access_token=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/')
        else:
            self.respond(404, {})


class AuthBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle = Path(__file__).resolve().parents[1] / 'dist'
        if not (bundle / 'index.html').exists():
            raise RuntimeError('Run npm run build first')
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(AuthHandler, directory=str(bundle)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch(timeout=20000)
        except BaseException:
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
        self.server.fixture = self
        self.account = None
        self.fail_next_login = False
        self.fail_next_session = False
        self.settings = {'registrations_enabled': True, 'publications_enabled': True, 'purchases_enabled': True,
                         'maintenance_mode': False, 'announcement': ''}
        self.calls, self.external, self.errors = [], [], []
        self.user = {'id': 'b2d8c790-22a4-4c81-8ef2-5c073dac3f81', 'email': 'fixture@example.com',
                     'is_admin': False, 'rating': 4, 'warning_count': 0, 'trust_score': 100,
                     'is_kyc_verified': False, 'is_email_verified': False}
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.set_default_timeout(8000)
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        def boundary(route):
            if urlsplit(route.request.url).netloc == urlsplit(self.origin).netloc:
                route.continue_()
            else:
                self.external.append(urlsplit(route.request.url).netloc)
                route.abort()
        self.page.route('**/*', boundary)

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def signup(self):
        self.page.goto(self.origin + '/#login', wait_until='domcontentloaded')
        self.page.locator('section[aria-labelledby="auth-title"] > button').click()
        self.page.locator('#auth-email').fill('fixture@example.com')
        self.page.locator('#auth-phone').fill('000000000')
        self.page.locator('#auth-password').fill('FixturePassword123!')
        self.page.get_by_role('button', name='Registrarse', exact=True).click()

    def test_signup_login_session_and_logout_use_the_real_same_origin_cookie(self):
        self.signup()
        expect(self.page.get_by_role('button', name='Salir', exact=True)).to_be_visible()
        expect(self.page.get_by_role('heading', name='Entradas disponibles', exact=True)).to_be_visible()
        expect(self.page.locator('section[aria-labelledby="auth-title"]')).to_have_count(0)
        self.page.reload(wait_until='domcontentloaded')
        expect(self.page.get_by_role('button', name='Salir', exact=True)).to_be_visible()
        self.page.get_by_role('button', name='Salir', exact=True).click()
        expect(self.page.get_by_role('button', name='Ingresar', exact=True)).to_be_visible()
        with self.page.expect_response(lambda response: urlsplit(response.url).path == '/api/auth/me') as session:
            self.page.reload(wait_until='domcontentloaded')
        self.assertEqual(session.value.status, 401)
        expect(self.page.get_by_role('button', name='Ingresar', exact=True)).to_be_visible()
        self.page.get_by_role('button', name='Ingresar', exact=True).click()
        self.page.locator('#auth-email').fill('fixture@example.com')
        self.page.locator('#auth-password').fill('FixturePassword123!')
        self.page.get_by_role('button', name='Iniciar sesión', exact=True).click()
        expect(self.page.get_by_role('button', name='Salir', exact=True)).to_be_visible()
        expect(self.page.get_by_role('heading', name='Entradas disponibles', exact=True)).to_be_visible()
        expect(self.page.locator('section[aria-labelledby="auth-title"]')).to_have_count(0)
        self.assertEqual(self.calls.count('/api/auth/register'), 1)
        self.assertEqual(self.external, [])

    def test_referral_opens_signup_and_clears_attribution_after_register_even_when_login_fails(self):
        self.fail_next_login = True
        self.page.goto(self.origin + '/?ref=Invite_123#login')
        expect(self.page.locator('#auth-title')).to_have_text('Crea tu cuenta')
        expect(self.page.get_by_label('Código de invitación (opcional)')).to_have_value('Invite_123')
        self.page.locator('#auth-email').fill('fixture@example.com')
        self.page.locator('#auth-phone').fill('000000000')
        self.page.locator('#auth-password').fill('FixturePassword123!')
        self.page.get_by_role('button', name='Registrarse', exact=True).click()
        expect(self.page.get_by_role('alert')).to_contain_text('temporalmente no disponible')
        self.assertEqual(self.registration['referral_code'], 'Invite_123')
        self.assertNotIn('ref=', self.page.url)
        self.assertIsNone(self.page.evaluate("sessionStorage.getItem('tickia:referral-code')"))
        self.page.get_by_role('button', name='Iniciar sesión', exact=True).click()
        expect(self.page.get_by_role('button', name='Salir', exact=True)).to_be_visible()
        expect(self.page.get_by_role('heading', name='Entradas disponibles', exact=True)).to_be_visible()
        expect(self.page.locator('section[aria-labelledby="auth-title"]')).to_have_count(0)
        self.assertEqual(self.calls.count('/api/auth/register'), 1)

    def test_created_account_can_retry_login_without_repeating_registration(self):
        self.fail_next_login = True
        self.signup()
        expect(self.page.get_by_role('alert')).to_contain_text('temporalmente no disponible')
        expect(self.page.get_by_role('status')).to_contain_text('Tu cuenta ya está creada')
        expect(self.page.locator('#auth-title')).to_have_text('Bienvenido a Tickia')
        self.page.get_by_role('button', name='Iniciar sesión', exact=True).click()
        expect(self.page.get_by_role('button', name='Salir', exact=True)).to_be_visible()
        self.assertEqual(self.calls.count('/api/auth/register'), 1)

    def test_registration_pause_keeps_login_available(self):
        self.settings['registrations_enabled'] = False
        self.page.goto(self.origin + '/?ref=Invite_123#login', wait_until='domcontentloaded')
        expect(self.page.get_by_role('button', name='Registrarse', exact=True)).to_be_disabled()
        self.page.get_by_role('button', name='¿Ya tienes cuenta? Inicia sesión').click()
        expect(self.page.get_by_role('button', name='Iniciar sesión', exact=True)).to_be_enabled()
        self.assertEqual(self.calls.count('/api/auth/register'), 0)

    def test_created_account_can_retry_when_login_succeeds_but_session_check_fails(self):
        self.fail_next_session = True
        self.signup()
        expect(self.page.get_by_role('alert')).to_contain_text('Sin sesión')
        expect(self.page.get_by_role('status')).to_contain_text('Tu cuenta ya está creada')
        expect(self.page.locator('#auth-title')).to_have_text('Bienvenido a Tickia')
        self.page.get_by_role('button', name='Iniciar sesión', exact=True).click()
        expect(self.page.get_by_role('button', name='Salir', exact=True)).to_be_visible()
        self.assertEqual(self.calls.count('/api/auth/register'), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
