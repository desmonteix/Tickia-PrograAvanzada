"""Carga inicial de catálogo e inventario; reiniciar nunca restablece el stock."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import insert, select
from .dataset import DATASET_DB, open_dataset
from .marketplace_models import LocalCategory, LocalProduct, LocalVariant, LocalSeed
from .routers.dataset import search_key


def cents(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def seed_marketplace(engine, source=DATASET_DB):
    with engine.begin() as target:
        if target.execute(select(LocalSeed.id).where(LocalSeed.id == 1)).first():
            return
        with open_dataset(source) as original:
            target.execute(insert(LocalCategory), [dict(r) for r in original.execute("SELECT * FROM categorias")])
            products = []
            now = datetime.now(timezone.utc)
            for row in original.execute("SELECT * FROM catalogo_productos ORDER BY id_producto"):
                products.append(dict(id_producto=row["id_producto"], source_product_id=row["id_producto"],
                    titulo=row["titulo"], descripcion="", id_categoria=row["id_categoria"], categoria=row["categoria"],
                    vendedor=row["vendedor"], reputacion=str(row["reputacion"]), distrito=row["distrito"],
                    provincia=row["provincia"], precio_centimos=cents(row["precio"]),
                    estrellas=str(row["estrellas"]) if row["estrellas"] is not None else None,
                    total_resenas=row["total_resenas"], created_at=now,
                    search_text=search_key(row["titulo"] + " " + row["categoria"] + " " + row["vendedor"])))
            if products:
                target.execute(insert(LocalProduct), products)
            variants = [dict(r) for r in original.execute("SELECT * FROM variantes")]
            if variants:
                target.execute(insert(LocalVariant), variants)
        target.execute(insert(LocalSeed).values(id=1))
