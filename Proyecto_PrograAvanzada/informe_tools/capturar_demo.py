"""Capturas verificables de la instancia aislada preparada para la entrega."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'Proyecto_PrograAvanzada/entregables/informe/figuras'
LOCAL=ROOT/'Proyecto_PrograAvanzada/.local/informe-build'
URL='http://127.0.0.1:5202'
PASSWORD='TickiaDemo2026!'
PEOPLE=[('vendedor.campus@example.com','Tienda Campus'),('papeleria.demo@example.com','Papelería Universitaria'),('comprador.demo@example.com','Comprador de demostración')]
TITLE='Mochila Campus Tickia — demostración'
SECOND='Cuaderno universitario Tickia — demostración'


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch()
        contexts=[];pages=[];errors=[]
        for email,name in PEOPLE:
            context=browser.new_context(viewport={'width':1280,'height':900},device_scale_factor=1.5)
            contexts.append(context);page=context.new_page();pages.append(page)
            page.on('pageerror',lambda error:errors.append(str(error)))
            created=context.request.post(URL+'/api/auth/register',data=dict(email=email,password=PASSWORD,phone_number='999999999',full_name=name))
            assert created.status in (201,400),created.text()
            logged=context.request.post(URL+'/api/auth/login',form=dict(username=email,password=PASSWORD))
            assert logged.status==200,logged.text()
        seller,stationer,buyer=pages
        anonymous=browser.new_context(viewport={'width':1120,'height':800},device_scale_factor=1.5)
        login=anonymous.new_page();login.goto(URL+'/#login')
        login.get_by_label('Correo electrónico',exact=True).fill(PEOPLE[2][0])
        login.get_by_label('Contraseña',exact=True).fill(PASSWORD)
        login.screenshot(path=str(OUT/'02_acceso.png'))
        anonymous.close()

        seller.goto(URL+'/#seller')
        expect(seller.get_by_role('heading',name='Publicar un producto',exact=True)).to_be_visible()
        existing=contexts[0].request.get(URL+'/api/marketplace/products',params={'q':TITLE}).json()['items']
        if not existing:
            seller.get_by_label('Nombre del producto',exact=True).fill(TITLE)
            seller.get_by_label('Descripción',exact=True).fill('Mochila para clases y actividades del campus. Publicación ficticia para la demostración académica.')
            seller.get_by_label('Precio (S/)',exact=True).fill('89.90')
            seller.get_by_label('Stock disponible',exact=True).fill('5')
            seller.get_by_label('Categoría del producto',exact=True).select_option('110')
            seller.get_by_label('Talla o tamaño',exact=True).fill('Mediana')
            seller.get_by_label('Color',exact=True).fill('Azul')
            seller.get_by_role('button',name='Agregar variante',exact=True).click()
            seller.get_by_label('Talla de variante 2',exact=True).fill('Grande')
            seller.get_by_label('Color de variante 2',exact=True).fill('Gris')
            seller.get_by_label('Stock de variante 2',exact=True).fill('4')
            seller.locator('form').first.screenshot(path=str(OUT/'03_publicacion.png'))
            with seller.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/marketplace/products')) as result:
                seller.get_by_role('button',name='Publicar producto',exact=True).click()
            assert result.value.status==201,result.value.text()
            product=result.value.json()
        else:
            product=contexts[0].request.get(URL+f"/api/marketplace/products/{existing[0]['id_producto']}").json()
        existing=contexts[1].request.get(URL+'/api/marketplace/products',params={'q':SECOND}).json()['items']
        if not existing:
            response=contexts[1].request.post(URL+'/api/marketplace/products',multipart=dict(titulo=SECOND,precio='12.50',stock='8',id_categoria='107',descripcion='Cuaderno ficticio para demostrar una compra a otro vendedor.',talla='A4',color='Verde'))
            assert response.status==201,response.text()
            second=response.json()
        else:second=contexts[1].request.get(URL+f"/api/marketplace/products/{existing[0]['id_producto']}").json()

        buyer.goto(URL+'/#catalog')
        expect(buyer.locator('.ticket-card')).to_have_count(24)
        buyer.get_by_role('heading',name='Catálogo de productos',exact=True).scroll_into_view_if_needed()
        buyer.screenshot(path=str(OUT/'01_catalogo.png'))
        orders=contexts[2].request.get(URL+'/api/marketplace/orders').json()['items']
        demo_order=next((order for order in orders if any(item['id_producto']==product['id_producto'] for item in order['items'])),None)
        previous_metadata=LOCAL/'demo.json'
        quote=json.loads(previous_metadata.read_text(encoding='utf-8')).get('quote') if previous_metadata.is_file() else None
        if demo_order is None:
            buyer.get_by_role('searchbox').fill(TITLE)
            buyer.get_by_role('button',name='Comprar '+TITLE,exact=True).click()
            modal=buyer.get_by_role('dialog')
            expect(modal.get_by_role('heading',name=TITLE,exact=True)).to_be_visible()
            modal.screenshot(path=str(OUT/'04_detalle_variantes.png'))
            modal.get_by_label('Cantidad',exact=True).fill('2')
            modal.get_by_role('button',name='Agregar al carrito',exact=True).click()
            modal.get_by_label('Variante',exact=True).select_option(str(product['variantes'][1]['id_variante']))
            modal.get_by_label('Cantidad',exact=True).fill('1')
            modal.get_by_role('button',name='Agregar al carrito',exact=True).click()
            buyer.keyboard.press('Escape')
            buyer.get_by_role('searchbox').fill(SECOND)
            buyer.get_by_role('button',name='Comprar '+SECOND,exact=True).click()
            buyer.get_by_role('dialog').get_by_role('button',name='Agregar al carrito',exact=True).click()
            buyer.keyboard.press('Escape')
            buyer.get_by_role('button',name='Carrito (4)',exact=True).click()
            expect(buyer.get_by_role('heading',name='Tu carrito',exact=True)).to_be_visible()
            buyer.get_by_label('Courier',exact=True).select_option('2')
            districts=contexts[2].request.get(URL+'/api/marketplace/districts').json()
            district=next(d for d in districts if d['departamento']=='Cusco')
            buyer.get_by_label('Distrito de entrega',exact=True).select_option(str(district['id_distrito']))
            coupons=contexts[2].request.get(URL+'/api/marketplace/coupons').json()
            buyer.get_by_label('Código de cupón (opcional)',exact=True).fill(coupons[0]['codigo'])
            with buyer.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/marketplace/quote') and r.request.post_data_json.get('coupon_code')==coupons[0]['codigo']) as priced:
                buyer.get_by_role('button',name='Aplicar cupón',exact=True).click()
            quote=priced.value.json()
            buyer.get_by_role('heading',name='Tu carrito',exact=True).scroll_into_view_if_needed()
            buyer.screenshot(path=str(OUT/'05_carrito.png'))
            buyer.locator('.cart-summary').screenshot(path=str(OUT/'06_resumen_pago.png'))
            with buyer.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/marketplace/orders')) as confirmed:
                buyer.get_by_role('button',name='Confirmar pedido y pago de demostración',exact=True).click()
            assert confirmed.value.status==201,confirmed.value.text()
            demo_order=confirmed.value.json()
        buyer.goto(URL+'/#wallet')
        expect(buyer.get_by_role('heading',name='Mis compras',exact=True)).to_be_visible()
        if demo_order['estado']=='pagado':
            buyer.screenshot(path=str(OUT/'07_compra_pagada.png'))
            buyer.get_by_role('button',name='Simular despacho',exact=True).click()
            expect(buyer.get_by_role('button',name='Confirmar recepción',exact=True)).to_be_visible()
            buyer.screenshot(path=str(OUT/'08_despacho.png'))
            buyer.get_by_role('button',name='Confirmar recepción',exact=True).click()
        expect(buyer.get_by_text('Recibido:',exact=False)).to_be_visible()
        buyer.screenshot(path=str(OUT/'09_recepcion.png'))

        buyer.goto(URL+'/#catalog');buyer.get_by_role('searchbox').fill(TITLE)
        buyer.get_by_role('button',name='Comprar '+TITLE,exact=True).click();modal=buyer.get_by_role('dialog')
        expect(modal.locator('.product-community')).to_be_visible()
        if modal.get_by_role('button',name='Guardar en favoritos',exact=True).count():
            modal.get_by_role('button',name='Guardar en favoritos',exact=True).click()
            expect(modal.get_by_role('button',name='Quitar de favoritos',exact=True)).to_be_visible()
        question='¿La mochila incluye un compartimento para laptop?'
        if not modal.get_by_text(question,exact=True).count():
            modal.get_by_label('Haz una pregunta al vendedor',exact=True).fill(question)
            modal.get_by_role('button',name='Publicar pregunta',exact=True).click()
            expect(modal.get_by_text(question,exact=True)).to_be_visible()
        if modal.get_by_label('Cuéntanos tu experiencia',exact=True).count():
            modal.get_by_label('Cuéntanos tu experiencia',exact=True).fill('Producto recibido en la demostración. Variantes, descuento y seguimiento funcionaron correctamente.')
            modal.get_by_role('button',name='Publicar reseña',exact=True).click()
            expect(modal.get_by_text('Ya dejaste tu reseña para este producto.',exact=True)).to_be_visible()
        modal.locator('.product-community').screenshot(path=str(OUT/'10_comunidad.png'))
        seller.goto(URL+'/#catalog');seller.get_by_role('searchbox').fill(TITLE)
        seller.get_by_role('button',name='Comprar '+TITLE,exact=True).click()
        owned=seller.get_by_role('dialog')
        expect(owned.locator('.product-community')).to_be_visible()
        if owned.get_by_label('Tu respuesta',exact=True).count():
            owned.get_by_label('Tu respuesta',exact=True).fill('Sí, este modelo de demostración incluye un compartimento para laptop.')
            owned.get_by_role('button',name='Publicar respuesta',exact=True).click()
            expect(owned.get_by_text('Sí, este modelo de demostración incluye un compartimento para laptop.',exact=True)).to_be_visible()
        owned.locator('.product-community').screenshot(path=str(OUT/'11_respuesta_vendedor.png'))
        buyer.keyboard.press('Escape');buyer.goto(URL+'/#analytics')
        expect(buyer.locator('.analysis-table-scroll tbody tr')).to_have_count(14,timeout=120000)
        buyer.screenshot(path=str(OUT/'12_diagnostico.png'))
        buyer.get_by_label('Análisis a consultar',exact=True).select_option('rfm')
        expect(buyer.get_by_label('Gráfico de resultados')).to_be_visible(timeout=120000)
        buyer.screenshot(path=str(OUT/'13_rfm_aplicacion.png'))
        buyer.get_by_label('Análisis a consultar',exact=True).select_option('riesgo_courier')
        expect(buyer.locator('.analysis-table-scroll tbody tr')).to_have_count(25,timeout=120000)
        buyer.set_viewport_size({'width':390,'height':844})
        assert buyer.evaluate('document.documentElement.scrollWidth')<=390
        buyer.screenshot(path=str(OUT/'14_movil.png'))
        assert not errors,errors
        metadata=dict(url=URL,database='tickia_universidad_clean_test',product_id=product['id_producto'],second_product_id=second['id_producto'],order_id=demo_order['id'],quote=quote,
            order=contexts[2].request.get(URL+'/api/marketplace/orders/'+demo_order['id']).json(),accounts=[dict(email=email,name=name) for email,name in PEOPLE],password=PASSWORD,errors=errors)
        (LOCAL/'demo.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Capturas reales completadas; pedido de demostración',demo_order['id'])
        browser.close()


if __name__=='__main__':run()
