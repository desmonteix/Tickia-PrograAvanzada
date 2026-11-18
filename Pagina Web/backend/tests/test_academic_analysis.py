"""Los análisis se verifican con datos pequeños de resultado conocido."""
import sys
from pathlib import Path
import unittest
import pandas as pd

sys.path.insert(0,str(Path(__file__).parents[2]))
from backend.academic.analysis_frames import rfm,cohorts,co_purchases,delivery_summary,vendor_summary,stars_vs_sales


class AcademicAnalysisTests(unittest.TestCase):
    def test_rfm_counts_orders_without_multiplying_line_items_and_includes_nonbuyers(self):
        orders=pd.DataFrame(dict(id_pedido=[1,2,3],id_usuario=[1,1,2],fecha=pd.to_datetime(['2026-01-01','2026-02-01','2026-01-01']),total_centimos=[1000,2500,500]))
        result,reference=rfm(orders,pd.DataFrame({'id_usuario':[1,2,3]}))
        buyer=result.set_index('id_usuario').loc[1]
        self.assertEqual(buyer.frecuencia,2)
        self.assertEqual(buyer.monetario,35)
        self.assertEqual(reference,pd.Timestamp('2026-02-02'))
        self.assertEqual(result.set_index('id_usuario').loc[3,'segmento'],'Sin compras')

    def test_cohorts_use_unique_customers_and_include_observed_zero_retention(self):
        orders=pd.DataFrame(dict(id_pedido=[1,2,3,4,5],id_usuario=[1,1,2,3,3],fecha=pd.to_datetime(['2026-01-01','2026-02-01','2026-01-02','2026-02-05','2026-03-01'])))
        result=cohorts(orders).set_index(['cohorte','mes'])
        self.assertEqual(result.loc[('2026-01',1),'retencion_pct'],50)
        self.assertEqual(result.loc[('2026-01',2),'retencion_pct'],0)
        self.assertNotIn(('2026-03',1),result.index)

    def test_copurchases_deduplicate_the_same_product_in_an_order(self):
        items=pd.DataFrame(dict(id_pedido=[1,1,1,2,2],id_producto=[1,1,2,1,2],titulo=['A','A','B','A','B']))
        result=co_purchases(items)
        self.assertEqual(len(result),1)
        self.assertEqual(result.iloc[0].pedidos_juntos,2)
        self.assertEqual(result.iloc[0].soporte_pct,100)
        self.assertEqual(result.iloc[0].confianza_a_b_pct,100)

    def test_same_day_delivery_is_not_late_and_invalid_intervals_are_excluded(self):
        shipments=pd.DataFrame(dict(id_envio=[1,2,3],id_pedido=[1,2,3],courier=['A']*3,departamento=['Lima']*3,
            fecha_envio=['2026-01-01']*3,fecha_entrega=['2026-01-02 23:00','2026-01-03','2025-12-31'],fecha_estimada=['2026-01-02']*3))
        result=delivery_summary(shipments).iloc[0]
        self.assertEqual(result.envios,2)
        self.assertEqual(result.retraso_pct,50)

    def test_stars_vs_sales_groups_products_by_rating_and_correlates_by_rank(self):
        items=pd.DataFrame(dict(id_pedido=[1,2,3,3,4],id_producto=[1,2,3,1,4],id_vendedor=[1,1,2,2,2],
                                cantidad=[1,2,3,1,4],precio_unit_centimos=[1000]*5))
        reviews=pd.DataFrame(dict(id_resena=[1,2,3,4,5],id_producto=[1,2,3,4,4],estrellas=[5,4,3,2,4]))
        vendors=pd.DataFrame(dict(pedidos=[10,12,15,3],estrellas_promedio=[4.0,3.0,2.0,5.0],
                                  ventas_brutas=[100.0,200.0,300.0,999.0]))
        products,bands,summary=stars_vs_sales(items,reviews,vendors,min_reviews=1)
        self.assertEqual(summary['productos'],4)
        self.assertEqual(products.set_index('id_producto').loc[1,'unidades'],2)
        self.assertEqual(products.set_index('id_producto').loc[1,'ventas_brutas'],20)
        self.assertEqual(bands.set_index('tramo_estrellas').loc['3,0–3,5','productos'],2)
        self.assertAlmostEqual(bands.participacion_ventas_pct.sum(),100,places=1)
        self.assertEqual(summary['vendedores'],3)          # el de 3 pedidos no es elegible
        self.assertEqual(summary['spearman_vendedor_estrellas_ventas'],-1.0)

    def test_vendor_reviews_and_sales_are_aggregated_separately(self):
        items=pd.DataFrame(dict(id_pedido=[1,1],id_producto=[1,2],id_vendedor=[1,1],cantidad=[2,1],precio_unit_centimos=[1000,2000]))
        reviews=pd.DataFrame(dict(id_vendedor=[1,1],id_resena=[1,2],estrellas=[1,5]))
        shipments=pd.DataFrame(dict(id_envio=[1],id_pedido=[1],fecha_envio=['2026-01-01'],fecha_entrega=['2026-01-03'],fecha_estimada=['2026-01-02']))
        vendors=pd.DataFrame(dict(id_vendedor=[1],razon_social=['Tienda']))
        result=vendor_summary(items,reviews,shipments,vendors).iloc[0]
        self.assertEqual(result.ventas_brutas,40)
        self.assertEqual(result.resenas,2)
        self.assertEqual(result.estrellas_promedio,3)
        self.assertEqual(result.pedidos,1)
        self.assertEqual(result.retraso_pct,100)
