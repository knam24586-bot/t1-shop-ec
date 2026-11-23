import unittest
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.models.category import Category
from app.models.product import Product
from app.models.variant import ProductVariant
from app.routers.inventory import router as inventory_router


class TestInventoryAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        category = Category(name="Test", slug="test")
        self.db.add(category)
        self.db.flush()
        product = Product(
            category_id=category.id,
            name="Product",
            slug="product",
            price=Decimal("10.00"),
            stock=10,
            store_id=1,
        )
        self.db.add(product)
        self.db.flush()
        self.variant = ProductVariant(
            product_id=product.id, sku="SKU-1", stock=5
        )
        self.db.add(self.variant)
        self.db.commit()

        app = FastAPI()
        app.include_router(inventory_router)

        def override_get_db():
            session = Session(self.engine)
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.headers = {"X-Role": "VENDOR", "X-Store-Id": "1"}

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_receive_and_history(self):
        response = self.client.post(
            f"/api/inventory/{self.variant.id}/receive",
            json={"quantity": 3, "reason": "Nhập hàng"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stock"], 8)

        history = self.client.get(
            f"/api/inventory/{self.variant.id}/movements",
            headers=self.headers,
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()[0]["quantity"], 3)
        self.assertEqual(history.json()[0]["stock_before"], 5)
        self.assertEqual(history.json()[0]["stock_after"], 8)

    def test_adjustment_cannot_make_stock_negative(self):
        response = self.client.post(
            f"/api/inventory/{self.variant.id}/adjust",
            json={"quantity": -6},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Stock cannot be negative")

    def test_vendor_cannot_access_another_store(self):
        self.db.query(Product).filter_by(id=self.variant.product_id).update(
            {"store_id": 2}
        )
        self.db.commit()
        response = self.client.get(
            f"/api/inventory/{self.variant.id}", headers=self.headers
        )
        self.assertEqual(response.status_code, 403)

    def test_set_inventory_and_normalize_role_header(self):
        response = self.client.put(
            f"/api/inventory/{self.variant.id}",
            json={"stock": 12, "reason": "Kiểm kho"},
            headers={"X-Role": " vendor ", "X-Store-Id": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stock"], 12)


if __name__ == "__main__":
    unittest.main()
