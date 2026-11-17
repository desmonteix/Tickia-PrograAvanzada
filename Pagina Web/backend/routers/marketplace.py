"""Compras de demostración y publicaciones: sin pasarelas ni movimientos de dinero."""
from decimal import Decimal
import math
from pathlib import Path
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Form, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import User, AuditLog
from ..marketplace_models import LocalProduct, LocalVariant, LocalOrder, LocalCategory
from ..marketplace import cents
from ..dataset import LOCAL_DIR, open_dataset
from .dataset import search_key

router = APIRouter(prefix="/api/marketplace", tags=["marketplace local"])
CATALOG = """FROM local_products p LEFT JOIN (
    SELECT id_producto, SUM(stock) AS stock FROM local_variants GROUP BY id_producto
) inventory ON inventory.id_producto=p.id_producto"""


def product_view(row):
    data = dict(row)
    data["precio"] = data.pop("precio_centimos") / 100
    data["reputacion"] = float(data["reputacion"])
    data["estrellas"] = float(data["estrellas"]) if data["estrellas"] is not None else None
    data["owner_id"] = str(uuid.UUID(str(data["owner_id"]))) if data["owner_id"] else None
    data.pop("search_text", None)
    return data


def order_view(order):
    return {"id": str(order.id), "id_producto": order.id_producto, "id_variante": order.id_variante,
            "titulo": order.titulo, "vendedor": order.vendedor, "variante": order.variante,
            "cantidad": order.cantidad, "precio_unit_centimos": order.precio_unit_centimos,
            "total_centimos": order.total_centimos, "created_at": order.created_at,
            "estado": "CONFIRMADO", "simulado": True}


@router.get("/products")
def products(q: Annotated[str, Query(max_length=120)] = "", category: Annotated[int | None, Query(ge=1)] = None,
             sort: Literal["id", "price_asc", "price_desc", "rating", "stock", "newest"] = "id",
             in_stock: bool = False, page: Annotated[int, Query(ge=1)] = 1,
             page_size: Annotated[int, Query(ge=1, le=60)] = 24, db: Session = Depends(get_db)):
    order = {"id": "p.id_producto", "price_asc": "p.precio_centimos, p.id_producto",
             "price_desc": "p.precio_centimos DESC, p.id_producto", "rating": "CAST(p.reputacion AS REAL) DESC, p.id_producto",
             "stock": "stock DESC, p.id_producto", "newest": "p.id_producto DESC"}[sort]
    conditions, params = [], {}
    if q.strip():
        conditions.append("instr(p.search_text, :q) > 0")
        params["q"] = search_key(q.strip())
    if category is not None:
        conditions.append("""p.id_categoria IN (WITH RECURSIVE children(id) AS (
            SELECT id_categoria FROM local_categories WHERE id_categoria=:category
            UNION SELECT c.id_categoria FROM local_categories c JOIN children ON c.id_padre=children.id
        ) SELECT id FROM children)""")
        params["category"] = category
    if in_stock:
        conditions.append("COALESCE(stock,0) > 0")
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    total = db.execute(text("SELECT COUNT(*) " + CATALOG + where), params).scalar_one()
    params.update(limit=page_size, offset=(page - 1) * page_size)
    rows = db.execute(text("SELECT p.*, COALESCE(stock,0) AS stock " + CATALOG + where +
                           f" ORDER BY {order} LIMIT :limit OFFSET :offset"), params).mappings()
    return {"items": [product_view(row) for row in rows], "total": total,
            "page": page, "pages": math.ceil(total / page_size)}


@router.get("/products/{product_id}")
def product_detail(product_id: int, db: Session = Depends(get_db)):
    row = db.execute(text("SELECT p.*, COALESCE(stock,0) AS stock " + CATALOG + " WHERE p.id_producto=:id"),
                     {"id": product_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "Producto no encontrado.")
    result = product_view(row)
    result["variantes"] = [{"id_variante": v.id_variante, "talla": v.talla, "color": v.color, "stock": v.stock}
                          for v in db.query(LocalVariant).filter_by(id_producto=product_id).order_by(LocalVariant.id_variante)]
    result.update(resenas=[], preguntas=[])
    if result["source_product_id"] is not None:
        with open_dataset() as original:
            source_id = result["source_product_id"]
            result["resenas"] = [dict(r) for r in original.execute("""SELECT r.id_resena,r.estrellas,r.comentario,r.fecha,u.nombre AS autor
                FROM resenas r JOIN usuarios u USING(id_usuario) WHERE r.id_producto=? ORDER BY r.fecha DESC,r.id_resena DESC LIMIT 10""", (source_id,))]
            result["preguntas"] = [dict(r) for r in original.execute("""SELECT p.id_pregunta,p.texto,p.respuesta,p.fecha,u.nombre AS autor
                FROM preguntas p JOIN usuarios u USING(id_usuario) WHERE p.id_producto=? ORDER BY p.fecha DESC,p.id_pregunta DESC LIMIT 10""", (source_id,))]
    return result


def save_photo(photo):
    if photo is None:
        return None
    from ..qr_utils import MAX_FILE_BYTES, validate_image_file
    import cv2
    import numpy as np
    content = photo.file.read(MAX_FILE_BYTES + 1)
    if not validate_image_file(content, photo.content_type):
        raise HTTPException(422, "La foto debe ser PNG o JPEG y pesar como máximo 5 MB.")
    try:
        image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[0] * image.shape[1] > 20_000_000:
            raise ValueError("Dimensiones inválidas")
        success, encoded = cv2.imencode(".jpg", image)
        if not success:
            raise ValueError("Imagen inválida")
    except (ValueError, cv2.error):
        raise HTTPException(422, "No se pudo leer la foto. Usa un archivo PNG o JPEG válido.")
    filename = uuid.uuid4().hex + ".jpg"
    directory = LOCAL_DIR / "product-images"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(encoded.tobytes())
    return filename


@router.post("/products", status_code=201)
def publish_product(titulo: Annotated[str, Form(min_length=3, max_length=160)],
                    precio: Annotated[Decimal, Form(gt=0, le=1000000, decimal_places=2, allow_inf_nan=False)],
                    stock: Annotated[int, Form(ge=1, le=1000000)],
                    id_categoria: Annotated[int, Form(ge=1)],
                    descripcion: Annotated[str, Form(max_length=2000)] = "",
                    talla: Annotated[str, Form(max_length=60)] = "Única",
                    color: Annotated[str, Form(max_length=60)] = "No especificado",
                    foto: UploadFile | None = File(default=None),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    category = db.get(LocalCategory, id_categoria)
    if category is None or len(titulo.strip()) < 3:
        raise HTTPException(422, "Revisa el título y selecciona una categoría válida.")
    seller = user.full_name or "Vendedor " + str(user.id)[:8]
    filename = save_photo(foto)
    try:
        product = LocalProduct(owner_id=user.id, titulo=titulo.strip(), descripcion=descripcion.strip(),
            id_categoria=id_categoria, categoria=category.nombre, vendedor=seller, reputacion=str(user.rating),
            precio_centimos=cents(precio), imagen=filename,
            search_text=search_key(titulo.strip() + " " + category.nombre + " " + seller))
        db.add(product)
        db.flush()
        db.add(LocalVariant(id_producto=product.id_producto, talla=talla.strip(), color=color.strip(), stock=stock))
        db.add(AuditLog(user_id=user.id, action="LOCAL_PRODUCT_PUBLISHED", entity_type="product", entity_id=str(product.id_producto)))
        db.commit()
    except Exception:
        db.rollback()
        if filename:
            (LOCAL_DIR / "product-images" / filename).unlink(missing_ok=True)
        raise
    return product_detail(product.id_producto, db)


@router.get("/images/{filename}")
def product_image(filename: str):
    import re
    if not re.fullmatch(r"[0-9a-f]{32}\.jpg", filename):
        raise HTTPException(404, "Imagen no encontrada.")
    path = LOCAL_DIR / "product-images" / filename
    if not path.is_file():
        raise HTTPException(404, "Imagen no encontrada.")
    return FileResponse(path, media_type="image/jpeg")


class PurchaseInput(BaseModel):
    variant_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=100)
    request_id: uuid.UUID


def previous_order(db, user, request):
    row = db.query(LocalOrder).filter_by(buyer_id=user.id, request_id=request.request_id).first()
    if row and (row.id_variante != request.variant_id or row.cantidad != request.quantity):
        raise HTTPException(409, "Esta solicitud ya corresponde a otra compra. Revisa Mis compras.")
    return row


@router.post("/orders", status_code=201)
def buy_product(purchase: PurchaseInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    previous = previous_order(db, user, purchase)
    if previous:
        return order_view(previous)
    variant = db.get(LocalVariant, purchase.variant_id)
    if variant is None:
        raise HTTPException(404, "Variante no encontrada.")
    product = db.get(LocalProduct, variant.id_producto)
    if product.owner_id == user.id:
        raise HTTPException(409, "No puedes comprar tu propio producto.")
    changed = db.execute(update(LocalVariant).where(LocalVariant.id_variante == purchase.variant_id,
        LocalVariant.stock >= purchase.quantity).values(stock=LocalVariant.stock - purchase.quantity))
    if changed.rowcount != 1:
        db.rollback()
        previous = previous_order(db, user, purchase)
        if previous:
            return order_view(previous)
        raise HTTPException(409, "El stock disponible cambió. Revisa la cantidad antes de comprar.")
    order = LocalOrder(buyer_id=user.id, seller_id=product.owner_id, id_producto=product.id_producto,
        id_variante=variant.id_variante, request_id=purchase.request_id, titulo=product.titulo,
        vendedor=product.vendedor, variante=" · ".join(filter(None, (variant.talla, variant.color))),
        cantidad=purchase.quantity, precio_unit_centimos=product.precio_centimos,
        total_centimos=product.precio_centimos * purchase.quantity)
    try:
        db.add(order)
        db.flush()
        db.add(AuditLog(user_id=user.id, action="LOCAL_PRODUCT_PURCHASED", entity_type="local_order", entity_id=str(order.id)))
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = previous_order(db, user, purchase)
        if previous:
            return order_view(previous)
        raise HTTPException(409, "No se pudo confirmar la compra. Revisa Mis compras antes de reintentar.")
    return order_view(order)


@router.get("/my-products")
def my_products(page: Annotated[int, Query(ge=1)] = 1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total = db.query(LocalProduct).filter_by(owner_id=user.id).count()
    rows = db.execute(text("SELECT p.*,COALESCE(stock,0) AS stock " + CATALOG +
        " WHERE p.owner_id=:owner ORDER BY p.id_producto DESC LIMIT 24 OFFSET :offset"),
        {"owner": user.id.hex, "offset": (page - 1) * 24}).mappings()
    return {"items": [product_view(row) for row in rows], "total": total, "page": page, "pages": math.ceil(total / 24)}


def order_history(db, user, seller, page):
    column = LocalOrder.seller_id if seller else LocalOrder.buyer_id
    query = db.query(LocalOrder).filter(column == user.id)
    total = query.count()
    return {"items": [order_view(o) for o in query.order_by(LocalOrder.created_at.desc(), LocalOrder.id.desc()).offset((page-1)*24).limit(24)],
            "total": total, "page": page, "pages": math.ceil(total / 24)}


@router.get("/orders")
def orders(page: Annotated[int, Query(ge=1)] = 1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return order_history(db, user, False, page)


@router.get("/sales")
def sales(page: Annotated[int, Query(ge=1)] = 1, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return order_history(db, user, True, page)
