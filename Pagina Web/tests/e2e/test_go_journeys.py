"""Go UI + real API + temporary SQLite; only provider HTTP is mocked offline."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import urllib.request
from urllib.parse import urlsplit
import uuid

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://127.0.0.1:5180'
API = 'http://127.0.0.1:8007'


def wait_for(url, process):
    for _ in range(150):
        if process.poll() is not None:
            raise RuntimeError('Isolated Go test server exited')
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except OSError:
            time.sleep(.2)
    raise RuntimeError('Isolated Go test server did not become ready')


class GoJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        output = ROOT / 'test-results'
        output.mkdir(exist_ok=True)
        local_python = ROOT / 'backend/venv/Scripts/python.exe'
        cls.backend_python = str(local_python) if local_python.exists() else sys.executable
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        cls.api_log = (output / 'go-api.log').open('w', encoding='utf-8')
        cls.backend = subprocess.Popen([cls.backend_python, '-m', 'backend.tests.go_e2e_server'], cwd=ROOT,
            env={**os.environ, 'E2E_API_PORT': '8007', 'E2E_GO_FRONTEND': BASE, 'FRONTEND_PROD_URL': BASE},
            stdout=cls.api_log, stderr=subprocess.STDOUT, creationflags=flags)
        cls.frontend = None
        cls.pw = None
        try:
            wait_for(API + '/health', cls.backend)
            cls.frontend = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5180', '--strictPort'], cwd=ROOT / 'frontend',
                env={**os.environ, 'VITE_API_URL': '/api', 'TICKIA_API_PROXY_TARGET': API},
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            wait_for(BASE, cls.frontend)
            cls.pw = sync_playwright().start()
            cls.browser = getattr(cls.pw, os.getenv('TICKIA_BROWSER', 'chromium')).launch()
            page = cls.browser.new_page()
            page.goto(BASE)
            expect(page.get_by_role('heading', name='Entradas disponibles', exact=True)).to_be_visible(timeout=30000)
            page.close()
        except BaseException:
            if cls.pw:
                cls.pw.stop()
            for process in (cls.frontend, cls.backend):
                if process:
                    process.terminate()
                    process.wait(timeout=15)
            cls.api_log.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        for process in (cls.frontend, cls.backend):
            process.terminate()
            process.wait(timeout=15)
        cls.api_log.close()

    def setUp(self):
        self.contexts, self.errors = [], []

    def tearDown(self):
        for context in self.contexts:
            context.close()
        self.assertEqual(self.errors, [])

    def page(self, mobile=False):
        context = self.browser.new_context(viewport={'width': 360 if mobile else 1440, 'height': 900})
        self.contexts.append(context)
        page = context.new_page()
        page.set_default_timeout(15000)
        page.on('pageerror', lambda error: self.errors.append(str(error)))
        # No external scripts, checkout or verification services may be accessed.
        def boundary(route):
            if urlsplit(route.request.url).netloc == urlsplit(BASE).netloc:
                route.continue_()
            elif route.request.url.startswith('https://checkout-sbx.dlocalgo.com/validate/'):
                route.fulfill(content_type='text/html', body='<h1>Checkout Go aislado</h1>')
            else:
                route.abort()
        page.route('**/*', boundary)
        page.goto(BASE)
        return page

    def login(self, page, email):
        page.get_by_role('button', name='Ingresar', exact=True).click()
        page.get_by_label('Correo electrónico').fill(email)
        page.get_by_label('Contraseña', exact=True).fill('TestPassword123!')
        page.get_by_role('button', name='Iniciar sesión', exact=True).click()
        expect(page.get_by_role('button', name='Salir', exact=True)).to_be_visible()

    def seller(self):
        page = self.page(mobile=True)
        self.login(page, 'seller@example.com')
        page.get_by_role('button', name='Vender', exact=True).click()
        profile = page.context.request.get(BASE + '/api/payments/payout-profile').json()
        if profile['status'] == 'NOT_CONFIGURED':
            expect(page.get_by_role('button', name='Publicar mi entrada')).to_be_disabled()
            for label, value in [('Nombres', 'Ana'), ('Apellidos', 'Pérez'), ('Número de documento', '87654321'),
                                 ('Código del banco (3 dígitos)', '002'), ('CCI de tu cuenta en soles (20 dígitos)', '00200000000000000001')]:
                page.get_by_label(label, exact=True).fill(value)
            page.get_by_role('checkbox', name='Acepto la comisión').check()
            page.get_by_role('button', name='Registrar cuenta y comenzar verificación').click()
            expect(page.get_by_role('link', name='Verificar mi identidad')).to_have_attribute('href', 'https://verify.legaltalent.ai/s/fixture-1')
            expect(page.get_by_role('button', name='Publicar mi entrada')).to_be_disabled()
        self.assertEqual(page.request.post(BASE + '/api/_test/go/verify').status, 200)
        page.get_by_role('button', name='Consultar verificación').click()
        expect(page.get_by_role('button', name='Publicar mi entrada')).to_be_enabled()
        return page

    def qr(self):
        script = "import cv2,sys; image=cv2.QRCodeEncoder_create().encode('https://teleticket.com.pe/ticket/" + uuid.uuid4().hex + "'); image=cv2.copyMakeBorder(image,4,4,4,4,cv2.BORDER_CONSTANT,value=255); image=cv2.resize(image,(500,500),interpolation=cv2.INTER_NEAREST); sys.stdout.buffer.write(cv2.imencode('.png',image)[1].tobytes())"
        return subprocess.check_output([self.backend_python, '-c', script])

    def publish(self, page):
        label = 'Plan Go ' + uuid.uuid4().hex[:8]
        page.get_by_label('Nombre del evento').fill(label)
        page.get_by_label('Fecha y hora del evento (Perú)').fill('2099-12-01T20:00')
        page.get_by_label('Finalización del evento (Perú)').fill('2099-12-02T01:00')
        page.get_by_label('Zona', exact=True).fill('General')
        page.get_by_label('Tiquetera', exact=True).select_option('teleticket')
        page.get_by_label('Precio de venta (S/)').fill('100')
        page.get_by_label('Imagen original de la entrada').set_input_files({'name': 'entrada.png', 'mimeType': 'image/png', 'buffer': self.qr()})
        page.get_by_role('button', name='Publicar mi entrada', exact=True).click()
        expect(page.get_by_text('Publicaste tu entrada.', exact=False)).to_be_visible()
        return label

    def notify(self, page, payload):
        raw = json.dumps(payload, separators=(',', ':'))
        signature = hmac.new(b'go_e2e_secret_key', b'go_e2e_api_key' + raw.encode(), hashlib.sha256).hexdigest()
        result = page.request.post(BASE + '/api/payments/webhooks/dlocal-go', data=raw,
            headers={'Content-Type': 'application/json', 'Authorization': 'V2-HMAC-SHA256, Signature: ' + signature})
        self.assertEqual(result.status, 200, result.text())

    def buy(self, label):
        buyer = self.page()
        self.login(buyer, 'buyer@example.com')
        card = buyer.get_by_role('article').filter(has=buyer.get_by_role('heading', name=label, exact=True))
        card.get_by_role('button', name='Comprar entrada para ' + label, exact=True).click()
        buyer.get_by_role('button', name='Continuar al pago', exact=True).click()
        buyer.wait_for_url('https://checkout-sbx.dlocalgo.com/validate/*')
        transaction = buyer.url.rsplit('/', 1)[-1]
        # The real checkout endpoint still has not delivered a purchase.
        self.assertFalse(any(x['event_name'] == label for x in buyer.request.get(BASE + '/api/purchases').json()))
        result = buyer.request.post(BASE + '/api/_test/go/pay/' + transaction).json()
        self.assertEqual(result['amount'], 100)
        self.notify(buyer, {'payment_id': result['payment_id']})
        self.notify(buyer, {'payment_id': result['payment_id']})
        buyer.goto(BASE + '/?payment_transaction=' + transaction + '#wallet')
        expect(buyer.get_by_role('status').filter(has_text='Pago confirmado por el proveedor')).to_be_visible()
        card = buyer.get_by_role('article').filter(has=buyer.get_by_role('heading', name=label, exact=True))
        expect(card.get_by_role('button', name='Mostrar entrada', exact=True)).to_be_enabled()
        return buyer, card

    def test_01_bank_verification_purchase_and_confirmed_bank_payout(self):
        seller = self.seller()
        label = self.publish(seller)
        buyer, card = self.buy(label)
        before = buyer.request.get(BASE + '/api/auth/me').json()['rating']
        card.get_by_role('button', name='Mostrar entrada', exact=True).click()
        expect(buyer.get_by_alt_text('Entrada de ' + label)).to_be_visible()
        self.assertTrue(buyer.get_by_alt_text('Entrada de ' + label).evaluate('(image) => image.complete && image.naturalWidth > 0'))
        buyer.once('dialog', lambda dialog: dialog.accept())
        card.get_by_role('button', name='Todo bien con mi entrada', exact=True).click()
        expect(card.get_by_text('Abono al vendedor pendiente de confirmación', exact=True)).to_be_visible()
        stats = buyer.request.post(BASE + '/api/_test/go/settle').json()
        operation = next(x for x in stats['operations'] if x['kind'] == 'PAYOUT')
        self.assertEqual(operation['amount'], '85.47')
        self.assertNotEqual(operation['status'], 'SUCCEEDED')
        self.assertEqual(buyer.request.get(BASE + '/api/auth/me').json()['rating'], before)
        completed = buyer.request.post(BASE + '/api/_test/go/complete-payout').json()
        for identifier in completed['payout_ids']:
            self.notify(buyer, {'payout_id': identifier})
            self.notify(buyer, {'payout_id': identifier})
        buyer.reload()
        expect(card.get_by_text('Abono al vendedor confirmado', exact=True)).to_be_visible()
        self.assertEqual(buyer.request.get(BASE + '/api/auth/me').json()['rating'], min(5, before + .25))
        stats = buyer.request.post(BASE + '/api/_test/go/settle').json()
        self.assertEqual(stats['provider_posts']['payouts'], 1)
        seller.get_by_role('button', name='Mis ventas', exact=True).click()
        sale = seller.get_by_role('article').filter(has=seller.get_by_role('heading', name=label, exact=True))
        expect(sale.get_by_text('Operación financiera confirmada.', exact=True)).to_be_visible()
        expect(sale.get_by_text('Neto calculado:', exact=False)).to_contain_text('85.47')

    def test_02_dispute_freezes_payout_until_admin_refund_is_verified(self):
        seller = self.seller()
        label = self.publish(seller)
        buyer, card = self.buy(label)
        card.get_by_role('button', name='Reportar un problema', exact=True).click()
        card.get_by_label('Describe el problema').fill('La entrada no permite ingresar; adjunto la evidencia recibida.')
        card.get_by_label('Evidencia del problema').set_input_files({'name': 'evidencia.png', 'mimeType': 'image/png', 'buffer': self.qr()})
        card.get_by_role('button', name='Presentar reclamo', exact=True).click()
        expect(card.get_by_text('Reclamo en investigación · dinero congelado', exact=True)).to_be_visible()
        before = buyer.request.post(BASE + '/api/_test/go/settle').json()['provider_posts']
        admin = self.page()
        self.login(admin, 'admin@example.com')
        admin.get_by_role('button', name='Administración', exact=True).click()
        case = admin.get_by_role('article').filter(has=admin.get_by_role('heading', name=label, exact=True))
        with admin.expect_download():
            case.get_by_role('button', name='Descargar evidencia 1').click()
        admin.on('dialog', lambda dialog: dialog.accept('Evidencia comprobada: corresponde devolver el importe completo.' if dialog.type == 'prompt' else None))
        case.get_by_role('button', name='Evidencia concluyente · Reembolsar', exact=True).click()
        expect(case.get_by_text('Reembolso pendiente de confirmación', exact=True)).to_be_visible()
        stats = buyer.request.post(BASE + '/api/_test/go/settle').json()
        self.assertEqual(stats['provider_posts']['payouts'], before['payouts'])
        refund = next(x for x in stats['operations'] if x['kind'] == 'REFUND')
        self.assertEqual(refund['amount'], '100.00')
        self.assertNotEqual(refund['status'], 'SUCCEEDED')
        completed = buyer.request.post(BASE + '/api/_test/go/complete-payout').json()
        for identifier in completed['refund_ids']:
            self.notify(buyer, {'refund_id': identifier})
            self.notify(buyer, {'refund_id': identifier})
        buyer.reload()
        expect(card.get_by_text('Reembolso confirmado', exact=True)).to_be_visible()
        stats = buyer.request.post(BASE + '/api/_test/go/settle').json()
        self.assertEqual(stats['provider_posts']['refunds'], before['refunds'] + 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
