"""Estado mutable del marketplace académico, separado de los CSV originales."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from .database import Base


class LocalCategory(Base):
    __tablename__ = "local_categories"
    id_categoria = Column(Integer, primary_key=True)
    id_padre = Column(Integer, nullable=True)
    nombre = Column(String(160), nullable=False)


class LocalProduct(Base):
    __tablename__ = "local_products"
    id_producto = Column(Integer, primary_key=True, autoincrement=True)
    source_product_id = Column(Integer, unique=True, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    titulo = Column(String(160), nullable=False)
    descripcion = Column(Text, nullable=False, default="")
    id_categoria = Column(Integer, ForeignKey("local_categories.id_categoria"), nullable=False, index=True)
    categoria = Column(String(160), nullable=False)
    vendedor = Column(String(160), nullable=False)
    reputacion = Column(String(10), nullable=False)
    distrito = Column(String(160), nullable=False, default="")
    provincia = Column(String(160), nullable=False, default="")
    precio_centimos = Column(Integer, nullable=False)
    estrellas = Column(String(30), nullable=True)
    total_resenas = Column(Integer, nullable=False, default=0)
    imagen = Column(String(100), nullable=True)
    search_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (CheckConstraint("precio_centimos > 0", name="chk_local_price"),)


class LocalVariant(Base):
    __tablename__ = "local_variants"
    id_variante = Column(Integer, primary_key=True, autoincrement=True)
    id_producto = Column(Integer, ForeignKey("local_products.id_producto"), nullable=False, index=True)
    talla = Column(String(60), nullable=True)
    color = Column(String(60), nullable=True)
    stock = Column(Integer, nullable=False)
    __table_args__ = (CheckConstraint("stock >= 0", name="chk_local_stock"),)


class LocalOrder(Base):
    __tablename__ = "local_orders"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    id_producto = Column(Integer, ForeignKey("local_products.id_producto"), nullable=False)
    id_variante = Column(Integer, ForeignKey("local_variants.id_variante"), nullable=False)
    request_id = Column(UUID(as_uuid=True), nullable=False)
    titulo = Column(String(160), nullable=False)
    vendedor = Column(String(160), nullable=False)
    variante = Column(String(160), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unit_centimos = Column(Integer, nullable=False)
    total_centimos = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (UniqueConstraint("buyer_id", "request_id", name="uq_local_purchase_request"),
                     CheckConstraint("cantidad > 0 AND precio_unit_centimos > 0 AND total_centimos = cantidad * precio_unit_centimos", name="chk_local_order_amount"))


class LocalSeed(Base):
    __tablename__ = "local_marketplace_seed"
    id = Column(Integer, primary_key=True)
