import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.tokens import create_access_token
from app.db.session import Base, get_db
from app.models.store import Store
from app.models.user import User
from app.models.vendor import Vendor
from app.routers.stores import router as stores_router


class TestStoreAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        self._orig_secret = settings.JWT_SECRET_KEY
        settings.JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-characters-long"
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
        self.db.flush()

        self.vendor_user = User(
            full_name="Vendor Owner",
            email="vendor_user@example.com",
            password_hash="hash",
            role="VENDOR",
            status="Active",
            store_id=self.store.id,
        )
        self.unassigned_vendor = User(
            full_name="Unassigned Vendor",
            email="unassigned@example.com",
            password_hash="hash",
            role="VENDOR",
            status="Active",
            store_id=None,
        )
        self.admin_user = User(
            full_name="Admin User",
            email="admin@example.com",
            password_hash="hash",
            role="ADMIN",
            status="Active",
        )
        self.customer_user = User(
            full_name="Customer User",
            email="customer@example.com",
            password_hash="hash",
            role="CUSTOMER",
            status="Active",
        )
        self.db.add_all(
            [self.vendor_user, self.unassigned_vendor, self.admin_user, self.customer_user]
        )
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
        self.vendor_headers = self._auth_headers(self.vendor_user)
        self.admin_headers = self._auth_headers(self.admin_user)

    def _auth_headers(self, user: User) -> dict[str, str]:
        token, _ = create_access_token(user)
        return {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.JWT_SECRET_KEY = self._orig_secret

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
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "Inactive")

    def test_missing_role_and_invalid_store_id_are_rejected(self):
        missing_token = self.client.get("/api/stores/me")
        self.assertEqual(missing_token.status_code, 401)

        customer_denied = self.client.get(
            "/api/stores/me",
            headers=self._auth_headers(self.customer_user),
        )
        self.assertEqual(customer_denied.status_code, 403)

        unassigned_denied = self.client.get(
            "/api/stores/me",
            headers=self._auth_headers(self.unassigned_vendor),
        )
        self.assertEqual(unassigned_denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
