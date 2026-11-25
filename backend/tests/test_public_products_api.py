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
from app.routers.products import router as products_router


class TestPublicProductsAPI(unittest.TestCase):
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

        active = Category(name="Active", slug="active", status="Active")
        inactive = Category(name="Inactive", slug="inactive", status="Inactive")
        self.db.add_all([active, inactive])
        self.db.flush()
        self.db.add_all(
            [
                Product(
                    category_id=active.id,
                    name="Published product",
                    slug="published-product",
                    price=Decimal("10.00"),
                    status="Published",
                ),
                Product(
                    category_id=active.id,
                    name="Draft product",
                    slug="draft-product",
                    price=Decimal("20.00"),
                    status="Draft",
                ),
                Product(
                    category_id=inactive.id,
                    name="Hidden category product",
                    slug="hidden-category-product",
                    price=Decimal("30.00"),
                    status="Published",
                ),
            ]
        )
        self.db.commit()

        app = FastAPI()
        app.include_router(products_router)

        def override_get_db():
            session = Session(self.engine)
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_list_never_exposes_unpublished_or_inactive_category_products(self):
        response = self.client.get("/api/products?status=Draft")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["slug"] for item in response.json()], ["published-product"])

    def test_details_search_and_filter_hide_inactive_category_products(self):
        hidden_id = self.db.query(Product).filter_by(slug="hidden-category-product").one().id

        self.assertEqual(self.client.get(f"/api/products/{hidden_id}").status_code, 404)
        search = self.client.get("/api/products/search?q=product")
        self.assertEqual([item["slug"] for item in search.json()["items"]], ["published-product"])
        filtered = self.client.get("/api/products/filter?min_price=1&max_price=100")
        self.assertEqual(
            [item["slug"] for item in filtered.json()["items"]], ["published-product"]
        )


if __name__ == "__main__":
    unittest.main()
