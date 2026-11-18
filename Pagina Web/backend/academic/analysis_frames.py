"""Transformaciones Pandas puras: sin acceso a archivos ni conexión a la BD."""
from collections import Counter
from itertools import combinations
import numpy as np
import pandas as pd


def rfm(orders,clients):
    grouped=orders.groupby('id_usuario').agg(ultima_compra=('fecha','max'),frecuencia=('id_pedido','nunique'),monetario_centimos=('total_centimos','sum'))
    frame=clients[['id_usuario']].merge(grouped,left_on='id_usuario',right_index=True,how='left')
    reference=(orders.fecha.max().normalize()+pd.Timedelta(days=1)) if not orders.empty else pd.Timestamp.now(tz='America/Lima').tz_localize(None).normalize()
    frame['recencia_dias']=(reference-frame.ultima_compra).dt.days
    frame['frecuencia']=frame.frecuencia.fillna(0).astype('int64')
    frame['monetario']=(frame.monetario_centimos.fillna(0)/100).round(2)
    active=frame.frecuencia>0
    for column,metric,inverse in [('r','recencia_dias',True),('f','frecuencia',False),('m','monetario',False)]:
        frame[column]=0
        score=np.ceil(frame.loc[active,metric].rank(method='average',pct=True)*5).astype('int64').clip(1,5)
        frame.loc[active,column]=6-score if inverse else score
    frame['segmento']=np.select([~active,(frame.r+frame.f+frame.m)>=13,(frame.r<=2)&(frame.f>=3),frame.f>=4,
                                (frame.r>=4)&(frame.f<=2)],
                               ['Sin compras','Campeones','En riesgo','Leales','Nuevos'],default='Ocasionales')
    return frame[['id_usuario','recencia_dias','frecuencia','monetario','r','f','m','segmento']].sort_values(['frecuencia','monetario'],ascending=False),reference


def cohorts(orders):
    columns=['cohorte','mes','clientes','base_cohorte','retencion_pct']
    if orders.empty:
        return pd.DataFrame(columns=columns)
    frame=orders[['id_pedido','id_usuario','fecha']].copy()
    frame['mes_numero']=frame.fecha.dt.year*12+frame.fecha.dt.month
    first=frame.groupby('id_usuario').mes_numero.min()
    frame['cohorte_numero']=frame.id_usuario.map(first)
    frame['mes']=frame.mes_numero-frame.cohorte_numero
    counts=frame.groupby(['cohorte_numero','mes']).id_usuario.nunique()
    sizes=first.value_counts()
    last=int(frame.mes_numero.max())
    records=[]
    for cohort in sorted(sizes.index,reverse=True):
        base=int(sizes.loc[cohort])
        for month in range(last-int(cohort)+1):
            count=int(counts.get((cohort,month),0))
            records.append([f'{(int(cohort)-1)//12:04}-{(int(cohort)-1)%12+1:02}',month,count,base,round(100*count/base,2)])
    return pd.DataFrame(records,columns=columns)


def co_purchases(items):
    columns=['producto_a','producto_b','pedidos_juntos','soporte_pct','confianza_a_b_pct','lift']
    basket=items[['id_pedido','id_producto']].drop_duplicates()
    pairs=Counter()
    for _,products in basket.groupby('id_pedido',sort=False):
        pairs.update(combinations(sorted(products.id_producto.tolist()),2))
    if not pairs:
        return pd.DataFrame(columns=columns)
    frequencies=basket.groupby('id_producto').id_pedido.nunique()
    total=basket.id_pedido.nunique()
    titles=items.drop_duplicates('id_producto').set_index('id_producto').titulo.to_dict()
    records=[]
    for (a,b),count in pairs.items():
        records.append([titles.get(a,str(a)),titles.get(b,str(b)),count,round(100*count/total,4),
                        round(100*count/frequencies[a],2),round(count*total/(frequencies[a]*frequencies[b]),4)])
    return pd.DataFrame(records,columns=columns).sort_values(['pedidos_juntos','lift'],ascending=False)


def clean_shipments(shipments):
    frame=shipments.copy()
    for column in ('fecha_envio','fecha_entrega','fecha_estimada'):
        frame[column]=pd.to_datetime(frame[column],errors='coerce',format='mixed')
    frame=frame[frame.fecha_envio.notna()&frame.fecha_entrega.notna()&(frame.fecha_entrega>=frame.fecha_envio)].copy()
    frame['entrega_dias']=(frame.fecha_entrega-frame.fecha_envio).dt.total_seconds()/86400
    # La promesa es una fecha, no la medianoche: entregar el mismo día es puntual.
    frame['retrasado']=(frame.fecha_entrega.dt.normalize()>frame.fecha_estimada.dt.normalize()).astype('Float64').where(frame.fecha_estimada.notna())
    return frame


def delivery_summary(shipments):
    valid=clean_shipments(shipments)
    frame=valid.groupby(['courier','departamento'],dropna=False).agg(envios=('id_envio','size'),
        entrega_dias=('entrega_dias','mean'),promesas_conocidas=('retrasado','count'),retraso_pct=('retrasado','mean')).reset_index()
    frame['retraso_pct']=frame.retraso_pct*100
    return frame.round(2).sort_values(['retraso_pct','envios'],ascending=False)


def vendor_summary(items,reviews,shipments,vendors):
    sales=items.assign(linea_centimos=items.cantidad*items.precio_unit_centimos).groupby('id_vendedor').agg(
        ventas_brutas_centimos=('linea_centimos','sum'),pedidos=('id_pedido','nunique'),unidades=('cantidad','sum'))
    ratings=reviews.groupby('id_vendedor').agg(estrellas_promedio=('estrellas','mean'),resenas=('id_resena','nunique'))
    valid=clean_shipments(shipments)
    per_order=valid.groupby('id_pedido').agg(retrasado=('retrasado','max'),entrega_dias=('entrega_dias','mean')).reset_index()
    links=items[['id_pedido','id_vendedor']].drop_duplicates().merge(per_order,on='id_pedido',how='inner')
    delivery=links.groupby('id_vendedor').agg(entregas_conocidas=('retrasado','count'),retraso_pct=('retrasado','mean'),entrega_dias=('entrega_dias','mean'))
    result=vendors.merge(sales,left_on='id_vendedor',right_index=True,how='left').merge(ratings,left_on='id_vendedor',right_index=True,how='left').merge(delivery,left_on='id_vendedor',right_index=True,how='left')
    for column in ('ventas_brutas_centimos','pedidos','unidades','resenas','entregas_conocidas'):
        result[column]=result[column].fillna(0).astype('int64')
    result['ventas_brutas']=(result.ventas_brutas_centimos/100).round(2)
    result['retraso_pct']=result.retraso_pct*100
    return result.drop(columns='ventas_brutas_centimos').round(2).sort_values('ventas_brutas',ascending=False)


def diagnose(vendors):
    eligible=vendors[(vendors.pedidos>=10)&vendors.estrellas_promedio.notna()]
    threshold=float(eligible.ventas_brutas.quantile(.75)) if not eligible.empty else 0
    flagged=eligible[(eligible.ventas_brutas>=threshold)&(eligible.estrellas_promedio<3.5)&(eligible.retraso_pct>=25)].copy()
    complete=eligible[['estrellas_promedio','retraso_pct','ventas_brutas']].dropna()
    correlation=float(complete.estrellas_promedio.corr(complete.retraso_pct)) if len(complete)>=3 else None
    if correlation is not None and not np.isfinite(correlation):
        correlation=None
    return flagged,dict(ventas_altas_desde=round(threshold,2),minimo_pedidos=10,maximo_estrellas=3.5,
                       minimo_retraso_pct=25,correlacion_estrellas_retrasos=correlation,vendedores_correlacion=len(complete))
