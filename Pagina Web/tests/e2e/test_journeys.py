"""Real UI + local FastAPI + temporary database/storage; payment gateway is offline."""
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import urllib.request
import uuid

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://127.0.0.1:5179'
API = 'http://127.0.0.1:8006'
OUTPUT = ROOT / 'test-results'


def wait_for(url, process):
    for _ in range(150):
        if process.poll() is not None:
            raise RuntimeError(f'Test server exited: {process.returncode}')
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except OSError:
            time.sleep(.2)
    raise RuntimeError(f'Test server not ready: {url}')


class JourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(exist_ok=True)
        local_python = ROOT / 'backend/venv/Scripts/python.exe'
        backend_python = str(local_python) if local_python.exists() else sys.executable
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        cls.api_log = (OUTPUT / 'api.log').open('w', encoding='utf8')
        cls.backend = subprocess.Popen([backend_python, '-m', 'backend.tests.e2e_server'], cwd=ROOT,
                                      env={**os.environ, 'E2E_API_PORT': '8006', 'FRONTEND_PROD_URL': BASE},
                                      stdout=cls.api_log, stderr=subprocess.STDOUT, creationflags=flags)
        try:
            wait_for(API + '/health', cls.backend)
            cls.frontend = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5179', '--strictPort'], cwd=ROOT / 'frontend',
                env={**os.environ, 'VITE_API_URL': API + '/api', 'VITE_CULQI_PUBLIC_KEY': 'pk_test_offline_fixture'},
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            wait_for(BASE, cls.frontend)
            cls.pw = sync_playwright().start()
            browser_name = os.getenv('TICKIA_BROWSER', 'chromium')
            cls.browser = getattr(cls.pw, browser_name).launch()
        except BaseException:
            if hasattr(cls, 'frontend'):
                cls.frontend.terminate()
                cls.frontend.wait(timeout=10)
            cls.backend.terminate()
            cls.backend.wait(timeout=10)
            cls.api_log.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        for server in [cls.frontend, cls.backend]:
            server.terminate()
            server.wait(timeout=15)
        cls.api_log.close()

    def setUp(self):
        self.contexts = []
        self.javascript_errors = []

    def tearDown(self):
        for context in self.contexts:
            context.close()
        self.assertEqual(self.javascript_errors, [])

    def page(self, mobile=False, declined=False, cancelled=False):
        context = self.browser.new_context(viewport={'width': 360 if mobile else 1440, 'height': 900}, reduced_motion='reduce')
        self.contexts.append(context)
        page = context.new_page()
        page.on('pageerror', lambda error: self.javascript_errors.append(str(error)))
        page.route('https://js.culqi.com/**', lambda route: route.fulfill(body='', content_type='application/javascript'))
        token = 'tkn_test_declined' if declined else 'tkn_test_' + uuid.uuid4().hex
        page.add_init_script('window.testCheckoutCancelled = ' + str(cancelled).lower() + '; window.CulqiCheckout = class { constructor(key, config) { this.token = { id: "' + token + '" }; window.testPaymentAmount = config.settings.amount; } close() {} open() { if (!window.testCheckoutCancelled) this.culqi(); } };')
        page.goto(BASE)
        return page

    def login(self, page, email):
        page.get_by_role('button', name='Ingresar', exact=True).click()
        page.get_by_label('Correo electrónico').fill(email)
        page.get_by_label('Contraseña', exact=True).fill('TestPassword123!')
        page.get_by_role('button', name='Iniciar sesión', exact=True).click()
        expect(page.get_by_role('button', name='Salir', exact=True)).to_be_visible()

    def upload(self, page, label=None, nominated=False, blank=False):
        label = label or 'Plan ' + uuid.uuid4().hex[:8]
        page.get_by_role('button', name='Vender', exact=True).click()
        page.get_by_label('Nombre del evento').fill(label)
        page.get_by_label('Fecha y hora del evento (Perú)').fill('2099-12-01T20:00')
        page.get_by_label('Finalización del evento (Perú)').fill('2099-12-02T01:00')
        page.get_by_label('Zona', exact=True).fill('General')
        page.get_by_label('Tiquetera', exact=True).select_option('teleticket')
        page.get_by_label('Precio de venta (S/)').fill('125.50')
        if nominated:
            page.get_by_label('Tipo de entrada').select_option('nominada')
        # Generate genuine QR bytes using backend's installed OpenCV, no production files.
        local_python = ROOT / 'backend/venv/Scripts/python.exe'
        command = "import cv2,sys; import numpy as np; image=" + ('np.ones((400,400),dtype=np.uint8)*255' if blank else "cv2.QRCodeEncoder_create().encode('https://teleticket.com.pe/ticket/" + uuid.uuid4().hex + "'); image=cv2.copyMakeBorder(image,4,4,4,4,cv2.BORDER_CONSTANT,value=255); image=cv2.resize(image,(500,500),interpolation=cv2.INTER_NEAREST)") + "; sys.stdout.buffer.write(cv2.imencode('.png',image)[1].tobytes())"
        image = subprocess.check_output([str(local_python) if local_python.exists() else sys.executable, '-c', command])
        page.get_by_label('Imagen original de la entrada').set_input_files({'name': 'entrada.png', 'mimeType': 'image/png', 'buffer': image})
        page.get_by_role('button', name='Publicar mi entrada', exact=True).click()
        return label

    def buy(self, page, label):
        page.get_by_role('button', name='Explorar', exact=True).click()
        card = page.get_by_role('article').filter(has=page.get_by_role('heading', name=label, exact=True))
        card.get_by_role('button', name='Comprar entrada para ' + label, exact=True).click()
        page.get_by_role('button', name='Continuar al pago', exact=True).click()

    def test_01_register_open_access_logout_and_login(self):
        page = self.page()
        page.get_by_role('button', name='Ingresar', exact=True).click()
        page.get_by_role('button', name='¿No tienes cuenta? Regístrate').click()
        email = uuid.uuid4().hex[:8] + '@example.com'
        page.get_by_label('Correo electrónico').fill(email)
        page.get_by_label('Teléfono').fill('999999999')
        page.get_by_label('Contraseña', exact=True).fill('TestPassword123!')
        page.get_by_role('button', name='Registrarse', exact=True).click()
        expect(page.get_by_role('button', name='Salir', exact=True)).to_be_visible()
        expect(page.get_by_role('heading', name='Entradas disponibles', exact=True)).to_be_visible()
        page.get_by_role('button', name='Salir', exact=True).click()
        expect(page.get_by_role('button', name='Ingresar', exact=True)).to_be_visible()
        self.login(page, email)

    def test_02_invalid_login_and_duplicate_registration_show_errors(self):
        page = self.page()
        page.get_by_role('button', name='Ingresar', exact=True).click()
        page.get_by_label('Correo electrónico').fill('buyer@example.com')
        page.get_by_label('Contraseña', exact=True).fill('wrong-password')
        page.get_by_role('button', name='Iniciar sesión', exact=True).click()
        expect(page.get_by_role('alert')).to_be_visible()
        page.get_by_role('button', name='¿No tienes cuenta? Regístrate').click()
        page.get_by_label('Teléfono').fill('999999999')
        page.get_by_label('Contraseña', exact=True).fill('TestPassword123!')
        page.get_by_role('button', name='Registrarse', exact=True).click()
        expect(page.get_by_role('alert')).to_be_visible()

    def test_03_publish_search_purchase_and_download(self):
        seller = self.page()
        self.login(seller, 'seller@example.com')
        label = self.upload(seller)
        expect(seller.get_by_text('Publicaste tu entrada.', exact=False)).to_be_visible()
        seller.get_by_role('button', name='Mis ventas', exact=True).click()
        expect(seller.get_by_role('heading', name=label, exact=True)).to_be_visible()
        buyer = self.page()
        self.login(buyer, 'buyer@example.com')
        buyer.get_by_label('Buscar eventos o zonas').fill(label)
        expect(buyer.get_by_role('heading', name=label, exact=True)).to_be_visible()
        self.buy(buyer, label)
        expect(buyer.get_by_text('Pago confirmado.', exact=False)).to_be_visible()
        self.assertEqual(buyer.evaluate('window.testPaymentAmount'), 12550, 'Buyer must pay exactly the listed price')
        buyer.get_by_role('button', name='Mis compras', exact=True).click()
        card = buyer.get_by_role('article').filter(has=buyer.get_by_role('heading', name=label, exact=True))
        card.get_by_role('button', name='Mostrar entrada', exact=True).click()
        expect(buyer.get_by_alt_text('Entrada de ' + label)).to_be_visible()
        self.assertTrue(buyer.get_by_alt_text('Entrada de ' + label).evaluate('(image) => image.complete && image.naturalWidth > 0'))
        buyer.screenshot(path=str(OUTPUT / 'wallet-desktop.png'), full_page=True)
        with buyer.expect_download() as download:
            buyer.get_by_role('link', name='Guardar entrada', exact=True).click()
        self.assertTrue(download.value.suggested_filename.endswith('.png'))

    def test_04_image_without_qr_is_rejected(self):
        page = self.page()
        self.login(page, 'seller@example.com')
        self.upload(page, blank=True)
        expect(page.get_by_role('alert')).to_be_visible()
        expect(page.get_by_text('Publicaste tu entrada.', exact=False)).to_have_count(0)

    def test_05_declined_payment_does_not_create_purchase(self):
        seller = self.page()
        self.login(seller, 'seller@example.com')
        label = self.upload(seller)
        expect(seller.get_by_text('Publicaste tu entrada.', exact=False)).to_be_visible()
        buyer = self.page(declined=True)
        self.login(buyer, 'buyer@example.com')
        self.buy(buyer, label)
        expect(buyer.get_by_role('alert').first).to_be_visible()
        expect(buyer.get_by_text('Pago confirmado.', exact=False)).to_have_count(0)
        buyer.get_by_role('button', name='Mis compras', exact=True).click()
        expect(buyer.get_by_role('heading', name=label, exact=True)).to_have_count(0)

    def test_06_admin_restricted_and_suspend_user(self):
        user = self.page()
        self.login(user, 'buyer@example.com')
        user.goto(BASE + '/#admin')
        expect(user.get_by_role('alert')).to_contain_text('No tienes acceso')
        admin = self.page()
        self.login(admin, 'admin@example.com')
        admin.get_by_role('button', name='Administración', exact=True).click()
        expect(admin.get_by_role('heading', name='Gestión de usuarios', exact=True)).to_be_visible()
        row = admin.get_by_role('row').filter(has_text='other@example.com')
        admin.once('dialog', lambda dialog: dialog.accept())
        row.get_by_role('button', name='Suspender 7 días').click()
        expect(row).to_contain_text('Suspendido')

    def test_07_mobile_themes_keyboard_and_layout(self):
        page = self.page(mobile=True)
        expect(page.get_by_role('heading', name='Tu entrada,', exact=False)).to_be_visible()
        self.assertFalse(page.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
        page.screenshot(path=str(OUTPUT / 'catalog-mobile-dark.png'), full_page=True)
        page.get_by_role('button', name='Activar tema claro', exact=True).click()
        expect(page.locator('html')).to_have_attribute('data-theme', 'light')
        page.screenshot(path=str(OUTPUT / 'catalog-mobile-light.png'), full_page=True)
        page.keyboard.press('Tab')
        self.assertNotEqual(page.evaluate('document.activeElement.tagName'), 'BODY')

    def test_08_self_purchase_fails(self):
        page = self.page()
        self.login(page, 'seller@example.com')
        label = self.upload(page)
        expect(page.get_by_text('Publicaste tu entrada.', exact=False)).to_be_visible()
        self.buy(page, label)
        expect(page.get_by_role('alert').first).to_be_visible()
        expect(page.get_by_text('Pago confirmado.', exact=False)).to_have_count(0)

    def test_09_nominated_sale_renomination_and_delivery(self):
        seller = self.page()
        self.login(seller, 'seller@example.com')
        label = self.upload(seller, nominated=True)
        expect(seller.get_by_text('Publicaste tu entrada.', exact=False)).to_be_visible()
        buyer = self.page()
        self.login(buyer, 'buyer@example.com')
        self.buy(buyer, label)
        expect(buyer.get_by_text('Pago confirmado.', exact=False)).to_be_visible()
        buyer.get_by_role('button', name='Mis compras', exact=True).click()
        purchased = buyer.get_by_role('article').filter(has=buyer.get_by_role('heading', name=label, exact=True))
        expect(purchased.get_by_role('button', name='Pendiente de entrega')).to_be_disabled()
        seller.get_by_role('button', name='Mis ventas', exact=True).click()
        sale = seller.get_by_role('article').filter(has=seller.get_by_role('heading', name=label, exact=True))
        local_python = ROOT / 'backend/venv/Scripts/python.exe'
        command = "import cv2,sys; q=cv2.QRCodeEncoder_create().encode('https://teleticket.com.pe/new/" + uuid.uuid4().hex + "'); q=cv2.copyMakeBorder(q,4,4,4,4,cv2.BORDER_CONSTANT,value=255); q=cv2.resize(q,(500,500),interpolation=cv2.INTER_NEAREST); sys.stdout.buffer.write(cv2.imencode('.png',q)[1].tobytes())"
        image = subprocess.check_output([str(local_python) if local_python.exists() else sys.executable, '-c', command])
        sale.get_by_label('Subir entrada renominada').set_input_files({'name': 'renominada.png', 'mimeType': 'image/png', 'buffer': image})
        expect(seller.get_by_text('Archivo de renominación actualizado.', exact=True)).to_be_visible()
        buyer.reload()
        purchased = buyer.get_by_role('article').filter(has=buyer.get_by_role('heading', name=label, exact=True))
        purchased.get_by_role('button', name='Mostrar entrada', exact=True).click()
        expect(buyer.get_by_alt_text('Entrada de ' + label)).to_be_visible()

    def test_10_cancelled_checkout_can_reopen_without_second_reservation(self):
        seller = self.page()
        self.login(seller, 'seller@example.com')
        label = self.upload(seller)
        expect(seller.get_by_text('Publicaste tu entrada.', exact=False)).to_be_visible()
        buyer = self.page(cancelled=True)
        self.login(buyer, 'buyer@example.com')
        reservations = []
        buyer.on('request', lambda request: reservations.append(request.url) if request.url.endswith('/buy') else None)
        self.buy(buyer, label)
        expect(buyer.get_by_role('button', name='Comprar entrada para ' + label, exact=True)).to_be_enabled()
        buyer.evaluate('window.testCheckoutCancelled = false')
        self.buy(buyer, label)
        expect(buyer.get_by_text('Pago confirmado.', exact=False)).to_be_visible()
        self.assertEqual(len(reservations), 1)

    def test_11_uncertain_payment_does_not_invite_repeated_payment(self):
        seller = self.page()
        self.login(seller, 'seller@example.com')
        label = self.upload(seller)
        expect(seller.get_by_text('Publicaste tu entrada.', exact=False)).to_be_visible()
        buyer = self.page()
        self.login(buyer, 'buyer@example.com')
        buyer.route('**/api/payments/charge', lambda route: route.abort())
        self.buy(buyer, label)
        expect(buyer.get_by_role('alert').first).to_contain_text('No vuelvas a pagar')
        expect(buyer.get_by_role('button', name='Comprar entrada para ' + label, exact=True)).to_be_disabled()

    def test_12_checkout_script_failure_does_not_reserve_a_ticket(self):
        seller = self.page()
        self.login(seller, 'seller@example.com')
        label = self.upload(seller)
        expect(seller.get_by_text('Publicaste tu entrada.', exact=False)).to_be_visible()
        buyer = self.page()
        self.login(buyer, 'buyer@example.com')
        buyer.evaluate('window.CulqiCheckout = undefined')
        reservations = []
        buyer.on('request', lambda request: reservations.append(request.url) if request.url.endswith('/buy') else None)
        self.buy(buyer, label)
        expect(buyer.get_by_role('alert').first).to_contain_text('formulario de pago no está disponible')
        self.assertEqual(reservations, [])

    def test_13_expired_checkout_requests_a_new_reservation(self):
        seller = self.page()
        self.login(seller, 'seller@example.com')
        label = self.upload(seller)
        expect(seller.get_by_text('Publicaste tu entrada.', exact=False)).to_be_visible()
        buyer = self.page(cancelled=True)
        self.login(buyer, 'buyer@example.com')
        buyer.clock.install()
        reservations = []
        buyer.on('request', lambda request: reservations.append(request.url) if request.url.endswith('/buy') else None)
        self.buy(buyer, label)
        buyer.wait_for_function('typeof window.testPaymentAmount === "number"')
        buyer.clock.fast_forward(11 * 60 * 1000)
        buyer.get_by_role('button', name='Comprar entrada para ' + label, exact=True).click()
        buyer.get_by_role('button', name='Continuar al pago', exact=True).click()
        expect(buyer.get_by_role('alert').first).to_be_visible()
        self.assertEqual(len(reservations), 2, 'An expired SDK instance must not be reopened')

    def test_14_conflicting_charge_blocks_repeated_payment(self):
        seller = self.page()
        self.login(seller, 'seller@example.com')
        label = self.upload(seller)
        expect(seller.get_by_text('Publicaste tu entrada.', exact=False)).to_be_visible()
        buyer = self.page()
        self.login(buyer, 'buyer@example.com')
        buyer.route('**/api/payments/charge', lambda route: route.fulfill(status=409, json={'detail': 'Esta compra ya está procesada o pendiente de confirmación.'}))
        self.buy(buyer, label)
        expect(buyer.get_by_role('alert').first).to_contain_text('No vuelvas a pagar')
        expect(buyer.get_by_role('button', name='Comprar entrada para ' + label, exact=True)).to_be_disabled()

    def new_seller_purchase(self):
        seller=self.page()
        seller.get_by_role('button',name='Ingresar',exact=True).click()
        seller.get_by_role('button',name='¿No tienes cuenta? Regístrate').click()
        seller.get_by_label('Correo electrónico').fill(uuid.uuid4().hex[:10]+'@example.com')
        seller.get_by_label('Teléfono').fill('999999999')
        seller.get_by_label('Contraseña',exact=True).fill('TestPassword123!')
        seller.get_by_role('button',name='Registrarse',exact=True).click()
        expect(seller.get_by_role('button',name='Salir',exact=True)).to_be_visible()
        label=self.upload(seller)
        expect(seller.get_by_text('Publicaste tu entrada.',exact=False)).to_be_visible()
        buyer=self.page()
        self.login(buyer,'buyer@example.com')
        self.buy(buyer,label)
        expect(buyer.get_by_text('Pago confirmado.',exact=False)).to_be_visible()
        buyer.get_by_role('button',name='Mis compras',exact=True).click()
        card=buyer.get_by_role('article').filter(has=buyer.get_by_role('heading',name=label,exact=True))
        return buyer,card,label

    def test_15_buyer_confirmation_and_rating_after_verified_payout(self):
        buyer,card,label=self.new_seller_purchase()
        before=buyer.context.request.get(API+'/api/auth/me').json()['rating']
        buyer.once('dialog',lambda dialog:dialog.accept())
        card.get_by_role('button',name='Todo bien con mi entrada',exact=True).click()
        expect(card.get_by_text('Abono al vendedor pendiente de confirmación',exact=True)).to_be_visible()
        buyer.context.request.post(API+'/api/_test/settle')
        buyer.reload()
        expect(card.get_by_text('Abono al vendedor confirmado',exact=True)).to_be_visible()
        self.assertEqual(buyer.context.request.get(API+'/api/auth/me').json()['rating'],min(5,before+.25))

    def claim_journey(self,valid):
        buyer,card,label=self.new_seller_purchase()
        if valid:
            buyer.set_viewport_size({'width':360,'height':900})
        else:
            buyer.get_by_role('button',name='Activar tema claro',exact=True).click()
        before=buyer.context.request.get(API+'/api/auth/me').json()['rating']
        card.get_by_role('button',name='Reportar un problema',exact=True).click()
        self.audit_claim_view(buyer)
        card.get_by_label('Describe el problema').fill('La entrada fue rechazada en el acceso del concierto.')
        card.get_by_label('Evidencia del problema').set_input_files({'name':'evidencia.png','mimeType':'image/png','buffer':(ROOT/'frontend/public/brand/tickia-symbol.png').read_bytes()})
        card.get_by_role('button',name='Presentar reclamo',exact=True).click()
        expect(card.get_by_text('Reclamo en investigación · dinero congelado',exact=True)).to_be_visible()
        admin=self.page()
        self.login(admin,'admin@example.com')
        admin.get_by_role('button',name='Administración',exact=True).click()
        case=admin.get_by_role('article').filter(has=admin.get_by_role('heading',name=label,exact=True))
        expect(case.get_by_role('button',name='Descargar evidencia 1')).to_be_visible()
        if valid:
            admin.set_viewport_size({'width':360,'height':900})
        else:
            admin.get_by_role('button',name='Activar tema claro',exact=True).click()
        self.audit_claim_view(admin)
        with admin.expect_download():
            case.get_by_role('button',name='Descargar evidencia 1').click()
        def handle(dialog):
            dialog.accept('Decisión documentada tras revisar la evidencia del acceso.' if dialog.type=='prompt' else None)
        admin.on('dialog',handle)
        case.get_by_role('button',name='Evidencia concluyente · Reembolsar' if valid else 'Evidencia no concluyente · Abonar al vendedor',exact=True).click()
        expect(case.get_by_text('Reembolso pendiente de confirmación' if valid else 'Abono al vendedor pendiente de confirmación',exact=True)).to_be_visible()
        buyer.context.request.post(API+'/api/_test/settle')
        buyer.reload()
        expect(card.get_by_text('Reembolso confirmado' if valid else 'Abono al vendedor confirmado',exact=True)).to_be_visible()
        expected=min(5,before+.25) if valid else max(0,before-.25)
        self.assertEqual(buyer.context.request.get(API+'/api/auth/me').json()['rating'],expected)
        buyer.screenshot(path=str(OUTPUT/('claim-valid.png' if valid else 'claim-invalid.png')),full_page=True)

    def test_16_valid_claim_admin_evidence_refund_and_rating(self):
        self.claim_journey(True)

    def test_17_invalid_claim_admin_payout_and_rating_deduction(self):
        self.claim_journey(False)

    def test_18_silence_pays_after_deadline_without_rewarding_buyer(self):
        buyer,card,label=self.new_seller_purchase()
        before=buyer.context.request.get(API+'/api/auth/me').json()['rating']
        purchase=next(row for row in buyer.context.request.get(API+'/api/purchases').json() if row['event_name']==label)
        self.assertEqual(buyer.context.request.post(API+'/api/_test/expire/'+purchase['purchase_id']).status,200)
        buyer.reload()
        expect(card.get_by_text('Abono al vendedor pendiente de confirmación',exact=True)).to_be_visible()
        expect(card.get_by_role('button',name='Todo bien con mi entrada',exact=True)).to_have_count(0)
        buyer.context.request.post(API+'/api/_test/settle')
        buyer.reload()
        expect(card.get_by_text('Abono al vendedor confirmado',exact=True)).to_be_visible()
        self.assertEqual(buyer.context.request.get(API+'/api/auth/me').json()['rating'],before)

    def audit_claim_view(self,page):
        page.add_script_tag(path=str(ROOT/'frontend/node_modules/axe-core/axe.min.js'))
        violations=page.evaluate("async () => (await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})).violations.map(v => ({id:v.id,nodes:v.nodes.map(n=>n.target)}))")
        self.assertEqual(violations,[])
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
