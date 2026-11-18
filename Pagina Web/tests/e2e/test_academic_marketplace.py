"""Recorrido real sobre MySQL AISLADO: TICKIA_ACADEMIC_URL=http://127.0.0.1:5201.

Crea cuentas y pedidos de prueba. Nunca apuntar a una instancia de uso real.
"""
import csv
import io
import os
from pathlib import Path
import re
import unittest
import uuid
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

URL = os.getenv('TICKIA_ACADEMIC_URL', '')
ARTIFACTS = Path(__file__).resolve().parents[3]/'Proyecto_PrograAvanzada'/'.local'


@unittest.skipUnless(URL, 'Requiere la instancia MySQL aislada de prueba')
class AcademicBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()
        ARTIFACTS.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def context(self, mobile=False):
        context = self.browser.new_context(viewport={'width':390 if mobile else 1440,'height':844 if mobile else 1000})
        self.addCleanup(context.close)
        page = context.new_page()
        page.on('pageerror',lambda error:self.errors.append(str(error)))
        page.on('request',lambda request:self.external.append(request.url) if urlparse(request.url).hostname not in ('localhost','127.0.0.1') else None)
        return context,page

    def register(self,page,role):
        page.get_by_role('button',name='¿No tienes cuenta? Regístrate').click()
        page.get_by_label('Correo electrónico',exact=True).fill(role+'-'+uuid.uuid4().hex+'@example.com')
        page.get_by_label('Teléfono',exact=True).fill('999999999')
        page.get_by_label('Contraseña',exact=True).fill('University123!')
        page.get_by_role('button',name='Registrarse',exact=True).click()
        expect(page.get_by_role('button',name='Salir',exact=True)).to_be_visible()

    def open_product(self,page,title):
        page.goto(URL+'/#catalog')
        expect(page.get_by_role('searchbox')).to_be_visible()
        page.get_by_role('searchbox').fill(title)
        page.get_by_role('button',name='Comprar '+title,exact=True).click()
        modal=page.get_by_role('dialog')
        expect(modal.get_by_role('heading',name=title,exact=True)).to_be_visible()
        return modal

    def test_multi_vendor_purchase_shipping_social_and_full_analytics(self):
        self.errors,self.external=[],[]
        seller_context,seller=self.context()
        seller.goto(URL)
        self.assertEqual(seller_context.request.get(URL+'/api/runtime').json()['database'],'mysql')
        seller.get_by_role('button',name='Vender',exact=True).click()
        self.register(seller,'seller')
        expect(seller.get_by_role('heading',name='Publicar un producto')).to_be_visible()
        title='Rúbrica A '+uuid.uuid4().hex[:10]
        seller.get_by_label('Nombre del producto',exact=True).fill(title)
        seller.get_by_label('Descripción',exact=True).fill('Producto del recorrido completo de la rúbrica.')
        seller.get_by_label('Precio (S/)',exact=True).fill('25.00')
        seller.get_by_label('Stock disponible',exact=True).fill('5')
        seller.get_by_label('Categoría del producto',exact=True).select_option('37')
        seller.get_by_label('Talla o tamaño',exact=True).fill('M')
        seller.get_by_label('Color',exact=True).fill('Azul')
        seller.get_by_role('button',name='Agregar variante',exact=True).click()
        seller.get_by_label('Talla de variante 2',exact=True).fill('L')
        seller.get_by_label('Color de variante 2',exact=True).fill('Rojo')
        seller.get_by_label('Stock de variante 2',exact=True).fill('4')
        seller.get_by_label('Foto del producto (opcional)',exact=True).set_input_files(str(Path(__file__).resolve().parents[2]/'frontend/public/brand/tickia-symbol.png'))
        with seller.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/marketplace/products')) as created:
            seller.get_by_role('button',name='Publicar producto',exact=True).click()
        self.assertEqual(created.value.status,201,created.value.text())
        product=created.value.json()
        self.assertEqual(len(product['variantes']),2)
        expect(seller.get_by_text('Producto publicado',exact=True)).to_be_visible()

        other,_=self.context()
        email='other-'+uuid.uuid4().hex+'@example.com'
        self.assertEqual(other.request.post(URL+'/api/auth/register',data=dict(email=email,password='University123!',phone_number='999999999')).status,201)
        self.assertEqual(other.request.post(URL+'/api/auth/login',form=dict(username=email,password='University123!')).status,200)
        second_title='Rúbrica B '+uuid.uuid4().hex[:10]
        second=other.request.post(URL+'/api/marketplace/products',multipart=dict(titulo=second_title,precio='10.00',stock='5',id_categoria='37')).json()

        buyer_context,buyer=self.context(mobile=True)
        modal=self.open_product(buyer,title)
        modal.get_by_role('button',name='Agregar al carrito',exact=True).click()
        modal.get_by_label('Variante',exact=True).select_option(str(product['variantes'][1]['id_variante']))
        modal.get_by_label('Cantidad',exact=True).fill('2')
        modal.get_by_role('button',name='Agregar al carrito',exact=True).click()
        buyer.keyboard.press('Escape')
        modal=self.open_product(buyer,second_title)
        modal.get_by_role('button',name='Agregar al carrito',exact=True).click()
        modal.get_by_role('link',name='Ir al carrito',exact=True).click()
        expect(buyer.get_by_role('heading',name='Tu carrito',exact=True)).to_be_visible()
        expect(buyer.get_by_role('button',name='Carrito (4)',exact=True)).to_be_visible()
        buyer.get_by_role('button',name='Ingresar para confirmar',exact=True).click()
        self.register(buyer,'buyer')
        expect(buyer.get_by_role('heading',name='Tu carrito',exact=True)).to_be_visible()
        coupons=buyer_context.request.get(URL+'/api/marketplace/coupons').json()
        self.assertTrue(coupons)
        districts=buyer_context.request.get(URL+'/api/marketplace/districts').json()
        district=next(d for d in districts if d['departamento']!='Lima')
        buyer.get_by_label('Courier',exact=True).select_option('2')
        buyer.get_by_label('Distrito de entrega',exact=True).select_option(str(district['id_distrito']))
        buyer.get_by_label('Código de cupón (opcional)',exact=True).fill(coupons[0]['codigo'])
        with buyer.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/marketplace/quote') and r.request.post_data_json.get('coupon_code')==coupons[0]['codigo']) as quoted:
            buyer.get_by_role('button',name='Aplicar cupón',exact=True).click()
        quote=quoted.value.json()
        self.assertEqual(quote['subtotal_centimos'],8500)
        self.assertEqual(len(quote['descuentos']),2)
        self.assertGreater(quote['envio_centimos'],0)
        self.assertLessEqual(buyer.evaluate('document.documentElement.scrollWidth'),390)
        buyer.screenshot(path=str(ARTIFACTS/'rubrica-carrito-mobile.png'),full_page=True)
        with buyer.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/marketplace/orders')) as bought:
            buyer.get_by_role('button',name='Confirmar pedido y pago de demostración',exact=True).click()
        self.assertEqual(bought.value.status,201,bought.value.text())
        order=bought.value.json()
        self.assertEqual(len(order['items']),3)
        self.assertEqual(order['total_centimos'],quote['total_centimos'])
        expect(buyer.get_by_role('heading',name='Mis compras',exact=True)).to_be_visible()
        buyer.get_by_role('button',name='Simular despacho',exact=True).click()
        buyer.get_by_role('button',name='Confirmar recepción',exact=True).click()
        expect(buyer.get_by_text('Recibido:',exact=False)).to_be_visible()
        self.assertEqual(buyer_context.request.get(URL+f"/api/marketplace/products/{product['id_producto']}").json()['stock'],6)
        self.assertEqual(buyer_context.request.get(URL+f"/api/marketplace/products/{second['id_producto']}").json()['stock'],4)
        buyer.screenshot(path=str(ARTIFACTS/'rubrica-pedido-mobile.png'),full_page=True)

        modal=self.open_product(buyer,title)
        modal.get_by_role('button',name='Guardar en favoritos',exact=True).click()
        expect(modal.get_by_role('button',name='Quitar de favoritos',exact=True)).to_be_visible()
        modal.get_by_label('Haz una pregunta al vendedor',exact=True).fill('¿La próxima semana tendrán más colores?')
        modal.get_by_role('button',name='Publicar pregunta',exact=True).click()
        expect(modal.get_by_text('¿La próxima semana tendrán más colores?',exact=True)).to_be_visible()
        modal.get_by_label('Calificación',exact=True).select_option('5')
        modal.get_by_label('Cuéntanos tu experiencia',exact=True).fill('Entrega recibida y producto conforme.')
        modal.get_by_role('button',name='Publicar reseña',exact=True).click()
        expect(modal.get_by_text('Ya dejaste tu reseña para este producto.',exact=True)).to_be_visible()
        owner_modal=self.open_product(seller,title)
        owner_modal.get_by_label('Tu respuesta',exact=True).fill('Sí, tendremos verde la próxima semana.')
        owner_modal.get_by_role('button',name='Publicar respuesta',exact=True).click()
        expect(owner_modal.get_by_text('Sí, tendremos verde la próxima semana.',exact=True)).to_be_visible()
        buyer.keyboard.press('Escape')
        buyer.get_by_role('button',name='Favoritos',exact=True).click()
        expect(buyer.locator('.ticket-card')).to_have_count(1)
        buyer.get_by_role('button',name='Comprar '+title,exact=True).click()
        expect(buyer.get_by_role('dialog').get_by_text('Sí, tendremos verde la próxima semana.',exact=True)).to_be_visible()
        buyer.keyboard.press('Escape')
        buyer.get_by_role('button',name='Análisis',exact=True).click()
        expect(buyer.get_by_role('heading',name='Análisis del marketplace',exact=True)).to_be_visible()
        try:
            expect(buyer.locator('.analysis-table-scroll tbody tr')).to_have_count(14,timeout=120000)
        except AssertionError:
            buyer.screenshot(path=str(ARTIFACTS/'rubrica-error-analisis.png'),full_page=True)
            self.fail('No se cargó el diagnóstico: '+buyer.locator('main').inner_text()+'; errores JS: '+str(self.errors))
        self.assertLessEqual(buyer.evaluate('document.documentElement.scrollWidth'),390)
        buyer.screenshot(path=str(ARTIFACTS/'rubrica-analisis-mobile.png'),full_page=True)
        buyer.get_by_label('Análisis a consultar',exact=True).select_option('rfm')
        expect(buyer.get_by_label('Gráfico de resultados')).to_be_visible(timeout=60000)
        with buyer.expect_download() as downloaded:
            buyer.get_by_role('link',name='Descargar CSV completo',exact=True).click()
        contents=Path(downloaded.value.path()).read_text(encoding='utf-8-sig')
        self.assertEqual(len(list(csv.DictReader(io.StringIO(contents)))),45000)
        buyer.get_by_label('Análisis a consultar',exact=True).select_option('cohortes')
        expect(buyer.get_by_label('Gráfico de resultados')).to_be_visible()
        buyer.set_viewport_size({'width':1440,'height':1000})
        buyer.get_by_label('Análisis a consultar',exact=True).select_option('vendedores')
        expect(buyer.get_by_role('img',name=re.compile('Cada punto'))).to_be_visible()
        buyer.screenshot(path=str(ARTIFACTS/'rubrica-analisis-desktop.png'),full_page=True)
        self.assertEqual(self.errors,[])
        self.assertEqual(self.external,[])
