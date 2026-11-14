"""Real browser -> registration/referrals -> discounted charge -> next full charge.

Uses a temporary API database and an offline provider. No production accounts,
credentials, email, SMS or bank movements are involved.
"""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import urlsplit
import uuid

from playwright.sync_api import expect, sync_playwright
import test_journeys as journeys

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://127.0.0.1:5191'
API = 'http://127.0.0.1:8010'


class PromotionJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        local_python = ROOT / 'backend/venv/Scripts/python.exe'
        cls.python = str(local_python) if local_python.exists() else sys.executable
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        output = ROOT / 'test-results'
        output.mkdir(exist_ok=True)
        cls.log = (output / 'promotions-api.log').open('w', encoding='utf-8')
        cls.api = subprocess.Popen([cls.python, '-m', 'backend.tests.promotions_e2e_server'], cwd=ROOT,
            env={**os.environ, 'TICKIA_LOAD_ENV': '0', 'E2E_API_PORT': '8010', 'FRONTEND_PROD_URL': BASE},
            stdout=cls.log, stderr=subprocess.STDOUT, creationflags=flags)
        try:
            journeys.wait_for(API + '/health', cls.api)
            cls.web = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                '--port', '5191', '--strictPort'], cwd=ROOT / 'frontend',
                env={**os.environ, 'VITE_API_URL': API + '/api', 'VITE_CULQI_PUBLIC_KEY': 'pk_test_offline_fixture'},
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            journeys.wait_for(BASE, cls.web)
            cls.pw = sync_playwright().start()
            cls.browser = getattr(cls.pw, os.getenv('TICKIA_BROWSER', 'chromium')).launch()
        except BaseException:
            for child in (getattr(cls, 'web', None), cls.api):
                if child:
                    child.terminate()
                    child.wait(timeout=10)
            cls.log.close()
            if hasattr(cls, 'pw'):
                cls.pw.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        for child in (cls.web, cls.api):
            child.terminate()
            child.wait(timeout=15)
        cls.log.close()

    def setUp(self):
        self.contexts, self.errors = [], []

    def tearDown(self):
        for context in self.contexts:
            context.close()
        self.assertEqual(self.errors, [])

    def page(self):
        context = self.browser.new_context(viewport={'width': 1280, 'height': 900}, reduced_motion='reduce')
        self.contexts.append(context)
        page = context.new_page()
        page.set_default_timeout(12000)
        page.on('pageerror', lambda error: self.errors.append(str(error)))
        page.route('https://js.culqi.com/**', lambda route: route.fulfill(body='', content_type='application/javascript'))
        # Only the external checkout boundary is simulated. /charge uses the
        # actual API and canonical persisted amount.
        page.add_init_script("window.CulqiCheckout = class { constructor(key, config) { "
            "this.token = {id: 'tkn_test_' + crypto.randomUUID().replaceAll('-', '')}; "
            "window.fixturePaymentAmount = config.settings.amount; } close() {} open() { this.culqi(); } };")
        page.goto(BASE, wait_until='domcontentloaded')
        return page

    login = journeys.JourneyTests.login

    def signup(self, page, link=None):
        if link:
            page.goto(link, wait_until='domcontentloaded')
        else:
            page.get_by_role('button', name='Ingresar', exact=True).click()
            page.get_by_role('button', name='¿No tienes cuenta? Regístrate', exact=True).click()
        expect(page.get_by_role('heading', name='Crea tu cuenta', exact=True)).to_be_visible()
        page.get_by_label('Correo electrónico').fill('promo-' + uuid.uuid4().hex[:12] + '@example.com')
        page.get_by_label('Teléfono').fill('900000003')
        page.get_by_label('Contraseña', exact=True).fill('TestPassword123!')
        page.get_by_role('button', name='Registrarse', exact=True).click()
        expect(page.get_by_role('button', name='Salir', exact=True)).to_be_visible()

    def refresh_reward(self, page):
        with page.expect_response(lambda response: urlsplit(response.url).path == '/api/referrals'):
            page.get_by_role('button', name='Actualizar beneficio', exact=True).click()

    def publish(self, seller):
        label = 'Promotion ' + uuid.uuid4().hex[:8]
        seller.get_by_role('button', name='Vender', exact=True).click()
        seller.get_by_label('Nombre del evento').fill(label)
        seller.get_by_label('Fecha y hora del evento (Perú)').fill('2099-12-01T20:00')
        seller.get_by_label('Finalización del evento (Perú)').fill('2099-12-02T01:00')
        seller.get_by_label('Zona', exact=True).fill('General')
        seller.get_by_label('Tiquetera', exact=True).select_option('teleticket')
        seller.get_by_label('Precio de venta (S/)').fill('100')
        code = "import cv2,sys; image=cv2.QRCodeEncoder_create().encode('https://teleticket.com.pe/ticket/" + uuid.uuid4().hex + "'); image=cv2.copyMakeBorder(image,4,4,4,4,cv2.BORDER_CONSTANT,value=255); image=cv2.resize(image,(500,500),interpolation=cv2.INTER_NEAREST); sys.stdout.buffer.write(cv2.imencode('.png',image)[1].tobytes())"
        data = subprocess.check_output([self.python, '-c', code])
        seller.get_by_label('Imagen original de la entrada').set_input_files(
            {'name': 'ticket.png', 'mimeType': 'image/png', 'buffer': data})
        seller.get_by_role('button', name='Publicar mi entrada', exact=True).click()
        expect(seller.get_by_text('Publicaste tu entrada.', exact=False)).to_be_visible()
        return label

    def buy(self, buyer, label, expected_cents):
        # Inventory was loaded before the other browser published its listing.
        buyer.reload(wait_until='domcontentloaded')
        expect(buyer.get_by_role('button', name='Salir', exact=True)).to_be_visible()
        expect(buyer.get_by_label('Tu enlace de invitación')).to_be_visible()
        buyer.get_by_role('button', name='Explorar', exact=True).click()
        buyer.get_by_label('Buscar eventos o zonas').fill(label)
        buyer.get_by_role('button', name='Comprar entrada para ' + label, exact=True).click()
        expect(buyer.get_by_role('dialog').get_by_text('Total a pagar', exact=False)).to_be_visible()
        with buyer.expect_response(lambda response: urlsplit(response.url).path == '/api/payments/charge'
                                   and response.request.method == 'POST') as charge:
            buyer.get_by_role('button', name='Continuar al pago', exact=True).click()
        self.assertEqual(charge.value.status, 200)
        expect(buyer.get_by_text('Pago confirmado.', exact=False)).to_be_visible()
        self.assertEqual(buyer.evaluate('window.fixturePaymentAmount'), expected_cents)

    def test_invited_registration_grants_one_discount_and_next_purchase_pays_full_price(self):
        buyer, seller = self.page(), self.page()
        self.login(buyer, 'buyer@example.com')
        self.login(seller, 'seller@example.com')
        link = buyer.get_by_label('Tu enlace de invitación').input_value()
        self.assertEqual(urlsplit(link).netloc, urlsplit(BASE).netloc)
        friend = self.page()
        friend.goto(link, wait_until='domcontentloaded')
        expect(friend.get_by_role('heading', name='Crea tu cuenta', exact=True)).to_be_visible()
        expect(friend.get_by_label('Código de invitación (opcional)')).not_to_have_value('')
        friend.get_by_label('Correo electrónico').fill('invited-' + uuid.uuid4().hex[:12] + '@example.com')
        friend.get_by_label('Teléfono').fill('900000003')
        friend.get_by_label('Contraseña', exact=True).fill('TestPassword123!')
        friend.get_by_role('button', name='Registrarse', exact=True).click()
        expect(friend.get_by_role('button', name='Salir', exact=True)).to_be_visible()
        expect(friend.get_by_text('Aún no tienes un descuento por referidos.', exact=True)).to_be_visible()
        buyer.get_by_role('button', name='Actualizar beneficio', exact=True).click()
        expect(buyer.get_by_text('Tienes un 5 % de descuento disponible', exact=False)).to_be_visible()
        first = self.publish(seller)
        self.buy(buyer, first, 9500)
        expect(buyer.get_by_text('Ya usaste tu descuento por referidos.', exact=False)).to_be_visible()
        second = self.publish(seller)
        self.buy(buyer, second, 10000)
        ledger = buyer.request.get(API + '/api/_test/promotion-ledger').json()
        self.assertEqual(len(ledger), 2)
        self.assertEqual([row['status'] for row in ledger], ['SUCCEEDED', 'SUCCEEDED'])
        self.assertEqual([(r['listed_amount'], r['buyer_discount'], r['amount_total'], r['commission'], r['seller_amount'])
                          for r in ledger], [(100, 5, 95, 5, 95), (100, 0, 100, 5, 95)])
        buyer.get_by_role('button', name='Mis compras', exact=True).click()
        expect(buyer.get_by_role('heading', name=first, exact=True)).to_be_visible()
        buyer.screenshot(path=str(ROOT / 'test-results/promotions-wallet.png'), full_page=True)

    def test_seller_referral_upgrades_to_ten_percent_and_choice_cannot_be_reused(self):
        inviter, invited = self.page(), self.page()
        self.signup(inviter)
        link = inviter.get_by_label('Tu enlace de invitación').input_value()
        self.signup(invited, link)
        self.refresh_reward(inviter)
        expect(inviter.get_by_text('Tienes un 5 % de descuento disponible', exact=False)).to_be_visible()
        label = self.publish(invited)
        self.refresh_reward(inviter)
        expect(inviter.get_by_text('Tienes un beneficio disponible para elegir entre compra y venta.', exact=True)).to_be_visible()
        with inviter.expect_response(lambda response: urlsplit(response.url).path == '/api/referrals/choice') as choice:
            inviter.get_by_role('button', name='Usar 10 % en mi próxima compra', exact=True).click()
        self.assertEqual(choice.value.status, 200)
        expect(inviter.get_by_text('Tienes un 10 % de descuento disponible', exact=False)).to_be_visible()
        self.buy(inviter, label, 9000)
        expect(inviter.get_by_text('Ya usaste tu descuento por referidos.', exact=False)).to_be_visible()
        self.assertEqual(inviter.get_by_role('button', name='Usar 0 % de comisión Tickia en mi próxima venta', exact=True).count(), 0)
        ledger = inviter.request.get(API + '/api/_test/promotion-ledger').json()
        self.assertEqual((ledger[-1]['amount_total'], ledger[-1]['commission'], ledger[-1]['seller_amount']), (90, 5, 95))

    def test_seller_choice_waives_only_next_sale_not_gateway_costs(self):
        inviter, invited, buyer = self.page(), self.page(), self.page()
        self.signup(inviter)
        link = inviter.get_by_label('Tu enlace de invitación').input_value()
        self.signup(invited, link)
        self.publish(invited)
        self.refresh_reward(inviter)
        with inviter.expect_response(lambda response: urlsplit(response.url).path == '/api/referrals/choice') as choice:
            inviter.get_by_role('button', name='Usar 0 % de comisión Tickia en mi próxima venta', exact=True).click()
        self.assertEqual(choice.value.status, 200)
        expect(inviter.get_by_text('Tu próxima venta elegible tendrá 0 % de comisión Tickia.', exact=False)).to_be_visible()
        label = self.publish(inviter)
        self.signup(buyer)
        self.buy(buyer, label, 10000)
        inviter.get_by_role('button', name='Explorar', exact=True).click()
        self.refresh_reward(inviter)
        expect(inviter.get_by_text('Ya usaste tu descuento por referidos.', exact=False)).to_be_visible()
        ledger = inviter.request.get(API + '/api/_test/promotion-ledger').json()
        self.assertEqual((ledger[-1]['amount_total'], ledger[-1]['commission'], ledger[-1]['seller_amount']), (100, 0, 100))

    def test_z_admin_campaign_crud_and_operation_controls_use_real_api(self):
        admin = self.page()
        self.login(admin, 'admin@example.com')
        admin.get_by_role('button', name='Administración', exact=True).click()
        admin.get_by_role('button', name='Campañas', exact=True).click()
        admin.get_by_role('button', name='Crear campaña', exact=True).click()
        name = 'Campaña E2E ' + uuid.uuid4().hex[:8]
        admin.get_by_label('Nombre de campaña', exact=True).fill(name)
        admin.get_by_label('Inicio (hora de Perú)', exact=True).fill('2098-01-01T00:00')
        admin.get_by_label('Final (hora de Perú)', exact=True).fill('2098-02-01T00:00')
        for label, value in [('Comisión por publicación (%)', '4'), ('Descuento por registro referido (%)', '3'),
                             ('Descuento por vendedor referido (%)', '9'), ('Comisión de la venta beneficiada (%)', '0')]:
            admin.get_by_label(label, exact=True).fill(value)
        admin.get_by_label('Campaña habilitada', exact=True).check()
        admin.get_by_label('Motivo del cambio', exact=True).fill('Campaña creada desde navegador aislado')
        with admin.expect_response(lambda response: urlsplit(response.url).path == '/api/admin/campaigns'
                                    and response.request.method == 'POST') as created:
            admin.get_by_role('button', name='Guardar campaña', exact=True).click()
        self.assertEqual(created.value.status, 201, created.value.text())
        expect(admin.get_by_role('row').filter(has_text=name)).to_contain_text('4 %')
        admin.get_by_role('button', name='Editar ' + name, exact=True).click()
        expect(admin.get_by_label('Inicio (hora de Perú)', exact=True)).to_have_value('2098-01-01T00:00')
        admin.get_by_label('Comisión por publicación (%)', exact=True).fill('6')
        admin.get_by_label('Motivo del cambio', exact=True).fill('Actualizar comisión sin alterar historial')
        invalid = admin.locator('form input:invalid, form textarea:invalid').evaluate_all(
            'elements => elements.map(e => ({name:e.name, value:e.value, message:e.validationMessage}))')
        self.assertEqual(invalid, [], 'Campaign edit fields must satisfy native browser validation')
        with admin.expect_response(lambda response: response.request.method == 'PATCH' and '/admin/campaigns/' in response.url) as edited:
            admin.get_by_role('button', name='Guardar campaña', exact=True).click()
            self.assertEqual(admin.get_by_role('alert').all_text_contents(), [], 'Campaign edit must not fail client-side validation')
        self.assertEqual(edited.value.status, 200, edited.value.text())
        admin.get_by_role('button', name='Archivar ' + name, exact=True).click()
        admin.get_by_label('Motivo del archivo', exact=True).fill('Campaña de prueba finalizada correctamente')
        with admin.expect_response(lambda response: response.request.method == 'DELETE' and '/admin/campaigns/' in response.url) as archived:
            admin.get_by_role('button', name='Confirmar archivo', exact=True).click()
        self.assertEqual(archived.value.status, 200, archived.value.text())
        expect(admin.get_by_role('row').filter(has_text=name)).to_contain_text('Archivada')
        admin.get_by_role('button', name='Operación', exact=True).click()
        admin.get_by_label('Activar mantenimiento', exact=True).check()
        admin.get_by_label('Aviso público', exact=True).fill('Mantenimiento E2E <b>texto literal</b>')
        admin.get_by_label('Motivo de los ajustes', exact=True).fill('Comprobar pausa y aviso en navegador real')
        with admin.expect_response(lambda response: response.request.method == 'PATCH' and '/admin/settings' in response.url) as settings:
            admin.get_by_role('button', name='Guardar ajustes operativos', exact=True).click()
        self.assertEqual(settings.value.status, 200, settings.value.text())
        expect(admin.locator('p.notice').filter(has_text='Mantenimiento E2E')).to_be_visible()
        self.assertEqual(admin.locator('p.notice b').count(), 0)
        admin.get_by_role('button', name='Auditoría', exact=True).click()
        expect(admin.get_by_role('row').filter(has_text='ADMIN_CAMPAIGN_ARCHIVED')).to_be_visible()
        admin.screenshot(path=str(ROOT / 'test-results/promotions-admin-audit.png'), full_page=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
