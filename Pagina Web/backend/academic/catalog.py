"""Catálogo y exploración de las quince tablas operativas en MySQL."""
import math
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from .database import get_db
from .repositories import ProductRepository
from .auth import optional_user, get_current_user
from .bootstrap import TABLES

router = APIRouter(prefix='/api', tags=['catálogo MySQL'])


def product_view(record):
    for key in ('precio','reputacion','estrellas'):
        if record.get(key) is not None:
            record[key] = float(record[key])
    record['favorito'] = bool(record.get('favorito'))
    return record


def list_products(db, user, q='', category=None, sort='id', in_stock=False, page=1, page_size=24, owned=False, favorites=False):
    items,total = ProductRepository(db).search(user.id_usuario if user else 0,q,category,sort,in_stock,page,page_size,owned,favorites)
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
    repository = ProductRepository(db)
    result = repository.detail(product_id,user.id_usuario if user else 0)
    if result is None:
        raise HTTPException(404,'Producto no encontrado.')
    result = product_view(result)
    result['variantes'] = repository.variants(product_id)
    result['resenas'] = repository.latest_reviews(product_id)
    result['preguntas'] = repository.latest_questions(product_id)
    result['ya_resenado'] = bool(user and repository.has_review(user.id_usuario,product_id))
    result['puede_resenar'] = bool(user and not result['ya_resenado'] and repository.received(user.id_usuario,product_id))
    return result


@router.get('/dataset/categories')
def categories(db=Depends(get_db, scope="function")):
    return ProductRepository(db).categories()


@router.get('/dataset/summary')
def summary(db=Depends(get_db, scope="function")):
    repository = ProductRepository(db)
    tables = [dict(table=name,file=spec['file'],rows=repository.count(name)) for name,spec in TABLES.items()]
    tables.extend(dict(table=name,file='Normalizada desde 01_distritos.csv',rows=repository.count(name)) for name in ('departamentos','provincias'))
    return dict(tables=tables,total_records=sum(item['rows'] for item in tables),missing_files=[],database='MySQL')


@router.get('/dataset/tables/{table}')
def table_rows(table: str,page: Annotated[int,Query(ge=1,le=1000000)]=1,page_size: Annotated[int,Query(ge=1,le=100)]=25,db=Depends(get_db, scope="function")):
    if table not in TABLES:
        raise HTTPException(404,'Tabla no encontrada.')
    columns = [column for column in TABLES[table]['columns'] if column!='email']
    repository = ProductRepository(db)
    items = repository.table_page(table,columns,page,page_size)
    total = repository.count(table)
    return dict(columns=columns,items=items,total=total,page=page,pages=math.ceil(total/page_size))


@router.get('/marketplace/districts')
def districts(db=Depends(get_db, scope="function")):
    return ProductRepository(db).districts()


@router.get('/marketplace/couriers')
def couriers(db=Depends(get_db, scope="function")):
    return ProductRepository(db).couriers()


@router.get('/marketplace/coupons')
def coupons(db=Depends(get_db, scope="function")):
    return ProductRepository(db).active_coupons()
