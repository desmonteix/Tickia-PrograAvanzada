"""Catálogo y exploración de las quince tablas operativas en MySQL."""
import math
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from .database import get_db, rows, row
from .auth import optional_user, get_current_user
from .bootstrap import TABLES

router = APIRouter(prefix='/api', tags=['catálogo MySQL'])
CATALOG = '''FROM productos p JOIN categorias c USING(id_categoria)
    JOIN vendedores s USING(id_vendedor) JOIN usuarios u ON s.id_usuario=u.id_usuario
    JOIN v_distritos d USING(id_distrito)
    LEFT JOIN (SELECT id_producto,SUM(stock) stock FROM variantes GROUP BY id_producto) inv USING(id_producto)
    LEFT JOIN (SELECT id_producto,AVG(estrellas) estrellas,COUNT(*) total_resenas FROM resenas GROUP BY id_producto) r USING(id_producto)'''
FIELDS = '''p.*,c.nombre categoria,s.razon_social vendedor,s.reputacion,u.auth_uuid owner_id,
    d.nombre distrito,d.provincia,COALESCE(inv.stock,0) stock,r.estrellas,COALESCE(r.total_resenas,0) total_resenas,
    EXISTS(SELECT 1 FROM favoritos f WHERE f.id_producto=p.id_producto AND f.id_usuario=:viewer) favorito'''


def product_view(record):
    for key in ('precio','reputacion','estrellas'):
        if record.get(key) is not None:
            record[key] = float(record[key])
    record['favorito'] = bool(record.get('favorito'))
    return record


def list_products(db, user, q='', category=None, sort='id', in_stock=False, page=1, page_size=24, owned=False, favorites=False):
    order = {'id':'p.id_producto','price_asc':'p.precio,p.id_producto','price_desc':'p.precio DESC,p.id_producto',
             'rating':'s.reputacion DESC,p.id_producto','stock':'stock DESC,p.id_producto','newest':'p.id_producto DESC'}[sort]
    conditions, params = [], {'viewer': user.id_usuario if user else 0}
    if q.strip():
        conditions.append("LOCATE(:q,CONCAT_WS(' ',p.titulo,c.nombre,s.razon_social))>0")
        params['q'] = q.strip()
    if category is not None:
        conditions.append('''p.id_categoria IN (WITH RECURSIVE ramas AS (
            SELECT id_categoria FROM categorias WHERE id_categoria=:category
            UNION ALL SELECT c.id_categoria FROM categorias c JOIN ramas r ON c.id_padre=r.id_categoria
        ) SELECT id_categoria FROM ramas)''')
        params['category'] = category
    if in_stock:
        conditions.append('COALESCE(inv.stock,0)>0')
    if owned:
        conditions.append('s.id_usuario=:viewer')
    if favorites:
        conditions.append('EXISTS(SELECT 1 FROM favoritos f WHERE f.id_producto=p.id_producto AND f.id_usuario=:viewer)')
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    total = row(db,'SELECT COUNT(*) total '+CATALOG+where,params)['total']
    params.update(limit=page_size,offset=(page-1)*page_size)
    items = rows(db,'SELECT '+FIELDS+' '+CATALOG+where+' ORDER BY '+order+' LIMIT :limit OFFSET :offset',params)
    return dict(items=[product_view(record) for record in items], total=total, page=page, pages=math.ceil(total/page_size))


@router.get('/marketplace/products')
def products(q: Annotated[str,Query(max_length=120)]='',category: Annotated[int|None,Query(ge=1)]=None,
             sort: Literal['id','price_asc','price_desc','rating','stock','newest']='id', in_stock: bool=False,
             page: Annotated[int,Query(ge=1,le=1000000)]=1,page_size: Annotated[int,Query(ge=1,le=60)]=24,
             favorites: bool=False,user=Depends(optional_user),db=Depends(get_db, scope="function")):
    return list_products(db,user,q,category,sort,in_stock,page,page_size,favorites=favorites)


@router.get('/marketplace/my-products')
def my_products(page: Annotated[int,Query(ge=1,le=1000000)]=1,user=Depends(get_current_user),db=Depends(get_db, scope="function")):
    return list_products(db,user,sort='newest',page=page,owned=True)


@router.get('/marketplace/products/{product_id}')
def product_detail(product_id: int,user=Depends(optional_user),db=Depends(get_db, scope="function")):
    result = row(db,'SELECT '+FIELDS+' '+CATALOG+' WHERE p.id_producto=:id',dict(id=product_id,viewer=user.id_usuario if user else 0))
    if result is None:
        raise HTTPException(404,'Producto no encontrado.')
    result = product_view(result)
    result['variantes'] = rows(db,'SELECT * FROM variantes WHERE id_producto=:id ORDER BY id_variante',{'id':product_id})
    result['resenas'] = rows(db,'''SELECT r.id_resena,r.estrellas,r.comentario,r.fecha,u.nombre autor FROM resenas r
        JOIN usuarios u USING(id_usuario) WHERE r.id_producto=:id ORDER BY r.fecha DESC,r.id_resena DESC LIMIT 10''',{'id':product_id})
    result['preguntas'] = rows(db,'''SELECT p.id_pregunta,p.texto,p.respuesta,p.fecha,u.nombre autor FROM preguntas p
        JOIN usuarios u USING(id_usuario) WHERE p.id_producto=:id ORDER BY p.fecha DESC,p.id_pregunta DESC LIMIT 10''',{'id':product_id})
    result['ya_resenado'] = bool(user and row(db,'SELECT 1 FROM resenas WHERE id_producto=:id AND id_usuario=:user LIMIT 1',dict(id=product_id,user=user.id_usuario)))
    result['puede_resenar'] = bool(user and not result['ya_resenado'] and row(db,'''SELECT 1 FROM pedidos pe JOIN pedido_detalle de USING(id_pedido)
        JOIN variantes va USING(id_variante) WHERE pe.id_usuario=:user AND pe.estado='entregado' AND va.id_producto=:id LIMIT 1''',
        dict(user=user.id_usuario,id=product_id)))
    return result


@router.get('/dataset/categories')
def categories(db=Depends(get_db, scope="function")):
    return rows(db,'''SELECT c.*,COUNT(p.id_producto) productos FROM categorias c LEFT JOIN productos p USING(id_categoria)
        GROUP BY c.id_categoria ORDER BY c.nombre,c.id_categoria''')


@router.get('/dataset/summary')
def summary(db=Depends(get_db, scope="function")):
    tables = [dict(table=name,file=spec['file'],rows=row(db,'SELECT COUNT(*) n FROM `'+name+'`')['n']) for name,spec in TABLES.items()]
    tables.extend(dict(table=name,file='Normalizada desde 01_distritos.csv',rows=row(db,'SELECT COUNT(*) n FROM '+name)['n']) for name in ('departamentos','provincias'))
    return dict(tables=tables,total_records=sum(item['rows'] for item in tables),missing_files=[],database='MySQL')


@router.get('/dataset/tables/{table}')
def table_rows(table: str,page: Annotated[int,Query(ge=1,le=1000000)]=1,page_size: Annotated[int,Query(ge=1,le=100)]=25,db=Depends(get_db, scope="function")):
    if table not in TABLES:
        raise HTTPException(404,'Tabla no encontrada.')
    columns = [column for column in TABLES[table]['columns'] if column!='email']
    fields = ','.join('`'+column+'`' for column in columns)
    order = ','.join('`'+column+'`' for column in columns if column.startswith('id_'))
    source = 'v_distritos' if table=='distritos' else table
    items = rows(db,'SELECT '+fields+' FROM `'+source+'` ORDER BY '+order+' LIMIT :limit OFFSET :offset',
                 dict(limit=page_size,offset=(page-1)*page_size))
    total = row(db,'SELECT COUNT(*) n FROM `'+table+'`')['n']
    return dict(columns=columns,items=items,total=total,page=page,pages=math.ceil(total/page_size))


@router.get('/marketplace/districts')
def districts(db=Depends(get_db, scope="function")):
    return rows(db,'SELECT * FROM v_distritos ORDER BY departamento,provincia,nombre')


@router.get('/marketplace/couriers')
def couriers(db=Depends(get_db, scope="function")):
    return rows(db,'SELECT * FROM couriers ORDER BY id_courier')


@router.get('/marketplace/coupons')
def coupons(db=Depends(get_db, scope="function")):
    return rows(db,"SELECT * FROM cupones WHERE vence>=DATE(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','-05:00')) ORDER BY vence,id_cupon LIMIT 30")
