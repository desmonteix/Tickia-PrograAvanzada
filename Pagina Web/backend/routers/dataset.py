"""Catálogo de productos del dataset fijo; no expone operaciones de escritura."""
import math
import sqlite3
import unicodedata
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from ..dataset import TABLES, open_dataset

router = APIRouter(prefix="/api/dataset", tags=["dataset académico"])


def search_key(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.casefold()) if not unicodedata.combining(c))


def get_dataset_db():
    with open_dataset() as db:
        db.create_function("search_key", 1, search_key, deterministic=True)
        yield db


@router.get("/summary")
def summary(db: sqlite3.Connection = Depends(get_dataset_db)):
    tables = [dict(row) for row in db.execute(
        "SELECT table_name AS 'table', file, rows, sha256 FROM dataset_manifest ORDER BY file")]
    return {"tables": tables, "total_records": sum(t["rows"] for t in tables),
            "missing_files": ["10_pagos.csv", "15_favoritos.csv"]}


@router.get("/categories")
def categories(db: sqlite3.Connection = Depends(get_dataset_db)):
    return [dict(row) for row in db.execute("""SELECT c.*, COUNT(p.id_producto) AS productos
        FROM categorias c LEFT JOIN productos p USING (id_categoria)
        GROUP BY c.id_categoria ORDER BY c.nombre, c.id_categoria""")]


@router.get("/products")
def products(
    q: Annotated[str, Query(max_length=120)] = "",
    category: Annotated[int | None, Query(ge=1)] = None,
    sort: Literal["id", "price_asc", "price_desc", "rating", "stock"] = "id",
    in_stock: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=60)] = 24,
    db: sqlite3.Connection = Depends(get_dataset_db),
):
    order = {"id": "id_producto", "price_asc": "precio, id_producto",
             "price_desc": "precio DESC, id_producto", "rating": "reputacion DESC, id_producto",
             "stock": "stock DESC, id_producto"}[sort]
    conditions, params = [], {}
    if q.strip():
        conditions.append("instr(search_key(titulo || ' ' || categoria || ' ' || vendedor), :q) > 0")
        params["q"] = search_key(q.strip())
    if category is not None:
        conditions.append("""id_categoria IN (WITH RECURSIVE children(id) AS (
            SELECT id_categoria FROM categorias WHERE id_categoria=:category
            UNION SELECT c.id_categoria FROM categorias c JOIN children ON c.id_padre=children.id
        ) SELECT id FROM children)""")
        params["category"] = category
    if in_stock:
        conditions.append("stock > 0")
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    total = db.execute(f"SELECT COUNT(*) FROM catalogo_productos {where}", params).fetchone()[0]
    params.update(limit=page_size, offset=(page - 1) * page_size)
    items = [dict(row) for row in db.execute(
        f"SELECT * FROM catalogo_productos {where} ORDER BY {order} LIMIT :limit OFFSET :offset", params)]
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": math.ceil(total / page_size)}


@router.get("/products/{product_id}")
def product_detail(product_id: int, db: sqlite3.Connection = Depends(get_dataset_db)):
    row = db.execute("SELECT * FROM catalogo_productos WHERE id_producto=?", (product_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Producto no encontrado.")
    result = dict(row)
    result["variantes"] = [dict(r) for r in db.execute(
        "SELECT * FROM variantes WHERE id_producto=? ORDER BY id_variante", (product_id,))]
    result["resenas"] = [dict(r) for r in db.execute("""SELECT r.id_resena, r.estrellas,
        r.comentario, r.fecha, u.nombre AS autor FROM resenas r JOIN usuarios u USING (id_usuario)
        WHERE r.id_producto=? ORDER BY r.fecha DESC, r.id_resena DESC LIMIT 10""", (product_id,))]
    result["preguntas"] = [dict(r) for r in db.execute("""SELECT p.id_pregunta, p.texto,
        p.respuesta, p.fecha, u.nombre AS autor FROM preguntas p JOIN usuarios u USING (id_usuario)
        WHERE p.id_producto=? ORDER BY p.fecha DESC, p.id_pregunta DESC LIMIT 10""", (product_id,))]
    return result


@router.get("/tables/{table}")
def table_rows(table: str, page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=100)] = 25,
               db: sqlite3.Connection = Depends(get_dataset_db)):
    if table not in TABLES:
        raise HTTPException(404, "Tabla no encontrada.")
    # No se exponen correos de usuarios en el explorador público.
    columns = [column for column in TABLES[table]["columns"] if column != "email"]
    fields = ", ".join(f'"{column}"' for column in columns)
    rows = [dict(r) for r in db.execute(
        f'SELECT {fields} FROM "{table}" ORDER BY rowid LIMIT ? OFFSET ?',
        (page_size, (page - 1) * page_size))]
    total = db.execute("SELECT rows FROM dataset_manifest WHERE table_name=?", (table,)).fetchone()[0]
    return {"columns": columns, "items": rows, "total": total, "page": page,
            "page_size": page_size, "pages": math.ceil(total / page_size)}
