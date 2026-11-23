import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.models.store import Store
from app.models.vendor import Vendor
from app.routers.stores import router as stores_router


class TestStoreAPI(unittest.TestCase):
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

        vendor = Vendor(name="Vendor", email="vendor@example.com")
        self.db.add(vendor)
        self.db.flush()
        self.store = Store(
            vendor_id=vendor.id,
            name="Main Store",
            email="store@example.com",
            phone="0900000000",
            address="Ha Noi",
            status="Active",
        )
        self.db.add(self.store)
        self.db.commit()

        app = FastAPI()
        app.include_router(stores_router)

        def override_get_db():
            session = Session(self.engine)
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.vendor_headers = {"X-Role": " vendor ", "X-Store-Id": str(self.store.id)}

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_vendor_reads_and_updates_assigned_store(self):
        read = self.client.get("/api/stores/me", headers=self.vendor_headers)
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.json()["name"], "Main Store")

        updated = self.client.patch(
            "/api/stores/me",
            json={"name": "Updated Store", "phone": "0987654321"},
            headers=self.vendor_headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Updated Store")
        self.assertEqual(updated.json()["phone"], "0987654321")

    def test_vendor_cannot_update_status_or_another_store(self):
        denied_status = self.client.patch(
            "/api/stores/me",
            json={"status": "Inactive"},
            headers=self.vendor_headers,
        )
        self.assertEqual(denied_status.status_code, 403)

        denied_store = self.client.get(
            "/api/stores/999",
            headers=self.vendor_headers,
        )
        self.assertEqual(denied_store.status_code, 403)

    def test_admin_can_update_store_status(self):
        response = self.client.patch(
            f"/api/stores/{self.store.id}",
            json={"status": "Inactive"},
            headers={"X-Role": " admin "},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "Inactive")

    def test_missing_role_and_invalid_store_id_are_rejected(self):
        missing_role = self.client.get("/api/stores/me")
        self.assertEqual(missing_role.status_code, 401)

        invalid_id = self.client.get(
            "/api/stores/me",
            headers={"X-Role": "VENDOR", "X-Store-Id": "0"},
        )
        self.assertEqual(invalid_id.status_code, 422)


if __name__ == "__main__":
    unittest.main()
