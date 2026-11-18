"""Diagramas originales y editables de las entidades y clases reales del proyecto."""
import html
import json
from pathlib import Path
import shutil
import subprocess
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'Proyecto_PrograAvanzada/entregables/informe/diagramas'
VIZ=ROOT/'Proyecto_PrograAvanzada/.local/informe-build/viz'


def box(name,fields,methods=(),stereotype='',color='#183B56'):
    title=(html.escape(stereotype)+'<BR/>' if stereotype else '')+html.escape(name)
    row=lambda value:'<TR><TD ALIGN="LEFT"><FONT FACE="Arial" POINT-SIZE="11">'+html.escape(value)+'</FONT></TD></TR>'
    table='<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="6">'
    table+='<TR><TD BGCOLOR="'+color+'"><FONT FACE="Arial" COLOR="white" POINT-SIZE="13"><B>'+title+'</B></FONT></TD></TR>'
    table+=''.join(row(field) for field in fields)
    if methods:table+='<TR><TD HEIGHT="3" BGCOLOR="#E9EFF4"></TD></TR>'+''.join(row(method) for method in methods)
    return name+' [shape=plain label=<'+table+'</TABLE>>];\n'


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    graphs={}
    head='digraph G { graph [bgcolor="white", pad="0.25", nodesep="0.35", ranksep="0.50", splines=polyline]; node [fontname="Arial"]; edge [fontname="Arial", fontsize=10, color="#577188", arrowsize=.7];\n'
    entities={
      'departamentos':['PK id_departamento','UK nombre'],
      'provincias':['PK id_provincia','FK id_departamento','nombre'],
      'distritos':['PK id_distrito','FK id_provincia','nombre'],
      'usuarios':['PK id_usuario','FK id_distrito','nombre, email'],
      'cupones':['PK id_cupon','codigo, descuento_pct, vence'],
      'pedidos':['PK id_pedido','FK id_usuario, id_cupon','FK id_distrito_entrega','fecha, estado, total'],
      'vendedores':['PK id_vendedor','FK id_usuario','razon_social, reputacion'],
      'preguntas':['PK id_pregunta','FK id_producto, id_usuario','texto, respuesta'],
      'pagos':['PK id_pago','FK id_pedido','metodo, monto, estado'],
      'pedido_detalle':['PK/FK id_pedido','PK/FK id_variante','cantidad, precio_unit'],
      'productos':['PK id_producto','FK id_vendedor, id_categoria','titulo, precio'],
      'resenas':['PK id_resena','FK id_producto, id_usuario','estrellas, comentario'],
      'couriers':['PK id_courier','costo_base, estrategia'],
      'envios':['PK id_envio','FK id_pedido, id_courier','fechas, costo_envio'],
      'variantes':['PK id_variante','FK id_producto','talla, color, stock'],
      'favoritos':['PK/FK id_usuario','PK/FK id_producto','fecha'],
      'categorias':['PK id_categoria','FK id_padre (autorrelacion)','nombre'],
    }
    er=head+'graph [rankdir=TB];\n'
    for name,fields in entities.items():er+=box(name,[field for field in fields if field.startswith('PK')],color='#B45C29' if name in ('pedido_detalle','favoritos') else '#183B56')
    grid=[['departamentos','provincias','distritos','usuarios'],['cupones','pedidos','vendedores','preguntas'],['pagos','pedido_detalle','productos','resenas'],['couriers','envios','variantes','favoritos'],['categorias']]
    for group in grid:
        er+='{rank=same; '+';'.join(group)+'; '+' -> '.join(group)+' [style=invis,weight=40];}\n' if len(group)>1 else '{rank=same;categorias;}\n'
    er+='departamentos -> cupones -> pagos -> couriers -> categorias [style=invis,weight=80];\n'
    edges=[('departamentos','provincias','1','0..N'),('provincias','distritos','1','0..N'),('distritos','usuarios','1','0..N'),('usuarios','vendedores','1','0..N'),('usuarios','pedidos','1','0..N'),('cupones','pedidos','0..1','0..N'),('distritos','pedidos','0..1','0..N'),('vendedores','productos','1','0..N'),('categorias','productos','1','0..N'),('productos','variantes','1','0..N'),('pedidos','pedido_detalle','1','0..N'),('variantes','pedido_detalle','1','0..N'),('pedidos','pagos','1','0..N'),('pedidos','envios','1','0..N'),('couriers','envios','1','0..N'),('productos','resenas','1','0..N'),('usuarios','resenas','1','0..N'),('productos','preguntas','1','0..N'),('usuarios','preguntas','1','0..N'),('usuarios','favoritos','1','0..N'),('productos','favoritos','1','0..N'),('categorias','categorias','0..1','0..N')]
    for source,target,one,many in edges:
        er+=f'{source} -> {target} [constraint=false,taillabel="{one}",headlabel="{many}",labeldistance=1.4,arrowhead=none];\n'
    graphs['01_modelo_er']=er+'}'

    uml=head+'graph [rankdir=TB,ranksep=.55];\n'
    uml+=box('OrderBuilder',['-_items: dict','-_coupon: str | None','-_shipping: tuple | None'],['+add_item(id, quantity, price)','+with_coupon(code, percentage)','+shipping(strategy, base, department)','+build(): OrderDraft'])
    uml+=box('OrderDraft',['+items: tuple[OrderItem, ...]','+subtotal, discount: Decimal','+shipping_cost, total: Decimal'],stereotype='«dataclass inmutable»')
    uml+=box('OrderItem',['+variant_id: int','+quantity: int','+unit_price: Decimal'],stereotype='«dataclass inmutable»')
    uml+=box('PriceComponent',[],['+total(): Decimal','+discounts(): tuple'],stereotype='«abstracta»')
    uml+=box('BasePrice',['+amount: Decimal'],['+total(): Decimal'])
    uml+=box('PercentageDiscount',['+wrapped: PriceComponent','+percentage: Decimal','+label: str'],['+total(): Decimal','+discounts(): tuple'])
    uml+=box('ShippingStrategy',[],['+calculate(base, department, units)'],stereotype='«abstracta»')
    for name in ('StandardShipping','ExpressShipping','EconomyShipping'):uml+=box(name,[],['+calculate(...): Decimal'])
    uml+='OrderBuilder -> OrderDraft [style=dashed,label="«crea»"]; OrderDraft -> OrderItem [dir=both,arrowtail=odiamond,arrowhead=none,label="items 1..*"];\n'
    uml+='OrderBuilder -> ShippingStrategy [label="configura"]; OrderBuilder -> PriceComponent [style=dashed,label="cotiza"];\n'
    uml+='BasePrice -> PriceComponent [arrowhead=empty]; PercentageDiscount -> PriceComponent [arrowhead=empty];\n'
    uml+='PercentageDiscount -> PriceComponent [dir=both,arrowtail=odiamond,arrowhead=none,label="wrapped 1",constraint=false];\n'
    for name in ('StandardShipping','ExpressShipping','EconomyShipping'):uml+=name+' -> ShippingStrategy [arrowhead=empty];\n'
    graphs['02_uml_builder_strategy_decorator']=uml+'}'

    state=head+'graph [rankdir=TB,ranksep=.55];\n'
    state+=box('OrderContext',['+state: OrderState'],['+transition(target): OrderState'])
    state+=box('OrderState',['+name: str'],['+transition(next_name)','+pay(), ship(), deliver()','+from_name(name): OrderState'],stereotype='«clase base»')
    methods={'PendingState':['+pay(): PaidState'],'PaidState':['+ship(): ShippedState'],'ShippedState':['+deliver(): DeliveredState'],'DeliveredState':['Sin transiciones permitidas'],'CancelledState':['Estado historico terminal']}
    for name,items in methods.items():state+=box(name,[],items)
    state+='OrderContext -> OrderState [dir=both,arrowtail=diamond,arrowhead=none,label="estado actual 1"];\n'
    for name in methods:state+=name+' -> OrderState [arrowhead=empty];\n'
    graphs['03_uml_state']=state+'}'

    repo=head+'graph [rankdir=TB];\n'
    repo+=box('commerce',['quote_cart(), checkout()','history(), advance()'],stereotype='«modulo Python»')
    repo+=box('CatalogRepository',['+db: Connection'],['+variants(identifiers)','+valid_coupon(code)','+courier(id), district(id)'])
    repo+=box('OrderRepository',['+db: Connection'],['+find_by_request(user, request)','+receipt_records(ids)','+accessible(user, order)','+history(user, seller, page)','+locked_state(id), advance(id, state)','+confirm(engine, args) {static}'])
    repo+=box('Connection',[],['+execute(statement, params)'],stereotype='«SQLAlchemy»')
    repo+=box('Engine',[],['+begin(), connect()','+raw_connection()'],stereotype='«SQLAlchemy»')
    repo+='commerce -> CatalogRepository [style=dashed,label="usa"]; commerce -> OrderRepository [style=dashed,label="usa"];\n'
    repo+='CatalogRepository -> Connection [label="db inyectada"]; OrderRepository -> Connection [label="db inyectada"]; OrderRepository -> Engine [label="confirmacion atomica"];\n'
    graphs['04_uml_repository']=repo+'}'

    architecture=head+'graph [rankdir=LR]; node [shape=box,style="rounded,filled",fillcolor="#EDF3F7",fontsize=13,margin=.2];\n'
    architecture+='ui [label="React + TypeScript\nCatalogo, carrito y reportes"]; api [label="FastAPI\nAuth y rutas de la aplicacion"]; domain [label="Dominio Python\nBuilder, Strategy, Decorator, State"]; repositories [label="Repository de compras\nSQLAlchemy en los demas modulos"]; database [label="MySQL 8.4\n17 tablas, 3 vistas\nProcedimiento y trigger"]; pandas [label="Pandas\nRFM, cohortes, afinidad y entregas"]; loader [label="CSV originales / NumPy\nCarga y validacion de datos"];\n'
    architecture+='ui -> api [label="HTTP / JSON y cookies"]; api -> domain; api -> repositories; repositories -> database [label="SQL parametrizado"]; pandas -> database [label="SELECT"]; api -> pandas [label="reportes / CSV"]; loader -> database [label="carga transaccional"];\n'
    graphs['05_arquitectura']=architecture+'}'
    flow=head+'graph [rankdir=LR]; node [shape=box,style="rounded,filled",fillcolor="#EDF3F7",fontsize=14,margin=.2];\n'
    flow+='pendiente -> pagado [label="pago simulado\ny stock atomico"]; pagado -> enviado [label="simular despacho"]; enviado -> entregado [label="comprador confirma\nrecepcion"];\n'
    graphs['06_ciclo_pedido']=flow+'}'

    for name,dot in graphs.items():(OUT/(name+'.dot')).write_text(dot,encoding='utf-8')
    js='''import fs from "node:fs"; import * as Viz from "@viz-js/viz";
    const items=JSON.parse(fs.readFileSync(0,"utf8"));const viz=await Viz.instance();
    for (const item of items) fs.writeFileSync(item.output,viz.renderString(item.dot,{format:"svg"}));
    console.log("Diagramas SVG: "+items.length+"; Graphviz "+viz.graphvizVersion);'''
    result=subprocess.run([shutil.which('node'),'--input-type=module','-e',js],cwd=VIZ,
        input=json.dumps([dict(dot=dot,output=str(OUT/(name+'.svg'))) for name,dot in graphs.items()]),text=True,capture_output=True,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stderr)
    print(result.stdout)
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport={'width':2400,'height':2000},device_scale_factor=2)
        for name in graphs:
            page.goto((OUT/(name+'.svg')).as_uri());page.locator('svg').screenshot(path=str(OUT/(name+'.png')))
        browser.close()


if __name__=='__main__':run()
