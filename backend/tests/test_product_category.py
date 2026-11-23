import unittest
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.models.category import Category
from app.models.product import Product
from app.models.variant import ProductVariant
from app.routers.categories import router as categories_router
from app.routers.products import router as products_router
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.schemas.product import ProductCreate, ProductUpdate


class TestProductCategory(unittest.TestCase):
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

        self.active_category = Category(
            name="Fashion", slug="fashion", status="Active"
        )
        self.inactive_category = Category(
            name="Old Collection", slug="old-collection", status="Inactive"
        )
        self.db.add_all([self.active_category, self.inactive_category])
        self.db.flush()

        self.published = Product(
            category_id=self.active_category.id,
            name="T1 Jersey",
            slug="t1-jersey",
            description="Official jersey",
            price=Decimal("250.00"),
            rating=Decimal("4.5"),
            stock=10,
            status="Published",
            store_id=1,
        )
        self.draft = Product(
            category_id=self.active_category.id,
            name="Draft Jacket",
            slug="draft-jacket",
            price=Decimal("300.00"),
            status="Draft",
        )
        self.db.add_all([self.published, self.draft])
        self.db.flush()

        self.variant = ProductVariant(
            product_id=self.published.id,
            sku="T1-JERSEY-M",
            color="Red",
            size="M",
            stock=5,
        )
        self.db.add(self.variant)
        self.db.commit()

        app = FastAPI()
        app.include_router(categories_router, prefix="/api")
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

    def test_category_model_and_slug_are_persisted(self):
        category = self.db.get(Category, self.active_category.id)

        self.assertIsNotNone(category)
        self.assertEqual(category.slug, "fashion")
        self.assertEqual(category.status, "Active")
        self.assertEqual(category.products[0].slug, "t1-jersey")

    def test_category_slug_must_be_unique(self):
        self.db.add(Category(name="Duplicate", slug="fashion"))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_category_schema_validates_slug_and_parent(self):
        valid = CategoryCreate(name="Shoes", slug="shoes")
        self.assertEqual(valid.slug, "shoes")

        with self.assertRaises(ValueError):
            CategoryCreate(name="Invalid", slug="Invalid_Slug")
        with self.assertRaises(ValueError):
            CategoryUpdate(parent_id=0)

    def test_category_public_read_and_admin_create(self):
        public_response = self.client.get("/api/categories")
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(len(public_response.json()), 2)

        denied = self.client.post(
            "/api/categories",
            json={"name": "Accessories", "slug": "accessories"},
        )
        self.assertEqual(denied.status_code, 403)

        created = self.client.post(
            "/api/categories",
            json={"name": "Accessories", "slug": "accessories"},
            headers={"X-Admin-Role": "admin"},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["slug"], "accessories")

    def test_category_update_and_disable(self):
        category_id = self.active_category.id
        headers = {"X-Admin-Role": "admin"}

        updated = self.client.put(
            f"/api/categories/{category_id}",
            json={"name": "New Fashion", "status": "Active"},
            headers=headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "New Fashion")

        disabled = self.client.patch(
            f"/api/categories/{category_id}/disable",
            headers=headers,
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json()["status"], "Inactive")

    def test_category_cannot_be_its_own_parent(self):
        response = self.client.put(
            f"/api/categories/{self.active_category.id}",
            json={"parent_id": self.active_category.id},
            headers={"X-Admin-Role": "admin"},
        )
        self.assertEqual(response.status_code, 400)

    def test_product_model_variant_relationship(self):
        product = self.db.get(Product, self.published.id)

        self.assertEqual(product.status, "Published")
        self.assertEqual(product.variants[0].sku, "T1-JERSEY-M")
        self.assertEqual(product.category.slug, "fashion")

    def test_product_slug_and_variant_sku_must_be_unique(self):
        duplicate = Product(
            category_id=self.active_category.id,
            name="Duplicate",
            slug="t1-jersey",
            price=Decimal("10.00"),
        )
        self.db.add(duplicate)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

        duplicate_variant = ProductVariant(
            product_id=self.draft.id,
            sku="T1-JERSEY-M",
            stock=1,
        )
        self.db.add(duplicate_variant)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    def test_product_schema_validates_required_fields_and_status(self):
        valid = ProductCreate(
            category_id=self.active_category.id,
            name="  Shoes  ",
            slug="  shoes  ",
            price=Decimal("99.00"),
        )
        self.assertEqual(valid.name, "Shoes")
        self.assertEqual(valid.slug, "shoes")

        with self.assertRaises(ValueError):
            ProductCreate(
                category_id=self.active_category.id,
                name="Invalid",
                slug="invalid",
                price=Decimal("99.00"),
                status="Unknown",
            )
        with self.assertRaises(ValueError):
            ProductUpdate(rating=Decimal("6"))

    def test_public_product_api_hides_draft_and_inactive_category(self):
        response = self.client.get("/api/products")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["slug"] for item in response.json()], ["t1-jersey"])

    def test_public_product_detail_and_search(self):
        detail = self.client.get(f"/api/products/{self.published.id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["slug"], "t1-jersey")
        self.assertEqual(detail.json()["variants"][0]["sku"], "T1-JERSEY-M")

        missing = self.client.get(f"/api/products/{self.draft.id}")
        self.assertEqual(missing.status_code, 404)

        search = self.client.get("/api/products/search?q=jersey")
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["total"], 1)

    def test_product_filter_validates_range(self):
        invalid = self.client.get(
            "/api/products/filter?min_price=100&max_price=50"
        )
        self.assertEqual(invalid.status_code, 422)

        valid = self.client.get(
            "/api/products/filter?category_id=1&min_price=200&max_price=300"
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["total"], 1)

    def test_vendor_can_create_and_update_only_own_store_product(self):
        headers = {"X-Role": "VENDOR", "X-Store-Id": "1"}
        created = self.client.post(
            "/api/products",
            json={
                "category_id": self.active_category.id,
                "name": "Vendor Jacket",
                "slug": "vendor-jacket",
                "price": "150.00",
                "store_id": 1,
            },
            headers=headers,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["store_id"], 1)

        denied = self.client.patch(
            f"/api/products/{self.published.id}",
            json={"store_id": 2},
            headers=headers,
        )
        self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
