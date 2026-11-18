"""Contratos adicionales de la rúbrica, contra MySQL real y aislado."""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).parents[2]))
ENABLED=os.getenv('TICKIA_TEST_MYSQL')=='1'
if ENABLED:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from backend.academic.database import engine,make_engine,row,rows
    from backend.academic.bootstrap import initialize


@unittest.skipUnless(ENABLED,'Requiere MySQL aislado: TICKIA_TEST_MYSQL=1')
class AcademicRequirementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=make_engine(engine.url.set(database='tickia_universidad_test'))
        initialize(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_normalized_geography_reconstructs_every_original_district(self):
        import csv
        from backend.academic.settings import SOURCE_DIR
        with (SOURCE_DIR/'01_distritos.csv').open(encoding='utf-8-sig',newline='') as stream:
            original=list(csv.DictReader(stream))
        with self.engine.connect() as db:
            self.assertEqual(row(db,"SELECT COUNT(*) n FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'")['n'],17)
            columns={r['COLUMN_NAME'] for r in rows(db,"SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='distritos'")}
            self.assertNotIn('provincia',columns)
            self.assertNotIn('departamento',columns)
            current=rows(db,'SELECT id_distrito,nombre,provincia,departamento FROM v_distritos ORDER BY id_distrito')
            self.assertEqual([{**r,'id_distrito':int(r['id_distrito'])} for r in original],current)
            order_columns={r['COLUMN_NAME'] for r in rows(db,"SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='pedidos'")}
            self.assertFalse({'subtotal','descuento','costo_envio','destino'}&order_columns)
            self.assertIn('id_distrito_entrega',order_columns)

    def test_views_trigger_bridge_keys_and_facts_exist(self):
        with self.engine.connect() as db:
            self.assertGreaterEqual(row(db,'SELECT COUNT(*) n FROM information_schema.VIEWS WHERE TABLE_SCHEMA=DATABASE()')['n'],2)
            self.assertTrue(row(db,"SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME='tr_pedido_validar_estado'"))
            self.assertGreaterEqual(row(db,"SELECT COUNT(*) n FROM pedidos WHERE origen='dataset'")['n'],10000)
            for table in ('pedido_detalle','favoritos'):
                keys=rows(db,"SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:table AND CONSTRAINT_NAME='PRIMARY'",{'table':table})
                self.assertEqual(len(keys),2)

    def test_window_queries_have_correct_partition_boundaries_and_accumulations(self):
        from backend.academic.analytics import sql_queries
        queries=sql_queries()
        with self.engine.connect() as db:
            ranking=rows(db,queries['ranking_vendedores'])
            self.assertEqual(ranking[0]['posicion'],1)
            self.assertEqual(ranking[-1]['ventas_acumuladas'],sum(r['ventas_brutas'] for r in ranking))
            history=rows(db,queries['ventas_mensuales'])
            previous={}
            for record in history:
                vendor=record['id_vendedor']
                self.assertEqual(record['ventas_mes_anterior'],previous.get(vendor))
                previous[vendor]=record['ventas_brutas']
            self.assertGreaterEqual(len(queries),9)
            for name in ('ventas_distrito','stock','resenas_producto','favoritos_categoria','entregas_departamento'):
                with self.subTest(query=name):
                    self.assertGreaterEqual(queries[name].upper().count('JOIN '),2)
                    self.assertTrue(db.execute(text(queries[name])).fetchmany(1))

    def test_trigger_rejects_skipped_state_even_for_direct_sql(self):
        with self.engine.connect() as db:
            identifier=row(db,"SELECT id_pedido FROM pedidos WHERE estado='pagado' ORDER BY id_pedido LIMIT 1")['id_pedido']
        with self.engine.connect() as db:
            transaction=db.begin()
            try:
                with self.assertRaises(DBAPIError):
                    db.execute(text("UPDATE pedidos SET estado='entregado' WHERE id_pedido=:id"),{'id':identifier})
            finally:
                transaction.rollback()
        with self.engine.connect() as db:
            self.assertEqual(row(db,'SELECT estado FROM pedidos WHERE id_pedido=:id',{'id':identifier})['estado'],'pagado')
