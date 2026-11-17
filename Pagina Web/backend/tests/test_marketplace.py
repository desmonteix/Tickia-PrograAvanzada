"""Compras y publicaciones locales: stock, autorización e idempotencia reales."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("TICKIA_LOAD_ENV", "0")
os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, str(Path(__file__).parents[2]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base, get_db
from backend.models import User
from backend.auth_utils import create_access_token
from backend.marketplace import seed_marketplace
from backend.routers.marketplace import router
import test_dataset as dataset_fixtures
from backend.dataset import build_dataset, open_dataset


class MarketplaceTests(unittest.TestCase):
    def setUp(self):
        fixture = dataset_fixtures.DatasetTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        build_dataset(fixture.source, fixture.target)
        self.source_db = fixture.target
        source_patch = patch("backend.routers.marketplace.open_dataset", lambda: open_dataset(self.source_db))
        source_patch.start()
        self.addCleanup(source_patch.stop)
        self.original = fixture.target.read_bytes()
        self.engine = create_engine("sqlite:///" + str(Path(fixture.temp.name) / "app.sqlite3"),
                                    connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        seed_marketplace(self.engine, fixture.target)
        self.users = []
        with self.sessions() as db:
            for role in ("buyer", "seller", "other"):
                user = User(id=uuid.uuid4(), email=role + "@example.com", hashed_password="unused", full_name=role)
                db.add(user)
                self.users.append(user.id)
            db.commit()
        app = FastAPI()
        app.include_router(router)

        def connection():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = connection
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def headers(self, index=0):
        return {"Authorization": "Bearer " + create_access_token({"user_id": str(self.users[index])})}

    def purchase(self, **overrides):
        payload = dict(variant_id=1, quantity=2, request_id=str(uuid.uuid4()))
        payload.update(overrides)
        return payload

    def test_buy_is_atomic_idempotent_and_preserves_fixed_dataset(self):
        payload = self.purchase()
        first = self.client.post("/api/marketplace/orders", json=payload, headers=self.headers())
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()["total_centimos"], 14500)
        repeat = self.client.post("/api/marketplace/orders", json=payload, headers=self.headers())
        self.assertEqual(repeat.json()["id"], first.json()["id"])
        stock = self.client.get("/api/marketplace/products/1").json()["variantes"][0]["stock"]
        self.assertEqual(stock, 1)
        rejected = self.client.post("/api/marketplace/orders", json=self.purchase(), headers=self.headers(2))
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(self.client.get("/api/marketplace/orders", headers=self.headers()).json()["total"], 1)
        self.assertEqual(self.client.get("/api/marketplace/orders", headers=self.headers(2)).json()["total"], 0)
        self.assertEqual(self.source_db.read_bytes(), self.original)
        seed_marketplace(self.engine, self.source_db)
        self.assertEqual(self.client.get("/api/marketplace/products/1").json()["variantes"][0]["stock"], 1)

    def test_publish_then_other_account_buys_and_seller_sees_sale(self):
        created = self.client.post("/api/marketplace/products", data={"titulo": "Mi lámpara nueva",
            "descripcion": "Una lámpara para escritorio", "precio": "49.90", "stock": "2",
            "id_categoria": "2", "color": "Azul", "talla": "Única"}, headers=self.headers(1))
        self.assertEqual(created.status_code, 201, created.text)
        product = created.json()
        self.assertEqual(product["precio"], 49.9)
        self.assertEqual(self.client.get("/api/marketplace/products?q=lampara").json()["total"], 2)
        self.assertEqual(self.client.get("/api/marketplace/my-products", headers=self.headers(1)).json()["total"], 1)
        self.assertEqual(self.client.get("/api/marketplace/my-products", headers=self.headers()).json()["total"], 0)
        variant = product["variantes"][0]["id_variante"]
        own = self.client.post("/api/marketplace/orders", json=self.purchase(variant_id=variant), headers=self.headers(1))
        self.assertEqual(own.status_code, 409)
        bought = self.client.post("/api/marketplace/orders", json=self.purchase(variant_id=variant, quantity=1), headers=self.headers())
        self.assertEqual(bought.status_code, 201, bought.text)
        sales = self.client.get("/api/marketplace/sales", headers=self.headers(1)).json()
        self.assertEqual(sales["total"], 1)
        self.assertEqual(sales["items"][0]["titulo"], "Mi lámpara nueva")
        self.assertEqual(self.client.get("/api/marketplace/products/" + str(product["id_producto"])).json()["stock"], 1)

    def test_requires_authentication_and_validates_stock_price_and_request_reuse(self):
        self.assertEqual(self.client.post("/api/marketplace/orders", json=self.purchase()).status_code, 401)
        self.assertEqual(self.client.post("/api/marketplace/products", data={}).status_code, 401)
        self.assertEqual(self.client.post("/api/marketplace/orders", json=self.purchase(quantity=0), headers=self.headers()).status_code, 422)
        self.assertEqual(self.client.post("/api/marketplace/orders", json=self.purchase(variant_id=999), headers=self.headers()).status_code, 404)
        payload = self.purchase(quantity=1)
        self.client.post("/api/marketplace/orders", json=payload, headers=self.headers())
        payload["quantity"] = 2
        self.assertEqual(self.client.post("/api/marketplace/orders", json=payload, headers=self.headers()).status_code, 409)
        for price in ("-1", "NaN", "Infinity", "1.123"):
            bad = self.client.post("/api/marketplace/products", data={"titulo": "Producto", "precio": price,
                "stock": "2", "id_categoria": "2"}, headers=self.headers())
            self.assertEqual(bad.status_code, 422, bad.text)

    def test_two_buyers_cannot_purchase_the_same_last_unit(self):
        from concurrent.futures import ThreadPoolExecutor
        from sqlalchemy import update
        from backend.marketplace_models import LocalVariant, LocalOrder
        with self.sessions() as db:
            db.execute(update(LocalVariant).where(LocalVariant.id_variante == 1).values(stock=1))
            db.commit()
        def buy(index):
            return self.client.post("/api/marketplace/orders", json=self.purchase(quantity=1), headers=self.headers(index)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(buy, (0, 2)))
        self.assertEqual(sorted(statuses), [201, 409])
        with self.sessions() as db:
            self.assertEqual(db.get(LocalVariant, 1).stock, 0)
            self.assertEqual(db.query(LocalOrder).count(), 1)

    def test_product_photo_is_validated_and_served_without_using_client_filename(self):
        import cv2
        import numpy as np
        from backend.routers import marketplace
        with tempfile.TemporaryDirectory() as directory, patch.object(marketplace, "LOCAL_DIR", Path(directory)):
            payload = {"titulo": "Producto con foto", "precio": "12.50", "stock": "1", "id_categoria": "2"}
            invalid = self.client.post("/api/marketplace/products", data=payload,
                files={"foto": ("photo.jpg", b"<script>bad</script>", "image/jpeg")}, headers=self.headers(1))
            self.assertEqual(invalid.status_code, 422)
            _, encoded = cv2.imencode(".png", np.full((32, 32, 3), 100, dtype=np.uint8))
            valid = self.client.post("/api/marketplace/products", data=payload,
                files={"foto": ("../../ignored.png", encoded.tobytes(), "image/png")}, headers=self.headers(1))
            self.assertEqual(valid.status_code, 201, valid.text)
            filename = valid.json()["imagen"]
            self.assertRegex(filename, r"^[0-9a-f]{32}\.jpg$")
            response = self.client.get("/api/marketplace/images/" + filename)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/jpeg")
            self.assertEqual(self.client.get("/api/marketplace/images/not-a-file").status_code, 404)
