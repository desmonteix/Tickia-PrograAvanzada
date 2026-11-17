"""Importación atómica de los 13 CSV entregados; consultas siempre de solo lectura."""
import csv
import hashlib
import os
from itertools import islice
from pathlib import Path
import sqlite3
import tempfile
from contextlib import contextmanager

SOURCE_DIR = Path(__file__).resolve().parents[2] / "Proyecto_PrograAvanzada"
LOCAL_DIR = Path(os.getenv("TICKIA_LOCAL_DIR", str(SOURCE_DIR / ".local"))).resolve()
DATASET_DB = LOCAL_DIR / "marketplace.sqlite3"

# Los nombres SQL solo proceden de esta lista fija, nunca de una solicitud HTTP.
TABLES = {
    "distritos": {"file": "01_distritos.csv", "columns": "id_distrito nombre provincia departamento".split(),
                  "ddl": "id_distrito INTEGER PRIMARY KEY, nombre TEXT, provincia TEXT, departamento TEXT"},
    "usuarios": {"file": "02_usuarios.csv", "columns": "id_usuario id_distrito nombre email fecha_registro".split(),
                 "ddl": "id_usuario INTEGER PRIMARY KEY, id_distrito INTEGER REFERENCES distritos, nombre TEXT, email TEXT, fecha_registro TEXT"},
    "vendedores": {"file": "03_vendedores.csv", "columns": "id_vendedor id_usuario razon_social reputacion".split(),
                   "ddl": "id_vendedor INTEGER PRIMARY KEY, id_usuario INTEGER REFERENCES usuarios, razon_social TEXT, reputacion REAL"},
    "categorias": {"file": "04_categorias.csv", "columns": "id_categoria id_padre nombre".split(),
                   "ddl": "id_categoria INTEGER PRIMARY KEY, id_padre INTEGER REFERENCES categorias DEFERRABLE INITIALLY DEFERRED, nombre TEXT"},
    "productos": {"file": "05_productos.csv", "columns": "id_producto id_vendedor id_categoria titulo precio".split(),
                  "ddl": "id_producto INTEGER PRIMARY KEY, id_vendedor INTEGER REFERENCES vendedores, id_categoria INTEGER REFERENCES categorias, titulo TEXT, precio REAL"},
    "variantes": {"file": "06_variantes.csv", "columns": "id_variante id_producto talla color stock".split(),
                  "ddl": "id_variante INTEGER PRIMARY KEY, id_producto INTEGER REFERENCES productos, talla TEXT, color TEXT, stock INTEGER"},
    "cupones": {"file": "07_cupones.csv", "columns": "id_cupon codigo descuento_pct vence".split(),
                "ddl": "id_cupon INTEGER PRIMARY KEY, codigo TEXT, descuento_pct INTEGER, vence TEXT"},
    "pedidos": {"file": "08_pedidos.csv", "columns": "id_pedido id_usuario id_cupon fecha estado total".split(),
                "ddl": "id_pedido INTEGER PRIMARY KEY, id_usuario INTEGER REFERENCES usuarios, id_cupon INTEGER REFERENCES cupones, fecha TEXT, estado TEXT, total REAL"},
    "pedido_detalle": {"file": "09_pedido_detalle.csv", "columns": "id_pedido id_variante cantidad precio_unit".split(),
                       "ddl": "id_pedido INTEGER REFERENCES pedidos, id_variante INTEGER REFERENCES variantes, cantidad INTEGER, precio_unit REAL"},
    "couriers": {"file": "11_couriers.csv", "columns": "id_courier nombre costo_base".split(),
                 "ddl": "id_courier INTEGER PRIMARY KEY, nombre TEXT, costo_base REAL"},
    "envios": {"file": "12_envios.csv", "columns": "id_envio id_pedido id_courier fecha_envio fecha_entrega fecha_estimada costo_envio".split(),
               "ddl": "id_envio INTEGER PRIMARY KEY, id_pedido INTEGER REFERENCES pedidos, id_courier INTEGER REFERENCES couriers, fecha_envio TEXT, fecha_entrega TEXT, fecha_estimada TEXT, costo_envio REAL"},
    "resenas": {"file": "13_resenas.csv", "columns": "id_resena id_producto id_usuario estrellas comentario fecha".split(),
                "ddl": "id_resena INTEGER PRIMARY KEY, id_producto INTEGER REFERENCES productos, id_usuario INTEGER REFERENCES usuarios, estrellas INTEGER, comentario TEXT, fecha TEXT"},
    "preguntas": {"file": "14_preguntas.csv", "columns": "id_pregunta id_producto id_usuario texto respuesta fecha".split(),
                  "ddl": "id_pregunta INTEGER PRIMARY KEY, id_producto INTEGER REFERENCES productos, id_usuario INTEGER REFERENCES usuarios, texto TEXT, respuesta TEXT, fecha TEXT"},
}


@contextmanager
def open_dataset(path=DATASET_DB):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def build_dataset(source_dir=SOURCE_DIR, target=DATASET_DB):
    """Reconstruye en un archivo temporal y publica solo tras validar toda la carga."""
    source_dir, target = Path(source_dir), Path(target)
    missing = [spec["file"] for spec in TABLES.values() if not (source_dir / spec["file"]).is_file()]
    if missing:
        raise ValueError("Faltan archivos del dataset: " + ", ".join(missing))
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".sqlite3", delete=False) as temp:
        temporary = Path(temp.name)
    db = sqlite3.connect(temporary)
    manifest = []
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN")
        for table, spec in TABLES.items():
            db.execute(f'CREATE TABLE "{table}" ({spec["ddl"]})')
            source = source_dir / spec["file"]
            count = 0
            with source.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream)
                if next(reader, None) != spec["columns"]:
                    raise ValueError(f"{source.name}: columnas distintas del esquema esperado")
                placeholders = ",".join("?" for _ in spec["columns"])
                while batch := list(islice(reader, 5000)):
                    if any(len(row) != len(spec["columns"]) for row in batch):
                        raise ValueError(f"{source.name}: fila con número de columnas incorrecto")
                    db.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})',
                                   ([value if value != "" else None for value in row] for row in batch))
                    count += len(batch)
            manifest.append({"table": table, "file": source.name, "rows": count,
                             "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("El dataset contiene relaciones inválidas")
        for table, column in (("variantes", "id_producto"), ("resenas", "id_producto"),
                              ("preguntas", "id_producto"), ("pedidos", "id_usuario"),
                              ("pedido_detalle", "id_pedido"), ("envios", "id_pedido")):
            db.execute(f'CREATE INDEX "idx_{table}_{column}" ON "{table}" ("{column}")')
        # Catálogo derivado una sola vez: evita reagrupar todo el histórico en cada búsqueda.
        db.execute("""CREATE TABLE catalogo_productos AS
            SELECT p.*, c.nombre AS categoria, v.razon_social AS vendedor,
                   v.reputacion, d.nombre AS distrito, d.provincia,
                   COALESCE(s.stock, 0) AS stock, r.estrellas,
                   COALESCE(r.total_resenas, 0) AS total_resenas
            FROM productos p JOIN categorias c USING (id_categoria)
            JOIN vendedores v USING (id_vendedor) JOIN usuarios u ON u.id_usuario=v.id_usuario
            JOIN distritos d USING (id_distrito)
            LEFT JOIN (SELECT id_producto, SUM(stock) AS stock FROM variantes GROUP BY id_producto) s USING (id_producto)
            LEFT JOIN (SELECT id_producto, AVG(estrellas) AS estrellas, COUNT(*) AS total_resenas
                       FROM resenas GROUP BY id_producto) r USING (id_producto)""")
        db.execute("CREATE UNIQUE INDEX idx_catalogo_id ON catalogo_productos (id_producto)")
        db.execute("CREATE INDEX idx_catalogo_categoria ON catalogo_productos (id_categoria)")
        db.execute("CREATE TABLE dataset_manifest (table_name TEXT PRIMARY KEY, file TEXT, rows INTEGER, sha256 TEXT)")
        db.executemany("INSERT INTO dataset_manifest VALUES (:table, :file, :rows, :sha256)", manifest)
        db.commit()
        db.close()
        temporary.replace(target)
    finally:
        db.close()
        temporary.unlink(missing_ok=True)
    return manifest


def ensure_dataset():
    if not DATASET_DB.is_file():
        return build_dataset()
    with open_dataset() as db:
        return [dict(row) for row in db.execute(
            "SELECT table_name AS 'table', file, rows, sha256 FROM dataset_manifest ORDER BY file")]


if __name__ == "__main__":
    import json
    print(json.dumps(build_dataset(), ensure_ascii=False, indent=2))
