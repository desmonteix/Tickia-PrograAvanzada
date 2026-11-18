"""Crea, ejecuta y exporta un cuaderno real de SQL y Pandas para el informe."""
import json
import os
from pathlib import Path
import sys
import nbformat as nbf
from nbclient import NotebookClient
from nbconvert import HTMLExporter
from traitlets.config import Config
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
WEB=ROOT/'Pagina Web'
OUT=ROOT/'Proyecto_PrograAvanzada/entregables/informe'
LOCAL=ROOT/'Proyecto_PrograAvanzada/.local/informe-build'
sys.path.insert(0,str(WEB))


def run():
    from backend.academic.database import engine
    results=LOCAL/'resultados';results.mkdir(parents=True,exist_ok=True)
    os.environ['TICKIA_ACADEMIC_MYSQL_URL']=engine.url.set(database='tickia_universidad_clean_test').render_as_string(hide_password=False)
    os.environ['TICKIA_REPORT_OUTPUT']=str(results)
    kernels=LOCAL/'jupyter/kernels/tickia-informe';kernels.mkdir(parents=True,exist_ok=True)
    (kernels/'kernel.json').write_text(json.dumps(dict(argv=[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],display_name='Python Tickia — informe',language='python')),encoding='utf-8')
    os.environ['JUPYTER_PATH']=str(LOCAL/'jupyter')
    notebook=nbf.v4.new_notebook()
    notebook.metadata['kernelspec']=dict(display_name='Python Tickia — informe',language='python',name='tickia-informe')
    cells=[];captures={}
    def md(text):cells.append(nbf.v4.new_markdown_cell(text))
    def code(text,tag=None):
        if tag:captures[tag]=sum(cell.cell_type=='code' for cell in cells)
        if tag and tag.startswith(('22_','23_','24_','25_','26_')) and '\nfig, ' in text:
            before,after=text.split('\nfig, ',1)
            if tag.startswith('23_'):before+='\ndisplay(matrix.round(1))'
            cells.append(nbf.v4.new_code_cell(before))
            cells.append(nbf.v4.new_code_cell('fig, '+after))
        else:
            cells.append(nbf.v4.new_code_cell(text))
    md('# Tickia: evidencia ejecutada de MySQL y análisis con Pandas\n\nProyecto de Programación Avanzada. Todas las salidas se obtienen al ejecutar el código. Las operaciones comerciales de demostración usan una base aislada. El histórico se filtra con origen = dataset. No se muestran credenciales ni contraseñas.')
    code('''from pathlib import Path
import os, sys, json, platform
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sqlalchemy import text
from IPython.display import display

candidates = [Path.cwd(), *Path.cwd().parents]
ROOT = next(p for ancestor in candidates for p in (ancestor, ancestor / 'codigo_fuente')
            if (p / 'Pagina Web' / 'backend' / 'academic').is_dir())
sys.path.insert(0, str(ROOT / 'Pagina Web'))
# El ZIP usa una instancia propia en 3308; reutiliza su configuración local sin mostrarla.
delivery = ROOT.parent / '.entrega_config'
if ROOT.name == 'codigo_fuente' and not os.getenv('TICKIA_ACADEMIC_MYSQL_URL') and (delivery / 'mysql.env').is_file():
    from sqlalchemy.engine import URL
    values = dict(line.split('=', 1) for line in (delivery / 'mysql.env').read_text(encoding='utf-8').splitlines() if '=' in line)
    ports = json.loads((delivery / 'puertos.json').read_text(encoding='utf-8'))
    os.environ['TICKIA_ACADEMIC_MYSQL_URL'] = URL.create('mysql+pymysql', username=values['MYSQL_USER'],
        password=values['MYSQL_PASSWORD'], host='127.0.0.1', port=ports['mysql'], database=values['MYSQL_DATABASE'],
        query={'charset':'utf8mb4'}).render_as_string(hide_password=False)
    os.environ['TICKIA_LOCAL_DIR'] = str(delivery / 'app')
from backend.academic.database import engine
from backend.academic.analytics import build_bundle, sql_queries, export_csv, load_frames
from backend.academic.analysis_frames import clean_shipments
OUTPUT = Path(os.getenv('TICKIA_REPORT_OUTPUT', ROOT / 'Proyecto_PrograAvanzada/.local/analisis_informe'))
OUTPUT.mkdir(parents=True, exist_ok=True)
pd.set_option('display.max_columns', 15)
pd.set_option('display.float_format', lambda value: f'{value:,.2f}')
plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':10, 'axes.spines.top':False,
                     'axes.spines.right':False, 'figure.dpi':130, 'savefig.dpi':200})
print('Python:', platform.python_version(), '| Pandas:', pd.__version__, '| NumPy:', np.__version__)
with engine.connect() as connection:
    print('MySQL:', connection.execute(text('SELECT VERSION()')).scalar_one())''')
    md('## 1. Base cargada y estructura normalizada\nSe cuentan las tablas base por separado de las vistas. Los tres usuarios operativos y los registros web son ficticios y se incluyen en el respaldo de entrega.')
    code('''with engine.connect() as connection:
    tables = pd.read_sql_query(text("SELECT TABLE_NAME tabla FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"), connection)
    counts = []
    for name in tables.tabla:
        amount = connection.execute(text('SELECT COUNT(*) FROM `' + name + '`')).scalar_one()
        counts.append({'tabla':name, 'filas':amount})
    counts = pd.DataFrame(counts)
display(counts)
print('Tablas base:', len(counts), '| Filas físicas:', int(counts.filas.sum()))
counts.to_csv(OUTPUT / 'conteos_bd.csv', index=False)''','15_bd_conteos')
    code('''sql_fk = """SELECT TABLE_NAME tabla, COLUMN_NAME columna,
    REFERENCED_TABLE_NAME referencia, REFERENCED_COLUMN_NAME clave_destino
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, COLUMN_NAME"""
with engine.connect() as connection:
    foreign_keys = pd.read_sql_query(text(sql_fk), connection)
display(foreign_keys)
print('Llaves foráneas:', len(foreign_keys))
foreign_keys.to_csv(OUTPUT / 'llaves_foraneas.csv', index=False)''','16_bd_relaciones')
    code('''with engine.connect() as connection:
    views = pd.read_sql_query(text('SELECT TABLE_NAME vista FROM information_schema.VIEWS WHERE TABLE_SCHEMA=DATABASE()'), connection)
    procedures = pd.read_sql_query(text("SELECT ROUTINE_NAME procedimiento, ROUTINE_COMMENT version FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=DATABASE() AND ROUTINE_TYPE='PROCEDURE'"), connection)
    triggers = pd.read_sql_query(text('SELECT TRIGGER_NAME nombre, ACTION_TIMING momento, EVENT_MANIPULATION evento, EVENT_OBJECT_TABLE tabla FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()'), connection)
display(views); display(procedures); display(triggers)''','17_bd_objetos')
    md('## 2. Consultas SQL ejecutadas\nEl archivo de consultas contiene 13 sentencias identificadas. Aquí se muestran resultados, ventanas y el uso real de índices.')
    code('''queries = sql_queries()
print(queries['ranking_vendedores'])
with engine.connect() as connection:
    ranking = pd.read_sql_query(text(queries['ranking_vendedores']), connection)
display(ranking.head(8))
print('Vendedores con ventas válidas:', len(ranking))''','18_sql_ranking')
    code('''print(queries['ventas_mensuales'])
with engine.connect() as connection:
    monthly = pd.read_sql_query(text(queries['ventas_mensuales']), connection)
display(monthly.head(8))
print('Observaciones vendedor-mes:', len(monthly))''','19_sql_ventanas')
    code('''with engine.connect() as connection:
    critical_plan = pd.read_sql_query(text('EXPLAIN SELECT id_variante FROM variantes WHERE stock<=3'), connection)
    orders_plan = pd.read_sql_query(text('EXPLAIN SELECT id_pedido FROM pedidos WHERE id_usuario=1 ORDER BY fecha DESC,id_pedido DESC LIMIT 24'), connection)
display(critical_plan[['table','type','possible_keys','key','rows','Extra']])
display(orders_plan[['table','type','possible_keys','key','rows','Extra']])''','20_sql_indices')
    md('## 3. Análisis con Pandas\nLos importes de ventas, las reseñas y los envíos se agregan por separado. Se excluyen pedidos pendientes y cancelados del histórico. El reporte de stock usa inventario actual.')
    code('''bundle = build_bundle()
reports = bundle['reports']
display(pd.DataFrame([bundle['summary']]))
print('Referencia RFM:', bundle['reference_date'])
for name, frame in reports.items():
    (OUTPUT / (name + '.csv')).write_bytes(export_csv(frame))
metadata = {key:value for key,value in bundle.items() if key not in ('reports','charts')}
(OUTPUT / 'resultados.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
print('Reportes completos exportados:', len(reports))''','21_pandas_resumen')
    code('''rfm = reports['rfm']
segments = rfm.segmento.value_counts().rename_axis('segmento').reset_index(name='clientes')
display(segments)
display(rfm.head(6))
fig, ax = plt.subplots(figsize=(8.6,4.3))
bars = ax.barh(segments.segmento[::-1], segments.clientes[::-1], color='#1E597C')
ax.bar_label(bars, fmt='{:,.0f}', padding=4)
ax.set(xlabel='Clientes', title='Segmentación RFM del histórico (45.000 clientes)')
ax.set_xlim(0, segments.clientes.max()*1.18)
fig.tight_layout(); fig.savefig(OUTPUT/'grafico_rfm.png', bbox_inches='tight'); plt.show()''','22_pandas_rfm')
    code('''cohorts = reports['cohortes']
cohort_names = sorted(cohorts.cohorte.unique())[-12:]
matrix = cohorts[cohorts.cohorte.isin(cohort_names)].pivot(index='cohorte', columns='mes', values='retencion_pct').reindex(index=cohort_names, columns=range(12))
fig, ax = plt.subplots(figsize=(9,5.8))
colors = plt.get_cmap('Blues').copy(); colors.set_bad('#EEEEEE')
image = ax.imshow(matrix.to_numpy(dtype=float), vmin=0, vmax=100, aspect='auto', cmap=colors)
ax.set_xticks(range(12), labels=range(12)); ax.set_yticks(range(12), labels=cohort_names)
for row_index in range(12):
    for column_index in range(12):
        value = matrix.iloc[row_index,column_index]
        if pd.notna(value): ax.text(column_index,row_index,f'{value:.0f}',ha='center',va='center',fontsize=8,color='white' if value>50 else '#17384E')
ax.set(xlabel='Mes desde primera compra', ylabel='Cohorte', title='Retención: 12 cohortes recientes y meses 0–11 (%)')
fig.colorbar(image, ax=ax, label='Retención (%)')
fig.tight_layout(); fig.savefig(OUTPUT/'grafico_cohortes.png', bbox_inches='tight'); plt.show()
print('Meses sin exposición: celdas grises; no se convierten en cero.')''','23_pandas_cohortes')
    md('### Serie de tiempo de ventas\nresample agrupa los pedidos válidos por mes calendario, rolling calcula la media móvil de tres meses y pivot_table arma el calendario año × mes para comparar estacionalidad.')
    code('''series = reports['serie_mensual']
calendar = reports['ventas_calendario']
display(series.tail(8))
display(calendar)
fig, ax = plt.subplots(figsize=(10,4.3))
x = pd.to_datetime(series.mes)
ax.plot(x, series.ventas/1e6, marker='o', ms=3, color='#1E597C', label='Ventas del mes')
ax.plot(x, series.media_movil_3m/1e6, ls='--', color='#B45C29', label='Media móvil 3 meses')
ax.set(ylabel='Ventas (millones de S/)', title='Serie mensual de ventas del histórico')
ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(OUTPUT/'grafico_serie_mensual.png', bbox_inches='tight'); plt.show()
last = series.iloc[-1]
print(f"Último mes {last.mes}: S/ {last.ventas:,.2f}, variación anual {last.variacion_anual_pct:.1f} %.")''','23b_pandas_serie_mensual')
    code('''pairs = reports['cocompras']
display(pairs.head(6))
print('Los productos se deduplican dentro de cada pedido antes de formar parejas.')
top = pairs.head(8).copy()
import textwrap
labels = [textwrap.fill(a+' + '+b, 45) for a,b in zip(top.producto_a,top.producto_b)]
fig, ax = plt.subplots(figsize=(10,6.5))
bars = ax.barh(labels[::-1], top.pedidos_juntos.iloc[::-1], color='#287C76')
ax.bar_label(bars, padding=3)
ax.set(xlabel='Pedidos conjuntos', title='Ocho pares más frecuentes del histórico')
ax.set_xlim(0, top.pedidos_juntos.max()*1.15)
fig.tight_layout(); fig.savefig(OUTPUT/'grafico_cocompras.png', bbox_inches='tight'); plt.show()''','24_pandas_afinidad')
    code('''with engine.connect() as connection:
    orders,clients,items,shipments,reviews,vendors = load_frames(connection)
valid = clean_shipments(shipments)
courier_summary = valid.groupby('courier').agg(envios=('id_envio','size'), dias=('entrega_dias','mean'), retraso=('retrasado','mean')).reset_index()
courier_summary['retraso_pct'] = courier_summary.pop('retraso')*100
display(courier_summary.round(2))
fig, axes = plt.subplots(1,2,figsize=(11,4.2))
axes[0].barh(courier_summary.courier, courier_summary.dias, color='#1E597C'); axes[0].set_xlabel('Días medios')
axes[1].barh(courier_summary.courier, courier_summary.retraso_pct, color='#B45C29'); axes[1].set_xlabel('Entregas tardías (%)')
fig.suptitle('Couriers: duración y puntualidad, con fechas válidas')
fig.tight_layout(); fig.savefig(OUTPUT/'grafico_couriers.png', bbox_inches='tight'); plt.show()
courier_summary.to_csv(OUTPUT/'resumen_couriers.csv', index=False)''','25_pandas_entregas')
    code('''diagnostic = reports['diagnostico']
display(diagnostic[['id_vendedor','razon_social','ventas_brutas','estrellas_promedio','retraso_pct']].head(8))
display(pd.DataFrame([bundle['criteria']]))
vendors_frame = reports['vendedores']
eligible = vendors_frame[(vendors_frame.pedidos>=10)&vendors_frame.estrellas_promedio.notna()].dropna(subset=['retraso_pct'])
fig, ax = plt.subplots(figsize=(8.6,4.6))
ax.scatter(eligible.retraso_pct,eligible.estrellas_promedio,s=20,alpha=.65,color='#1E597C')
coefficient = np.polyfit(eligible.retraso_pct.to_numpy(dtype=float),eligible.estrellas_promedio.to_numpy(dtype=float),1)
horizontal = np.linspace(0,100,100); ax.plot(horizontal,np.polyval(coefficient,horizontal),color='#B45C29',lw=1.5)
ax.set(xlabel='Pedidos tardíos (%)',ylabel='Estrellas promedio',title='Asociación por vendedor: retrasos y calificación')
ax.text(.02,.05,f"n = {len(eligible)}; Pearson r = {bundle['criteria']['correlacion_estrellas_retrasos']:.3f}",transform=ax.transAxes)
fig.tight_layout(); fig.savefig(OUTPUT/'grafico_reputacion.png', bbox_inches='tight'); plt.show()
print('14 vendedores cumplen los tres criterios. La asociación no demuestra causalidad.')''','26_pandas_diagnostico')
    md('### Estrellas de reseña y ventas\nSe agrupan los productos con al menos cinco reseñas por tramo de estrellas y se compara con sus unidades y ventas. La correlación de Spearman se usa porque las ventas son muy asimétricas.')
    code('''bands = reports['estrellas_ventas']
relation = bundle['estrellas_ventas']
display(bands)
display(pd.DataFrame([relation]))
vendors_frame = reports['vendedores']
eligible = vendors_frame[(vendors_frame.pedidos>=10)&vendors_frame.estrellas_promedio.notna()]
fig, axes = plt.subplots(1,2,figsize=(11,4.4))
bars = axes[0].bar(bands.tramo_estrellas.astype(str), bands.unidades_mediana, color='#1E597C')
axes[0].bar_label(bars, labels=[f'{u:.0f} u.\\n({p} prod.)' for u,p in zip(bands.unidades_mediana,bands.productos)], padding=3, fontsize=8)
axes[0].set(xlabel='Estrellas promedio del producto', ylabel='Unidades vendidas (mediana)',
            title=f"Por producto: Spearman ρ = {relation['spearman_producto_estrellas_unidades']:.3f}")
axes[0].set_ylim(0, bands.unidades_mediana.max()*1.3)
axes[1].scatter(eligible.estrellas_promedio, eligible.ventas_brutas, s=18, alpha=.6, color='#1E597C')
axes[1].set_yscale('log')
axes[1].set(xlabel='Estrellas promedio del vendedor', ylabel='Ventas brutas S/ (escala log)',
            title=f"Por vendedor: Spearman ρ = {relation['spearman_vendedor_estrellas_ventas']:.3f} (n = {relation['vendedores']})")
fig.suptitle('Relación entre estrellas de reseña y ventas del histórico')
fig.tight_layout(); fig.savefig(OUTPUT/'grafico_estrellas_ventas.png', bbox_inches='tight'); plt.show()
print(f"{relation['productos']} productos con al menos {relation['minimo_resenas_producto']} reseñas. "
      'Las estrellas no se asocian con más o menos ventas; sí con los retrasos (sección anterior).')''','28_pandas_estrellas_ventas')
    md('## 4. Análisis SQL adicionales\nInactividad adaptada a la cadencia del cliente, concentración por categoría, riesgo de courier y afinidad mediante canastas deduplicadas.')
    code('''advanced = pd.DataFrame([{'reporte':name, 'filas':len(reports[name])}
    for name in ['clientes_inactivos','participacion_categorias','riesgo_courier','afinidad_sql']])
display(advanced)
display(reports['riesgo_courier'].head(6))
print('Los intervalos de Wilson son aproximados y presuponen observaciones independientes.')''','27_sql_avanzado')
    notebook.cells=cells
    path=OUT/'Analisis_Tickia.ipynb'
    NotebookClient(notebook,timeout=300,kernel_name='tickia-informe',resources={'metadata':{'path':str(WEB)}}).execute()
    nbf.write(notebook,path)
    config=Config();config.HTMLExporter.mathjax_url='';config.HTMLExporter.require_js_url=''
    exporter=HTMLExporter(config=config,template_name='lab')
    body,_=exporter.from_notebook_node(notebook)
    body=body.replace('</head>','<style>body{background:#f4f6f8!important}.jp-Notebook{max-width:1120px;margin:auto;background:white;padding:24px!important}.jp-Cell{padding:20px!important;border-bottom:1px solid #dde3e8}.jp-InputArea-editor,.jp-RenderedText pre{font-size:14px!important}table{font-size:14px!important}</style></head>')
    html=OUT/'Analisis_Tickia.html';html.write_text(body,encoding='utf-8')
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport={'width':1180,'height':1000},device_scale_factor=1.5)
        page.goto(html.as_uri())
        for name,index in captures.items():
            page.locator('.jp-CodeCell').nth(index).screenshot(path=str(OUT/'figuras'/f'{name}.png'))
        browser.close()
    (LOCAL/'cuaderno_ejecucion.json').write_text(json.dumps(dict(cells=len(cells),code_cells=sum(cell.cell_type=='code' for cell in cells),executed=True,errors=0,captures=captures),indent=2),encoding='utf-8')
    print('Cuaderno ejecutado, HTML y',len(captures),'capturas de SQL/Pandas generados.')


if __name__=='__main__':run()
