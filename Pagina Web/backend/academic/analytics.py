"""Análisis reproducibles de MySQL con Pandas, con exportación completa a CSV."""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
from threading import Lock
import time
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text
from .database import engine
from .settings import SQL_DIR
from ..dataset import LOCAL_DIR
from .analysis_frames import rfm,cohorts,co_purchases,delivery_summary,vendor_summary,diagnose,clean_shipments

router=APIRouter(prefix='/api/analytics',tags=['Pandas y consultas SQL'])
_cache={}
_lock=Lock()
NOTES={
 'rfm':'RFM por cliente. Recencia respecto al día posterior a la última compra del dataset; frecuencia = pedidos distintos; monetario = total de sus pedidos válidos. Incluye clientes sin compras.',
 'cohortes':'Cohorte de primera compra, no de registro. Retención por clientes únicos; se incluyen ceros observados y se excluyen meses futuros sin exposición.',
 'cocompras':'Cada producto cuenta una sola vez por pedido. Soporte y confianza se calculan sobre pedidos, no unidades; lift compara con la compra independiente.',
 'entregas':'Solo envíos con fechas válidas. Entregar el mismo día prometido es puntual. La tasa de retrasos excluye promesas desconocidas; se muestra su denominador.',
 'vendedores':'Ventas brutas de artículos antes de cupones y sin envío. Reseñas y puntualidad se agregan separadamente para evitar multiplicar importes. La demora pertenece al pedido consolidado.',
 'diagnostico':'Ventas altas = cuartil superior entre vendedores con al menos 10 pedidos; estrellas < 3.5 y retrasos >= 25%. Asociación a nivel vendedor: las reseñas no identifican un pedido y no prueban causalidad.',
 'ventas_distrito':'JOIN de seis tablas. Ventas brutas por vendedor y distrito del cliente; el dataset no identifica otra dirección histórica de entrega.',
 'stock':'Inventario actual con 0 a 3 unidades por variante, incluyendo productos publicados en la plataforma.',
 'categorias':'Árbol completo obtenido con WITH RECURSIVE, mostrando nivel y ruta de cada categoría.',
}


def sql_queries():
    chunks=re.split(r'^-- name: ([a-z_]+)\s*$',(SQL_DIR/'03_consultas.sql').read_text(encoding='utf-8'),flags=re.MULTILINE)
    return {chunks[i]:chunks[i+1].strip().rstrip(';') for i in range(1,len(chunks),2)}


def load_frames(connection):
    valid="pe.origen='dataset' AND pe.estado IN ('pagado','enviado','entregado')"
    orders=pd.read_sql_query(text('SELECT pe.id_pedido,pe.id_usuario,pe.fecha,CAST(ROUND(pe.total*100) AS SIGNED) total_centimos FROM pedidos pe WHERE '+valid),connection,parse_dates=['fecha'])
    clients=pd.read_sql_query(text('SELECT id_usuario FROM usuarios WHERE auth_uuid IS NULL'),connection)
    items=pd.read_sql_query(text('''SELECT de.id_pedido,va.id_producto,p.id_vendedor,p.titulo,de.cantidad,
        CAST(ROUND(de.precio_unit*100) AS SIGNED) precio_unit_centimos FROM pedido_detalle de
        JOIN variantes va USING(id_variante) JOIN productos p USING(id_producto) JOIN pedidos pe USING(id_pedido) WHERE '''+valid),connection)
    shipments=pd.read_sql_query(text('''SELECT e.*,c.nombre courier,COALESCE(JSON_UNQUOTE(JSON_EXTRACT(pe.destino,'$.departamento')),d.departamento) departamento
        FROM envios e JOIN pedidos pe USING(id_pedido) JOIN couriers c USING(id_courier)
        JOIN usuarios u ON pe.id_usuario=u.id_usuario JOIN distritos d ON u.id_distrito=d.id_distrito WHERE '''+valid),connection)
    reviews=pd.read_sql_query(text('''SELECT r.id_resena,p.id_vendedor,r.estrellas,r.comentario FROM resenas r
        JOIN productos p USING(id_producto) JOIN usuarios u ON r.id_usuario=u.id_usuario WHERE u.auth_uuid IS NULL'''),connection)
    vendors=pd.read_sql_query(text('''SELECT s.id_vendedor,s.razon_social,s.reputacion reputacion_registrada
        FROM vendedores s JOIN usuarios u USING(id_usuario) WHERE u.auth_uuid IS NULL'''),connection)
    return orders,clients,items,shipments,reviews,vendors


def build_bundle():
    with engine.connect() as connection:
        orders,clients,items,shipments,reviews,vendors=load_frames(connection)
        rfm_frame,reference=rfm(orders,clients)
        vendor_frame=vendor_summary(items,reviews,shipments,vendors)
        flagged,criteria=diagnose(vendor_frame)
        reports=dict(rfm=rfm_frame,cohortes=cohorts(orders),cocompras=co_purchases(items),
            entregas=delivery_summary(shipments),vendedores=vendor_frame,diagnostico=flagged)
        queries=sql_queries()
        for name in ('ventas_distrito','stock','categorias'):
            reports[name]=pd.read_sql_query(text(queries[name]),connection)
    valid_shipments=clean_shipments(shipments)
    segments=rfm_frame.segmento.value_counts().rename_axis('label').reset_index(name='value')
    retention=reports['cohortes'].groupby('mes').agg(clientes=('clientes','sum'),base=('base_cohorte','sum')).reset_index()
    retention['value']=(100*retention.clientes/retention.base).round(2)
    retention['label']=retention.mes.map(lambda value:'Mes '+str(value))
    times=valid_shipments.groupby('courier').entrega_dias.mean().round(2).rename_axis('label').reset_index(name='value')
    scatter=vendor_frame[['razon_social','ventas_brutas','estrellas_promedio','retraso_pct']].dropna()
    charts=dict(rfm=json.loads(segments.to_json(orient='records')),cohortes=json.loads(retention[['label','value']].to_json(orient='records')),
                entregas=json.loads(times.to_json(orient='records')),vendedores=json.loads(scatter.to_json(orient='records')))
    return dict(reports=reports,charts=charts,criteria=criteria,generated_at=datetime.now(timezone.utc).isoformat(),
        reference_date=reference.date().isoformat(),summary=dict(clientes=len(clients),pedidos_analizados=len(orders),
        vendedores=len(vendors),resenas=len(reviews),envios_validos=len(valid_shipments),vendedores_detectados=len(flagged)))


def get_bundle():
    with _lock:
        if not _cache or time.monotonic()-_cache['time']>=60:
            _cache.update(time=time.monotonic(),bundle=build_bundle())
        return _cache['bundle']


@router.get('/summary')
def summary():
    bundle=get_bundle()
    return {key:value for key,value in bundle.items() if key not in ('reports','charts')}|{'reports':list(NOTES),'scope':'Histórico original del dataset; inventario crítico actual.'}


@router.get('/reports/{name}')
def report(name:str,page:int=Query(1,ge=1,le=1000000),page_size:int=Query(25,ge=1,le=100)):
    if name not in NOTES:
        raise HTTPException(404,'Análisis no encontrado.')
    bundle=get_bundle()
    frame=bundle['reports'][name]
    return dict(columns=frame.columns.tolist(),items=json.loads(frame.iloc[(page-1)*page_size:page*page_size].to_json(orient='records',date_format='iso')),
        total=len(frame),page=page,pages=(len(frame)+page_size-1)//page_size,notes=NOTES[name],
        chart=bundle['charts'].get(name,[]),generated_at=bundle['generated_at'],criteria=bundle['criteria'] if name=='diagnostico' else None)


def export_csv(frame):
    safe=frame.copy()
    for column in safe.select_dtypes(include=['str','object']).columns:
        safe[column]=safe[column].map(lambda value:"'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value)
    return safe.to_csv(index=False).encode('utf-8-sig')


@router.get('/exports/{name}.csv')
def download(name:str):
    if name not in NOTES:
        raise HTTPException(404,'Análisis no encontrado.')
    return Response(export_csv(get_bundle()['reports'][name]),media_type='text/csv',
                    headers={'Content-Disposition':f'attachment; filename="tickia-{name}.csv"'})


def export_reports(destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    bundle=build_bundle()
    for name,frame in bundle['reports'].items():
        (destination/(name+'.csv')).write_bytes(export_csv(frame))
    metadata={key:value for key,value in bundle.items() if key not in ('reports','charts')}
    (destination/'resultados.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(metadata,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--export',default=str(LOCAL_DIR/'analisis'))
    export_reports(parser.parse_args().export)
