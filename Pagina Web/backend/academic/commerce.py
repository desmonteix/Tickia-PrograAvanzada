"""Carrito multítem, cotización con patrones y pedidos transaccionales en MySQL."""
from collections import defaultdict
from datetime import timezone
from decimal import Decimal
import hashlib
import json
import math
import uuid
from typing import Annotated, Literal
import pymysql
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from .database import engine, get_db, row, rows
from .auth import optional_user, get_current_user
from .patterns import OrderBuilder, OrderContext, SHIPPING_STRATEGIES

router = APIRouter(prefix='/api/marketplace', tags=['pedidos multítem'])


class CartItem(BaseModel):
    variant_id: int = Field(ge=1, strict=True)
    quantity: int = Field(ge=1, le=100, strict=True)


class CartInput(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=20)
    coupon_code: str | None = Field(default=None, max_length=80)
    courier_id: int = Field(default=1, ge=1)
    district_id: int = Field(default=1, ge=1)
    payment_method: Literal['tarjeta_demo','yape_demo','transferencia_demo'] = 'yape_demo'


class CheckoutInput(CartInput):
    request_id: uuid.UUID
    expected_total_centimos: int = Field(ge=0, le=999999999999)


def placeholders(values):
    return ','.join(':id'+str(i) for i in range(len(values))), {'id'+str(i): value for i,value in enumerate(values)}


def quote_cart(data, user, db):
    quantities = defaultdict(int)
    for item in data.items:
        quantities[item.variant_id] += item.quantity
    fields, params = placeholders(sorted(quantities))
    found = rows(db, '''SELECT va.id_variante,va.stock,va.talla,va.color,p.id_producto,p.titulo,p.precio,p.imagen,
        s.id_usuario owner FROM variantes va JOIN productos p USING(id_producto)
        JOIN vendedores s USING(id_vendedor) WHERE va.id_variante IN (''' + fields + ')', params)
    if len(found) != len(quantities):
        raise HTTPException(404,'Una variante del carrito ya no existe.')
    builder, items = OrderBuilder(), []
    try:
        for record in sorted(found,key=lambda item:item['id_variante']):
            quantity = quantities[record['id_variante']]
            if user and record['owner'] == user.id_usuario:
                raise HTTPException(409,'No puedes comprar tus propios productos.')
            if quantity > record['stock']:
                raise HTTPException(409,'Stock insuficiente para '+record['titulo']+'.')
            builder.add_item(record['id_variante'],quantity,record['precio'])
            items.append(dict(variant_id=record['id_variante'],id_producto=record['id_producto'],titulo=record['titulo'],
                quantity=quantity,precio_unit_centimos=int(record['precio']*100),stock=record['stock'],
                variante=' · '.join(filter(None,(record['talla'],record['color']))),imagen=record['imagen']))
        coupon = None
        if data.coupon_code and data.coupon_code.strip():
            coupon = row(db,"SELECT * FROM cupones WHERE codigo=:code AND vence>=DATE(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','-05:00')) ORDER BY id_cupon LIMIT 1",{'code':data.coupon_code.strip()})
            if not coupon:
                raise HTTPException(422,'El cupón no existe o venció.')
            builder.with_coupon(coupon['codigo'],coupon['descuento_pct'])
        courier = row(db,'SELECT * FROM couriers WHERE id_courier=:id',{'id':data.courier_id})
        district = row(db,'SELECT * FROM distritos WHERE id_distrito=:id',{'id':data.district_id})
        if not courier or not district or courier['estrategia'] not in SHIPPING_STRATEGIES:
            raise HTTPException(422,'Selecciona un courier y un distrito válidos.')
        draft = builder.shipping(SHIPPING_STRATEGIES[courier['estrategia']](),courier['costo_base'],district['departamento']).build()
    except ValueError as error:
        raise HTTPException(422,str(error))
    return dict(items=items,subtotal_centimos=int(draft.subtotal*100),descuento_centimos=int(draft.discount*100),
        envio_centimos=int(draft.shipping_cost*100),total_centimos=int(draft.total*100),
        descuentos=[dict(nombre=label,centimos=int(amount*100)) for label,amount in draft.discounts],
        coupon_id=coupon['id_cupon'] if coupon else None,courier=courier,destino=district,simulado=True)


@router.post('/quote')
def quote(data: CartInput,user=Depends(optional_user),db=Depends(get_db, scope="function")):
    return quote_cart(data,user,db)


def fingerprint(data):
    quantities = defaultdict(int)
    for item in data.items:
        quantities[item.variant_id] += item.quantity
    payload = data.model_dump(exclude={'items','request_id'})
    payload['items'] = sorted(quantities.items())
    payload['coupon_code'] = (data.coupon_code or '').strip().casefold()
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def order_views(db, identifiers):
    if not identifiers:
        return []
    fields, params = placeholders(identifiers)
    orders = rows(db,'SELECT * FROM pedidos WHERE id_pedido IN ('+fields+') ORDER BY fecha DESC,id_pedido DESC',params)
    details = rows(db,'''SELECT de.*,p.id_producto,p.titulo,s.razon_social vendedor,va.talla,va.color
        FROM pedido_detalle de JOIN variantes va USING(id_variante) JOIN productos p USING(id_producto)
        JOIN vendedores s USING(id_vendedor) WHERE de.id_pedido IN ('''+fields+') ORDER BY de.id_variante',params)
    payments = rows(db,'SELECT * FROM pagos WHERE id_pedido IN ('+fields+') ORDER BY id_pago',params)
    shipments = rows(db,'''SELECT e.*,c.nombre courier FROM envios e JOIN couriers c USING(id_courier)
        WHERE e.id_pedido IN ('''+fields+') ORDER BY e.id_envio',params)
    result = []
    for order in orders:
        items = [dict(id_producto=d['id_producto'],id_variante=d['id_variante'],titulo=d['titulo'],vendedor=d['vendedor'],
            cantidad=d['cantidad'],precio_unit_centimos=int(d['precio_unit']*100),
            variante=' · '.join(filter(None,(d['talla'],d['color'])))) for d in details if d['id_pedido']==order['id_pedido']]
        destination = json.loads(order['destino']) if isinstance(order['destino'],str) else order['destino']
        result.append(dict(id=str(order['id_pedido']),id_pedido=order['id_pedido'],items=items,
            titulo=items[0]['titulo'] if len(items)==1 else f"Pedido de {len(items)} artículos",
            vendedor=', '.join(sorted(set(item['vendedor'] for item in items))),
            variante=items[0]['variante'] if len(items)==1 else 'Varias variantes',cantidad=sum(i['cantidad'] for i in items),
            total_centimos=int(order['total']*100),subtotal_centimos=int((order['subtotal'] or order['total'])*100),
            descuento_centimos=int(order['descuento']*100),envio_centimos=int(order['costo_envio']*100),
            created_at=order['fecha'].replace(tzinfo=timezone.utc),estado=order['estado'],simulado=True,destino=destination,
            pagos=[p for p in payments if p['id_pedido']==order['id_pedido']],
            envios=[s for s in shipments if s['id_pedido']==order['id_pedido']]))
    return result


def can_access(db,user,order_id):
    return row(db,'''SELECT pe.* FROM pedidos pe WHERE pe.id_pedido=:id AND (pe.id_usuario=:user OR EXISTS(
        SELECT 1 FROM pedido_detalle de JOIN variantes va USING(id_variante) JOIN productos p USING(id_producto)
        JOIN vendedores s USING(id_vendedor) WHERE de.id_pedido=pe.id_pedido AND s.id_usuario=:user))''',
        dict(id=order_id,user=user.id_usuario))


@router.get('/orders/{order_id}')
def order_detail(order_id:int,user=Depends(get_current_user),db=Depends(get_db, scope="function")):
    if not can_access(db,user,order_id):
        raise HTTPException(404,'Pedido no encontrado.')
    return order_views(db,[order_id])[0]


@router.post('/orders',status_code=201)
def checkout(data:CheckoutInput,user=Depends(get_current_user),db=Depends(get_db, scope="function")):
    digest = fingerprint(data)
    previous = row(db,'SELECT id_pedido,solicitud_hash FROM pedidos WHERE id_usuario=:user AND solicitud_uuid=:request',
                   dict(user=user.id_usuario,request=str(data.request_id)))
    if previous:
        if previous['solicitud_hash'] != digest:
            raise HTTPException(409,'Esta solicitud ya corresponde a otro pedido.')
        return order_views(db,[previous['id_pedido']])[0]
    bill = quote_cart(data,user,db)
    if bill['total_centimos'] != data.expected_total_centimos:
        raise HTTPException(409,'La cotización cambió. Revisa el total antes de confirmar.')
    state = OrderContext('pendiente').transition('pagado')
    connection = engine.raw_connection()
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute('CALL confirmar_pedido(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (user.id_usuario,str(data.request_id),digest,json.dumps([item.model_dump() for item in data.items]),
                 bill['coupon_id'],data.courier_id,data.district_id,data.payment_method,Decimal(data.expected_total_centimos)/100))
            outcome = cursor.fetchone()
            while cursor.nextset():
                pass
        connection.commit()
    except pymysql.MySQLError as error:
        connection.rollback()
        code = error.args[0]
        if code == 1644:
            raise HTTPException(409,error.args[1])
        if code in (1213,1205,1062):
            raise HTTPException(409,'El inventario está ocupado. Reintenta la misma solicitud.')
        raise HTTPException(503,'No se pudo confirmar el pedido. Revisa Mis compras antes de reintentar.')
    finally:
        connection.close()
    if outcome is None or outcome['estado'] not in (state.name,'enviado','entregado'):
        raise HTTPException(503,'No se pudo verificar el estado del pedido.')
    return order_views(db,[outcome['id_pedido']])[0]


def history(db,user,seller,page):
    condition = '''EXISTS(SELECT 1 FROM pedido_detalle de JOIN variantes va USING(id_variante)
        JOIN productos pr USING(id_producto) JOIN vendedores s USING(id_vendedor)
        WHERE de.id_pedido=p.id_pedido AND s.id_usuario=:user)''' if seller else 'p.id_usuario=:user'
    params = dict(user=user.id_usuario,offset=(page-1)*24)
    total = row(db,'SELECT COUNT(*) n FROM pedidos p WHERE '+condition,params)['n']
    identifiers = [r['id_pedido'] for r in rows(db,'SELECT p.id_pedido FROM pedidos p WHERE '+condition+
        ' ORDER BY p.fecha DESC,p.id_pedido DESC LIMIT 24 OFFSET :offset',params)]
    return dict(items=order_views(db,identifiers),total=total,page=page,pages=math.ceil(total/24))


@router.get('/orders')
def orders(page:Annotated[int,Query(ge=1,le=1000000)]=1,user=Depends(get_current_user),db=Depends(get_db, scope="function")):
    return history(db,user,False,page)


@router.get('/sales')
def sales(page:Annotated[int,Query(ge=1,le=1000000)]=1,user=Depends(get_current_user),db=Depends(get_db, scope="function")):
    return history(db,user,True,page)


class Transition(BaseModel):
    next_state: Literal['enviado','entregado']


@router.post('/orders/{order_id}/status')
def advance(order_id:int,data:Transition,user=Depends(get_current_user),db=Depends(get_db, scope="function")):
    allowed = can_access(db,user,order_id)
    if not allowed:
        raise HTTPException(404,'Pedido no encontrado.')
    if data.next_state == 'entregado' and allowed['id_usuario'] != user.id_usuario:
        raise HTTPException(403,'Solo el comprador puede confirmar la recepción.')
    current = row(db,'SELECT estado FROM pedidos WHERE id_pedido=:id FOR UPDATE',{'id':order_id})
    if current['estado'] != data.next_state:
        try:
            OrderContext(current['estado']).transition(data.next_state)
        except ValueError as error:
            raise HTTPException(409,str(error))
        db.execute(text('UPDATE pedidos SET estado=:state WHERE id_pedido=:id'),dict(state=data.next_state,id=order_id))
        field = 'fecha_envio' if data.next_state=='enviado' else 'fecha_entrega'
        db.execute(text('UPDATE envios SET '+field+'=UTC_TIMESTAMP() WHERE id_pedido=:id AND '+field+' IS NULL'),{'id':order_id})
    return order_views(db,[order_id])[0]
