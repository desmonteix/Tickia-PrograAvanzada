"""Integración real de MySQL. TICKIA_TEST_MYSQL=1; usa solamente tickia_universidad_test."""
import os
from pathlib import Path
import sys
import unittest
import uuid
import json
import hashlib
import sqlite3
import tempfile
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0,str(Path(__file__).parents[2]))
ENABLED = os.getenv('TICKIA_TEST_MYSQL')=='1'
if ENABLED:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import text
    import pymysql
    from backend.academic import auth,catalog,commerce,social
    from backend.academic.database import engine,make_engine,get_db,row
    from backend.academic.bootstrap import initialize
    from backend.auth_utils import create_access_token


@unittest.skipUnless(ENABLED,'Requiere MySQL de prueba: TICKIA_TEST_MYSQL=1')
class AcademicMySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = make_engine(engine.url.set(database='tickia_universidad_test'))
        initialize(cls.engine)
        cls.app = FastAPI()
        for router in (auth.router,catalog.router,commerce.router,social.router):
            cls.app.include_router(router)
        def connection():
            with cls.engine.begin() as db:
                yield db
        cls.app.dependency_overrides[get_db]=connection
        cls.engine_patch=patch.object(commerce,'engine',cls.engine)
        cls.engine_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.engine_patch.stop()
        cls.engine.dispose()

    def setUp(self):
        self.client=TestClient(self.app)
        self.addCleanup(self.client.close)
        self.people=[]
        for role in ('buyer','seller','other'):
            response=self.client.post('/api/auth/register',json=dict(email=role+'-'+uuid.uuid4().hex+'@example.com',password='University123!',phone_number='999999999'))
            self.assertEqual(response.status_code,201,response.text)
            self.people.append(response.json())
        published=self.client.post('/api/marketplace/products',headers=self.headers(1),data=dict(
            titulo='Lámpara de prueba '+uuid.uuid4().hex[:8],precio='25.00',stock='3',id_categoria='37',
            variantes_json=json.dumps([dict(talla='M',color='Azul',stock=3),dict(talla='L',color='Rojo',stock=2)])))
        self.assertEqual(published.status_code,201,published.text)
        self.product=published.json()
        self.variants=[v['id_variante'] for v in self.product['variantes']]

    def headers(self,index=0):
        return {'Authorization':'Bearer '+create_access_token({'user_id':self.people[index]['id']})}

    def payload(self,items=None,**kwargs):
        return dict(items=items or [dict(variant_id=self.variants[0],quantity=1)],courier_id=1,district_id=1,
                    payment_method='yape_demo',**kwargs)

    def buy(self,index=0,**kwargs):
        data=self.payload(**kwargs)
        bill=self.client.post('/api/marketplace/quote',json=data,headers=self.headers(index))
        self.assertEqual(bill.status_code,200,bill.text)
        data.update(request_id=str(uuid.uuid4()),expected_total_centimos=bill.json()['total_centimos'])
        result=self.client.post('/api/marketplace/orders',json=data,headers=self.headers(index))
        return result,data,bill.json()

    def test_schema_and_all_fifteen_source_tables(self):
        with self.engine.connect() as db:
            self.assertEqual(row(db,'SELECT COUNT(*) n FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()')['n'],15)
            self.assertEqual(row(db,'SELECT COUNT(*) n FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE()')['n'],19)
            self.assertGreaterEqual(row(db,'SELECT COUNT(*) n FROM pagos')['n'],111528)
            self.assertGreaterEqual(row(db,'SELECT COUNT(*) n FROM favoritos')['n'],79970)
            self.assertTrue(row(db,"SELECT ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=DATABASE() AND ROUTINE_NAME='confirmar_pedido'"))

    def test_multi_item_coupon_decorators_and_idempotent_confirmation(self):
        code='TEST-'+uuid.uuid4().hex
        with self.engine.begin() as db:
            db.execute(text("INSERT INTO cupones(codigo,descuento_pct,vence) VALUES(:code,10,'2099-12-31')"),{'code':code})
        result,data,bill=self.buy(items=[dict(variant_id=self.variants[0],quantity=2),dict(variant_id=self.variants[1],quantity=1)],coupon_code=code)
        self.assertEqual(result.status_code,201,result.text)
        self.assertEqual(bill['subtotal_centimos'],7500)
        self.assertEqual(len(bill['descuentos']),2)
        self.assertEqual(bill['total_centimos'],7747)
        order=result.json()
        self.assertEqual(order['estado'],'pagado')
        self.assertEqual(len(order['items']),2)
        self.assertEqual(order['pagos'][0]['estado'],'aprobado')
        repeat=self.client.post('/api/marketplace/orders',json=data,headers=self.headers())
        self.assertEqual(repeat.status_code,201,repeat.text)
        self.assertEqual(repeat.json()['id'],order['id'])
        current=self.client.get('/api/marketplace/products/'+str(self.product['id_producto'])).json()
        self.assertEqual([variant['stock'] for variant in current['variantes']],[1,1])
        data['items'][0]['quantity']=1
        self.assertEqual(self.client.post('/api/marketplace/orders',json=data,headers=self.headers()).status_code,409)

    def test_state_shipping_receipt_reviews_questions_and_favorites(self):
        product_id=self.product['id_producto']
        review=dict(estrellas=5,comentario='Buen producto y entrega.')
        self.assertEqual(self.client.post(f'/api/marketplace/products/{product_id}/reviews',json=review,headers=self.headers()).status_code,403)
        bought,_,_=self.buy()
        self.assertEqual(bought.status_code,201,bought.text)
        order_id=bought.json()['id']
        endpoint=f'/api/marketplace/orders/{order_id}/status'
        self.assertEqual(self.client.post(endpoint,json={'next_state':'entregado'},headers=self.headers()).status_code,409)
        self.assertEqual(self.client.get('/api/marketplace/orders/'+order_id,headers=self.headers(2)).status_code,404)
        shipped=self.client.post(endpoint,json={'next_state':'enviado'},headers=self.headers(1))
        self.assertEqual(shipped.status_code,200,shipped.text)
        self.assertTrue(shipped.json()['envios'][0]['fecha_envio'])
        self.assertEqual(self.client.post(endpoint,json={'next_state':'entregado'},headers=self.headers(1)).status_code,403)
        received=self.client.post(endpoint,json={'next_state':'entregado'},headers=self.headers())
        self.assertEqual(received.json()['estado'],'entregado')
        self.assertEqual(self.client.post(f'/api/marketplace/products/{product_id}/reviews',json=review,headers=self.headers()).status_code,201)
        self.assertEqual(self.client.post(f'/api/marketplace/products/{product_id}/reviews',json=review,headers=self.headers()).status_code,409)
        question=self.client.post(f'/api/marketplace/products/{product_id}/questions',json={'texto':'¿Tienen otro color?'},headers=self.headers()).json()
        answer_url='/api/marketplace/questions/'+str(question['id_pregunta'])+'/answer'
        self.assertEqual(self.client.put(answer_url,json={'texto':'Sí, tenemos varios.'},headers=self.headers(2)).status_code,404)
        self.assertEqual(self.client.put(answer_url,json={'texto':'Sí, tenemos varios.'},headers=self.headers(1)).status_code,200)
        favorite_url=f'/api/marketplace/products/{product_id}/favorite'
        for _ in range(2):
            self.assertEqual(self.client.put(favorite_url,json={'enabled':True},headers=self.headers()).status_code,200)
        self.assertEqual(self.client.get('/api/marketplace/products?favorites=true',headers=self.headers()).json()['total'],1)
        self.client.put(favorite_url,json={'enabled':False},headers=self.headers())
        self.assertEqual(self.client.get('/api/marketplace/products?favorites=true',headers=self.headers()).json()['total'],0)

    def test_stored_procedure_rolls_back_every_variant_if_one_has_insufficient_stock(self):
        connection=self.engine.raw_connection()
        try:
            with connection.cursor() as cursor:
                with self.assertRaises(pymysql.MySQLError):
                    cursor.execute('CALL confirmar_pedido(%s,%s,%s,%s,NULL,1,1,%s,109.00)',
                        (self.people[0]['id_usuario'],str(uuid.uuid4()),'0'*64,
                         json.dumps([dict(variant_id=self.variants[0],quantity=1),dict(variant_id=self.variants[1],quantity=3)]),'yape_demo'))
            connection.rollback()
        finally:
            connection.close()
        with self.engine.connect() as db:
            self.assertEqual(row(db,'SELECT stock FROM variantes WHERE id_variante=:id',{'id':self.variants[0]})['stock'],3)
            self.assertEqual(row(db,'SELECT stock FROM variantes WHERE id_variante=:id',{'id':self.variants[1]})['stock'],2)

    def test_two_buyers_cannot_purchase_the_last_unit(self):
        with self.engine.begin() as db:
            db.execute(text('UPDATE variantes SET stock=1 WHERE id_variante=:id'),{'id':self.variants[0]})
        data=self.payload()
        quote=self.client.post('/api/marketplace/quote',json=data,headers=self.headers()).json()
        def purchase(index):
            payload=dict(data,request_id=str(uuid.uuid4()),expected_total_centimos=quote['total_centimos'])
            return self.client.post('/api/marketplace/orders',json=payload,headers=self.headers(index)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(purchase,(0,2))),[201,409])

    def test_legacy_migration_preserves_accounts_orders_stock_and_source_file(self):
        from backend.academic.migration import migrate_legacy
        from backend.auth_utils import get_password_hash, verify_password
        seller, buyer = str(uuid.uuid4()), str(uuid.uuid4())
        request = str(uuid.uuid4())
        password = get_password_hash('Migration123!')
        with self.engine.connect() as db:
            product_id = row(db,'SELECT MAX(id_producto)+1000 n FROM productos')['n']
            variant_id = row(db,'SELECT MAX(id_variante)+1000 n FROM variantes')['n']
        with tempfile.TemporaryDirectory(prefix='tickia-migration-') as directory:
            source, marker = Path(directory)/'legacy.sqlite3', Path(directory)/'marker.json'
            with sqlite3.connect(source) as old:
                old.executescript('''
                    CREATE TABLE users(id TEXT, email TEXT, full_name TEXT, hashed_password TEXT, phone_number TEXT, is_admin INT, is_suspended INT, banned_until TEXT);
                    CREATE TABLE local_products(id_producto INT, source_product_id INT, owner_id TEXT, vendedor TEXT, reputacion REAL, id_categoria INT, titulo TEXT, precio_centimos INT, descripcion TEXT, imagen TEXT);
                    CREATE TABLE local_variants(id_variante INT, id_producto INT, talla TEXT, color TEXT, stock INT);
                    CREATE TABLE local_orders(id TEXT, buyer_id TEXT, request_id TEXT, created_at TEXT, total_centimos INT, id_variante INT, cantidad INT, precio_unit_centimos INT);
                ''')
                for identifier in (seller,buyer):
                    old.execute('INSERT INTO users VALUES(?,?,?,?,?,0,0,NULL)',(identifier,identifier+'@example.com','Cuenta migrada',password,'999999999'))
                old.execute('INSERT INTO local_products VALUES(?,NULL,?,?,5,37,?,2500,?,NULL)',(product_id,seller,'Tienda migrada','Producto migrado '+seller,'Antes de MySQL'))
                old.execute('INSERT INTO local_variants VALUES(?,?,?,?,?)',(variant_id,product_id,'M','Azul',2))
                old.execute('INSERT INTO local_orders VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),buyer,request,'2026-11-17 12:00:00',2500,variant_id,1,2500))
            old.close()
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            counts = migrate_legacy(self.engine,source,marker)
            self.assertEqual(counts,dict(users=2,products=1,orders=1))
            with self.engine.begin() as db:
                account = row(db,'SELECT * FROM usuarios WHERE auth_uuid=:id',{'id':buyer})
                self.assertTrue(verify_password('Migration123!',account['password_hash']))
                order = row(db,'SELECT id_pedido,total,estado FROM pedidos WHERE solicitud_uuid=:id',{'id':request})
                self.assertEqual(str(order['total']),'25.00')
                self.assertEqual(order['estado'],'pagado')
                self.assertEqual(row(db,'SELECT stock FROM variantes WHERE id_variante=:id',{'id':variant_id})['stock'],2)
                db.execute(text('UPDATE variantes SET stock=1 WHERE id_variante=:id'),{'id':variant_id})
            self.assertEqual(migrate_legacy(self.engine,source,marker),counts)
            with self.engine.connect() as db:
                self.assertEqual(row(db,'SELECT stock FROM variantes WHERE id_variante=:id',{'id':variant_id})['stock'],1)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),digest)

    def test_required_sql_queries_execute_against_real_mysql(self):
        from backend.academic.analytics import sql_queries
        with self.engine.connect() as db:
            for name,query in sql_queries().items():
                with self.subTest(query=name):
                    self.assertTrue(db.execute(text(query)).fetchmany(1))
