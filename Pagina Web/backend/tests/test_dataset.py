"""Importación íntegra y consultas del dataset académico, sin servicios externos."""
import csv
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[2]))
from backend.dataset import TABLES, build_dataset, open_dataset


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.source.mkdir()
        self.target = Path(self.temp.name) / "dataset.sqlite3"
        self.rows = {
            "distritos": [[1, "Miraflores", "Lima", "Lima"]],
            "usuarios": [[1, 1, "Ana Pérez", "ana@example.com", "2024-01-01"]],
            "vendedores": [[1, 1, "Tienda de Ana", "4.25"]],
            "categorias": [[1, "", "Tecnología"], [2, 1, "Lámparas"]],
            "productos": [[1, 1, 2, "Lámpara de escritorio", "72.50"]],
            "variantes": [[1, 1, "Única", "Blanco", 3], [2, 1, "Única", "Negro", 2]],
            "cupones": [[1, "PRUEBA", 10, "2026-12-01"]],
            "pedidos": [[1, 1, "", "2024-01-03 08:15:25", "pendiente", "72.50"]],
            "pedido_detalle": [[1, 1, 1, "72.50"]],
            "couriers": [[1, "Courier", "12.00"]],
            "envios": [[1, 1, 1, "", "", "2024-01-10", "12.00"]],
            "resenas": [[1, 1, 1, 5, "Muy buena", "2024-01-14"]],
            "preguntas": [[1, 1, 1, "¿Otro color?", "", "2024-01-02 10:56:00"]],
        }
        self.write_sources()

    def write_sources(self):
        for table, spec in TABLES.items():
            with (self.source / spec["file"]).open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(spec["columns"])
                writer.writerows(self.rows[table])

    def test_imports_all_tables_and_relationships_without_changing_sources(self):
        original = {p.name: p.read_bytes() for p in self.source.iterdir()}
        manifest = build_dataset(self.source, self.target)
        self.assertEqual(len(manifest), 13)
        with open_dataset(self.target) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM variantes").fetchone()[0], 2)
            product = dict(db.execute("SELECT * FROM catalogo_productos").fetchone())
            self.assertEqual((product["titulo"], product["stock"], product["precio"]),
                             ("Lámpara de escritorio", 5, 72.5))
            self.assertEqual(product["vendedor"], "Tienda de Ana")
            self.assertEqual(product["estrellas"], 5)
            self.assertIsNone(db.execute("SELECT id_cupon FROM pedidos").fetchone()[0])
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM productos")
        self.assertEqual(original, {p.name: p.read_bytes() for p in self.source.iterdir()})

    def test_missing_file_and_invalid_foreign_key_keep_previous_database(self):
        build_dataset(self.source, self.target)
        original = self.target.read_bytes()
        (self.source / TABLES["couriers"]["file"]).unlink()
        with self.assertRaisesRegex(ValueError, "11_couriers.csv"):
            build_dataset(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), original)
        self.rows["productos"][0][1] = 999
        self.write_sources()
        with self.assertRaises((ValueError, sqlite3.IntegrityError)):
            build_dataset(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), original)

    def test_reimport_is_idempotent_and_detects_invalid_columns(self):
        first = build_dataset(self.source, self.target)
        self.assertEqual(first, build_dataset(self.source, self.target))
        path = self.source / TABLES["productos"]["file"]
        path.write_text("bad,header\n1,2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "columnas"):
            build_dataset(self.source, self.target)

    def test_catalog_api_search_pagination_details_and_read_only(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.routers.dataset import router, get_dataset_db, search_key
        build_dataset(self.source, self.target)
        app = FastAPI()
        app.include_router(router)

        def connection():
            with open_dataset(self.target) as db:
                db.create_function("search_key", 1, search_key)
                yield db
        app.dependency_overrides[get_dataset_db] = connection
        with TestClient(app) as client:
            response = client.get("/api/dataset/products?q=lampara&category=1&page_size=1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["total"], 1)
            self.assertEqual(response.json()["items"][0]["stock"], 5)
            self.assertEqual(client.get("/api/dataset/products?page=2").json()["items"], [])
            self.assertEqual(client.get("/api/dataset/products?q=' OR 1=1 --").json()["total"], 0)
            self.assertEqual(client.get("/api/dataset/products?page_size=10000").status_code, 422)
            self.assertEqual(client.get("/api/dataset/products?sort=bad").status_code, 422)
            detail = client.get("/api/dataset/products/1").json()
            self.assertEqual(len(detail["variantes"]), 2)
            self.assertEqual(detail["resenas"][0]["autor"], "Ana Pérez")
            self.assertIsNone(detail["preguntas"][0]["respuesta"])
            self.assertEqual(client.get("/api/dataset/products/999").status_code, 404)
            self.assertEqual(client.post("/api/dataset/products").status_code, 405)
            self.assertEqual(len(client.get("/api/dataset/summary").json()["tables"]), 13)
            self.assertEqual(client.get("/api/dataset/tables/users").status_code, 404)
            self.assertNotIn("email", client.get("/api/dataset/tables/usuarios").json()["columns"])
