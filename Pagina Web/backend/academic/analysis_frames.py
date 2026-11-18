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
    # Desempate por nombre: el orden no depende del orden en que MySQL devuelve las filas.
    return pd.DataFrame(records,columns=columns).sort_values(['pedidos_juntos','lift','producto_a','producto_b'],
        ascending=[False,False,True,True],kind='mergesort')


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


STAR_BANDS=[0,3,3.5,4,4.5,5.0001]
STAR_LABELS=['≤ 3,0','3,0–3,5','3,5–4,0','4,0–4,5','4,5–5,0']


def stars_vs_sales(items,reviews,vendors,min_reviews=5):
    """Relación entre estrellas de reseña y ventas, por producto y por vendedor.

    Por producto: promedio de estrellas (con al menos `min_reviews` reseñas) frente a
    unidades y ventas brutas del histórico. Por vendedor: mismas elegibilidades que el
    diagnóstico (10+ pedidos y con reseñas). Se usa Spearman porque las ventas tienen
    una distribución muy asimétrica (pocos productos concentran la mayoría)."""
    sales=items.assign(linea_centimos=items.cantidad*items.precio_unit_centimos).groupby('id_producto').agg(
        unidades=('cantidad','sum'),ventas_centimos=('linea_centimos','sum'),pedidos=('id_pedido','nunique'))
    ratings=reviews.groupby('id_producto').agg(estrellas_promedio=('estrellas','mean'),resenas=('id_resena','nunique'))
    products=ratings[ratings.resenas>=min_reviews].join(sales,how='inner')
    products['ventas_brutas']=(products.pop('ventas_centimos')/100).round(2)
    products['tramo_estrellas']=pd.cut(products.estrellas_promedio,STAR_BANDS,labels=STAR_LABELS,right=False)
    bands=products.groupby('tramo_estrellas',observed=False).agg(productos=('unidades','size'),
        unidades_mediana=('unidades','median'),ventas_mediana=('ventas_brutas','median'),
        ventas_totales=('ventas_brutas','sum')).reset_index()
    bands['participacion_ventas_pct']=(100*bands.ventas_totales/bands.ventas_totales.sum()).round(2)
    eligible=vendors[(vendors.pedidos>=10)&vendors.estrellas_promedio.notna()]

    def spearman(frame,left,right):
        frame=frame[[left,right]].dropna()
        if len(frame)<3:
            return None
        # Spearman = Pearson sobre rangos (empates promediados); no requiere scipy.
        value=float(frame[left].rank().corr(frame[right].rank()))
        return round(value,3) if np.isfinite(value) else None

    summary=dict(minimo_resenas_producto=min_reviews,productos=len(products),
        spearman_producto_estrellas_unidades=spearman(products,'estrellas_promedio','unidades'),
        spearman_producto_estrellas_ventas=spearman(products,'estrellas_promedio','ventas_brutas'),
        vendedores=len(eligible),spearman_vendedor_estrellas_ventas=spearman(eligible,'estrellas_promedio','ventas_brutas'))
    products=products.reset_index().sort_values('ventas_brutas',ascending=False)
    return products.round(2),bands.round(2),summary


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


MONTH_NAMES=['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Set','Oct','Nov','Dic']


def monthly_series(orders):
    """Serie de tiempo mensual de ventas y tabla de calendario año × mes.

    resample('MS') agrupa por mes calendario; rolling(3) suaviza con una media móvil
    de tres meses; las variaciones se calculan contra el mes anterior y contra el mismo
    mes del año previo. pivot_table arma el calendario para comparar estacionalidad."""
    columns=['mes','pedidos','ventas','ticket_promedio','media_movil_3m','variacion_mensual_pct','variacion_anual_pct']
    if orders.empty:
        return pd.DataFrame(columns=columns),pd.DataFrame()
    frame=orders[['id_pedido','fecha','total_centimos']].copy()
    frame['fecha']=pd.to_datetime(frame.fecha)
    frame['ventas']=frame.total_centimos/100
    series=frame.set_index('fecha').sort_index().resample('MS').agg({'id_pedido':'nunique','ventas':'sum'})
    series=series.rename(columns={'id_pedido':'pedidos'})
    series['ticket_promedio']=series.ventas/series.pedidos.where(series.pedidos>0)
    series['media_movil_3m']=series.ventas.rolling(3).mean()
    # Variaciones calculadas con shift: el resultado no depende de la versión de pandas.
    series['variacion_mensual_pct']=100*(series.ventas/series.ventas.shift(1)-1)
    series['variacion_anual_pct']=100*(series.ventas/series.ventas.shift(12)-1)
    series=series.replace([np.inf,-np.inf],np.nan).round(2).rename_axis('mes').reset_index()
    series['mes']=series.mes.dt.strftime('%Y-%m')
    calendar=frame.assign(anio=frame.fecha.dt.year,numero_mes=frame.fecha.dt.month).pivot_table(
        index='numero_mes',columns='anio',values='ventas',aggfunc='sum').round(2)
    calendar.index=[MONTH_NAMES[number-1] for number in calendar.index]
    calendar.index.name='mes'
    calendar.columns=[str(year) for year in calendar.columns]
    return series[columns],calendar.reset_index()
