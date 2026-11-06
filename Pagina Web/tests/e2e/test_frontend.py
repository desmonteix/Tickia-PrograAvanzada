"""Browser regressions with controlled API failures; no production services."""
import os
from pathlib import Path
import subprocess
import time
import unittest
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:5178"


class FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = {**os.environ, "VITE_API_URL": "/api"}
        cls.server = subprocess.Popen(
            ["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "5178", "--strictPort"],
            cwd=ROOT / "frontend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        for _ in range(100):
            try:
                urllib.request.urlopen(BASE, timeout=1).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            cls.server.terminate()
            raise RuntimeError("Vite did not start")
        try:
            cls.pw = sync_playwright().start()
            cls.browser = getattr(cls.pw, os.getenv('TICKIA_BROWSER', 'chromium')).launch()
            # HTML readiness alone does not wait for Vite's cold compilation.
            # Complete fixture startup before applying five-second UI assertions.
            warmup = cls.browser.new_page()
            warmup.route('**/api/**', lambda route: route.fulfill(json=[]))
            warmup.route('**/api/auth/me', lambda route: route.fulfill(status=401, json={}))
            warmup.route('**/api/payments/status', lambda route: route.fulfill(json={'enabled':False}))
            warmup.route('https://js.culqi.com/**', lambda route: route.fulfill(body='',content_type='application/javascript'))
            warmup.goto(BASE)
            expect(warmup.get_by_role('heading', name='Entradas disponibles',exact=True)).to_be_visible(timeout=30000)
            warmup.close()
        except BaseException:
            cls.server.terminate()
            cls.server.wait(timeout=10)
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.terminate()
        cls.server.wait(timeout=10)

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900})
        self.page = self.context.new_page()
        self.page.set_default_timeout(5000)
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.route("**/api/**", lambda route: route.fulfill(status=401, json={"detail": "Sesión requerida"}))
        self.page.route("**/api/tickets", lambda route: route.fulfill(json=[]))
        self.page.route("**/api/payments/status", lambda route: route.fulfill(json={"enabled": False}))
        self.page.route('**/api/purchases/admin/cases', lambda route: route.fulfill(json=[]))
        self.page.route("https://js.culqi.com/**", lambda route: route.fulfill(body="", content_type="application/javascript"))

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [], "Uncaught JavaScript errors")

    def test_catalog_network_failure_is_not_fake_inventory(self):
        self.page.route("**/api/tickets", lambda route: route.fulfill(status=503, json={"detail": "Servicio temporalmente no disponible"}))
        self.page.goto(BASE)
        expect(self.page.get_by_role("alert")).to_be_visible()
        expect(self.page.get_by_text("Concierto Mock", exact=False)).to_have_count(0)
        expect(self.page.get_by_role("button", name="Reintentar")).to_be_visible()

    def test_registration_exposes_required_phone(self):
        self.page.goto(BASE)
        self.page.get_by_role("button", name="Ingresar", exact=True).click()
        self.page.get_by_role("button", name="¿No tienes cuenta? Regístrate").click()
        expect(self.page.get_by_label("Teléfono")).to_be_visible()

    def test_authenticated_user_has_open_catalog(self):
        self.page.route("**/api/auth/me", lambda route: route.fulfill(json={"id": "user", "email": "fan@example.com", "is_admin": False, "has_access": False}))
        self.page.route("**/api/auth/waitlist/status", lambda route: route.fulfill(json={"position": 25, "referral_code": "abc", "referral_count": 0, "has_access": False}))
        self.page.goto(BASE)
        expect(self.page.get_by_role("button", name="Mis compras", exact=False)).to_be_visible()
        expect(self.page.get_by_role("heading", name="Entradas disponibles", exact=True)).to_be_visible()

    def authenticated(self, admin=False):
        self.page.route('**/api/auth/me', lambda route: route.fulfill(json={'id': 'user', 'email': 'fan@example.com', 'is_admin': admin}))

    def inventory(self):
        self.page.route('**/api/tickets', lambda route: route.fulfill(json=[{
            'id': '10000000-0000-0000-0000-000000000001', 'event_name': 'Plan de prueba',
            'event_date': '2099-12-01T20:00:00-05:00', 'zone': 'General', 'ticket_type': 'no_nominada',
            'is_renominated': False, 'estado': 'DISPONIBLE', 'price': 125.50,
        }]))

    def test_failed_wallet_does_not_fabricate_a_purchase(self):
        self.authenticated()
        self.page.route('**/api/purchases', lambda route: route.fulfill(status=503, json={'detail': 'No disponible'}))
        self.page.goto(BASE + '/#wallet')
        expect(self.page.get_by_role('alert')).to_be_visible()
        expect(self.page.get_by_text('Concierto Mock', exact=False)).to_have_count(0)
        expect(self.page.get_by_role('button', name='Mostrar entrada')).to_have_count(0)

    def test_expired_session_returns_to_login(self):
        self.authenticated()
        self.page.goto(BASE)
        self.page.get_by_role('button', name='Mis compras', exact=True).click()
        expect(self.page.get_by_role('heading', name='Bienvenido a Tickia')).to_be_visible()
        expect(self.page.get_by_text('Tu sesión terminó.', exact=False)).to_be_visible()

    def test_validation_array_does_not_crash_authentication(self):
        self.page.route('**/api/auth/login', lambda route: route.fulfill(status=422, json={'detail': [{'loc': ['body', 'email'], 'msg': 'invalid'}]}))
        self.page.goto(BASE + '/#login')
        self.page.get_by_label('Correo electrónico').fill('fan@example.com')
        self.page.get_by_label('Contraseña', exact=True).fill('password')
        self.page.get_by_role('button', name='Iniciar sesión', exact=True).click()
        expect(self.page.get_by_role('alert')).to_contain_text('Revisa los campos')

    def test_disabled_payments_never_reserve_inventory(self):
        self.authenticated()
        self.inventory()
        requests = []
        self.page.on('request', lambda request: requests.append(request.url))
        self.page.goto(BASE)
        self.page.get_by_role('button', name='Comprar entrada para Plan de prueba').click()
        self.page.get_by_role('button', name='Continuar al pago').click()
        expect(self.page.get_by_role('dialog').get_by_role('alert')).to_contain_text('pagos no están disponibles')
        self.assertFalse(any(url.endswith('/buy') for url in requests))

    def test_network_failure_recovers_after_retry(self):
        self.page.route('**/api/tickets', lambda route: route.abort())
        self.page.goto(BASE)
        expect(self.page.get_by_role('alert')).to_be_visible()
        self.page.route('**/api/tickets', lambda route: route.fulfill(json=[]))
        self.page.get_by_role('button', name='Reintentar').click()
        expect(self.page.get_by_role('heading', name='Todavía no hay entradas disponibles')).to_be_visible()
        expect(self.page.get_by_role('alert')).to_have_count(0)

    def test_search_has_clear_empty_state(self):
        self.inventory()
        self.page.goto(BASE)
        self.page.get_by_label('Buscar eventos o zonas').fill('Noexistexyz')
        expect(self.page.get_by_role('heading', name='No encontramos entradas para esa búsqueda')).to_be_visible()
        self.page.get_by_label('Buscar eventos o zonas').fill('General')
        expect(self.page.get_by_role('heading', name='Plan de prueba')).to_be_visible()

    def test_search_preserves_seller_rating_priority(self):
        self.page.route('**/api/tickets', lambda route: route.fulfill(json=[{
            'id': 'high', 'event_name': 'Plan Estelar', 'seller_rating': 5,
            'event_date': '2099-12-01T20:00:00-05:00', 'zone': 'General',
            'ticket_type': 'no_nominada', 'estado': 'DISPONIBLE', 'price': 125.50,
        }, {
            'id': 'low', 'event_name': 'Estelar', 'seller_rating': 2,
            'event_date': '2099-12-01T20:00:00-05:00', 'zone': 'General',
            'ticket_type': 'no_nominada', 'estado': 'DISPONIBLE', 'price': 100,
        }]))
        self.page.goto(BASE)
        self.page.get_by_label('Buscar eventos o zonas').fill('Estelar')
        expect(self.page.get_by_role('article').first.get_by_role('heading')).to_have_text('Plan Estelar')

    def test_failed_logout_keeps_session_visible(self):
        self.authenticated()
        self.page.route('**/api/auth/logout', lambda route: route.fulfill(status=503, json={'detail': 'No se pudo cerrar la sesión'}))
        self.page.goto(BASE)
        self.page.get_by_role('button', name='Salir', exact=True).click()
        expect(self.page.get_by_role('status')).to_contain_text('No se pudo cerrar')
        expect(self.page.get_by_role('button', name='Mis compras', exact=True)).to_be_visible()

    def test_accessibility_catalog_login_seller_wallet_admin(self):
        self.authenticated(admin=True)
        self.inventory()
        self.page.route('**/api/purchases', lambda route: route.fulfill(json=[]))
        self.page.route('**/api/admin/metrics', lambda route: route.fulfill(json={'total_users': 0, 'total_tickets': 0, 'total_transactions': 0, 'total_revenue': 0}))
        self.page.route('**/api/admin/users', lambda route: route.fulfill(json=[]))
        script = ROOT / 'frontend/node_modules/axe-core/axe.min.js'
        for width in [360, 1280]:
            self.page.set_viewport_size({'width': width, 'height': 900})
            for view in ['catalog', 'login', 'seller', 'wallet', 'admin']:
                for theme in ['dark', 'light']:
                    with self.subTest(width=width, view=view, theme=theme):
                        self.page.goto(BASE + '/?check=' + str(width) + view + theme + '#' + view)
                        expect(self.page.get_by_role('button', name='Salir', exact=True)).to_be_visible()
                        if theme == 'light':
                            self.page.get_by_role('button', name='Activar tema claro', exact=True).click()
                        self.page.add_script_tag(path=str(script))
                        violations = self.page.evaluate("async () => (await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21aa']}})).violations.map(v => ({id:v.id, impact:v.impact, nodes:v.nodes.map(n=>n.target)}))")
                        self.assertEqual(violations, [])
                        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > window.innerWidth'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
