"""Integration tests for registration, JWT login, token expiry, logout, and RBAC."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from fastapi.testclient import TestClient
import jwt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.passwords import hash_password, verify_password
from app.core.tokens import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models.user import User


class TestAuthAPIs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        self._orig_secret = settings.JWT_SECRET_KEY
        self._orig_algo = settings.JWT_ALGORITHM
        self._orig_expire = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        settings.JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-characters-long"
        settings.JWT_ALGORITHM = "HS256"
        settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30

        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        def override_get_db():
            session = Session(self.engine)
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.JWT_SECRET_KEY = self._orig_secret
        settings.JWT_ALGORITHM = self._orig_algo
        settings.ACCESS_TOKEN_EXPIRE_MINUTES = self._orig_expire

    def test_register_success_hashes_password_and_defaults_customer_role(self):
        payload = {
            "full_name": "  Lee   Sang-hyeok  ",
            "email": "  Faker@T1.GG ",
            "phone": "090-123-4567",
            "password": "StrongPassword123!",
            "role": "ADMIN",  # Must be ignored; registered user is always CUSTOMER.
        }
        res = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["full_name"], "Lee Sang-hyeok")
        self.assertEqual(data["email"], "faker@t1.gg")
        self.assertEqual(data["phone"], "0901234567")
        self.assertEqual(data["role"], "CUSTOMER")
        self.assertEqual(data["status"], "Active")
        self.assertNotIn("password_hash", data)
        self.assertNotIn("password", data)

        user_db = self.db.scalar(select(User).where(User.email == "faker@t1.gg"))
        self.assertIsNotNone(user_db)
        self.assertNotEqual(user_db.password_hash, "StrongPassword123!")
        self.assertTrue(user_db.password_hash.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("StrongPassword123!", user_db.password_hash))

    def test_register_rejects_duplicate_email_and_phone(self):
        first = {
            "full_name": "First User",
            "email": "dup@t1.gg",
            "phone": "+84 91 234 5678",
            "password": "Password123!",
        }
        res1 = self.client.post("/api/auth/register", json=first)
        self.assertEqual(res1.status_code, 201)

        # Duplicate email (case-insensitive)
        dup_email = {
            "full_name": "Second User",
            "email": "DUP@T1.GG",
            "phone": "0998887777",
            "password": "Password123!",
        }
        res2 = self.client.post("/api/auth/register", json=dup_email)
        self.assertEqual(res2.status_code, 409)
        self.assertFalse(res2.json()["success"])
        self.assertEqual(res2.json()["error"]["code"], "CONFLICT")

        # Duplicate phone (normalized formatting)
        dup_phone = {
            "full_name": "Third User",
            "email": "other@t1.gg",
            "phone": "+84912345678",
            "password": "Password123!",
        }
        res3 = self.client.post("/api/auth/register", json=dup_phone)
        self.assertEqual(res3.status_code, 409)
        self.assertEqual(res3.json()["error"]["code"], "CONFLICT")

    def test_register_rejects_missing_or_invalid_inputs(self):
        invalid_cases = [
            {"full_name": "A", "email": "ok@t1.gg", "phone": "0901234567", "password": "Password123!"},
            {"full_name": "Valid Name", "email": "not-an-email", "phone": "0901234567", "password": "Password123!"},
            {"full_name": "Valid Name", "email": "ok@t1.gg", "phone": "abc123", "password": "Password123!"},
            {"full_name": "Valid Name", "email": "ok@t1.gg", "phone": "0901234567", "password": "short"},
            {"full_name": "Valid Name", "email": "ok@t1.gg", "password": "Password123!"},  # missing phone
            {"full_name": "Valid Name", "email": "ok@t1.gg", "phone": "0901234567", "password": " Password123! "},
        ]
        for payload in invalid_cases:
            res = self.client.post("/api/auth/register", json=payload)
            self.assertEqual(res.status_code, 422, msg=f"Expected 422 for {payload}")
            body = res.json()
            self.assertFalse(body["success"])
            self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")

    def test_login_with_email_or_phone_returns_jwt_and_role(self):
        user = User(
            full_name="Vendor Owner",
            email="vendor@t1.gg",
            phone="0905556666",
            password_hash=hash_password("VendorPass123!"),
            role="VENDOR",
            status="Active",
            store_id=42,
        )
        self.db.add(user)
        self.db.commit()

        # Login with email
        res_email = self.client.post(
            "/api/auth/login",
            json={"identifier": "  VENDOR@T1.GG ", "password": "VendorPass123!"},
        )
        self.assertEqual(res_email.status_code, 200)
        body = res_email.json()
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(body["expires_in"], 30 * 60)
        self.assertEqual(body["user"]["role"], "VENDOR")
        self.assertEqual(body["user"]["store_id"], 42)
        self.assertNotIn("password_hash", body["user"])

        claims = jwt.decode(
            body["access_token"],
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        self.assertEqual(claims["sub"], str(user.id))
        self.assertEqual(claims["role"], "VENDOR")
        self.assertEqual(claims["type"], "access")
        self.assertEqual(claims["exp"] - claims["iat"], 30 * 60)

        # Login with formatted phone number
        res_phone = self.client.post(
            "/api/auth/login",
            json={"identifier": "090-555-6666", "password": "VendorPass123!"},
        )
        self.assertEqual(res_phone.status_code, 200)

    def test_login_rejects_wrong_credentials_and_locked_account(self):
        locked = User(
            full_name="Locked User",
            email="locked@t1.gg",
            phone="0901112222",
            password_hash=hash_password("LockedPass123!"),
            role="CUSTOMER",
            status="Locked",
        )
        self.db.add(locked)
        self.db.commit()

        # Wrong password -> 401
        res_wrong = self.client.post(
            "/api/auth/login",
            json={"identifier": "locked@t1.gg", "password": "WrongPassword!"},
        )
        self.assertEqual(res_wrong.status_code, 401)
        self.assertEqual(res_wrong.json()["error"]["code"], "UNAUTHENTICATED")

        # Unknown user -> 401
        res_unknown = self.client.post(
            "/api/auth/login",
            json={"identifier": "nobody@t1.gg", "password": "SomePassword!"},
        )
        self.assertEqual(res_unknown.status_code, 401)

        # Valid password but locked account -> 403
        res_locked = self.client.post(
            "/api/auth/login",
            json={"identifier": "locked@t1.gg", "password": "LockedPass123!"},
        )
        self.assertEqual(res_locked.status_code, 403)
        self.assertEqual(res_locked.json()["error"]["code"], "FORBIDDEN")

    def test_me_logout_and_expired_token_handling(self):
        user = User(
            full_name="Active Customer",
            email="active@t1.gg",
            phone="0907778888",
            password_hash=hash_password("CustomerPass123!"),
            role="CUSTOMER",
            status="Active",
        )
        self.db.add(user)
        self.db.commit()

        login_res = self.client.post(
            "/api/auth/login",
            json={"identifier": "active@t1.gg", "password": "CustomerPass123!"},
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # /me works with valid token
        me_res = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["email"], "active@t1.gg")

        # X-User-Id alone without Bearer token is rejected
        spoof_res = self.client.get("/api/auth/me", headers={"X-User-Id": str(user.id)})
        self.assertEqual(spoof_res.status_code, 401)

        # Expired token is rejected with 401
        now = datetime.now(timezone.utc)
        expired_token = jwt.encode(
            {
                "sub": str(user.id),
                "role": "CUSTOMER",
                "ver": user.token_version,
                "type": "access",
                "jti": "expired-jti",
                "iat": now - timedelta(hours=2),
                "exp": now - timedelta(minutes=1),
            },
            settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )
        exp_res = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        self.assertEqual(exp_res.status_code, 401)
        self.assertIn("hết hạn", exp_res.json()["error"]["message"].lower())

        # Logout revokes current JWT
        logout_res = self.client.post("/api/auth/logout", headers=headers)
        self.assertEqual(logout_res.status_code, 200)
        self.assertTrue(logout_res.json()["success"])

        # Same token is rejected after logout
        after_logout_res = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(after_logout_res.status_code, 401)

    def test_locking_user_invalidates_existing_token(self):
        user = User(
            full_name="Soon Locked",
            email="soonlocked@t1.gg",
            phone="0902223333",
            password_hash=hash_password("Pass123456!"),
            role="CUSTOMER",
            status="Active",
        )
        self.db.add(user)
        self.db.commit()

        token, _ = create_access_token(user)
        headers = {"Authorization": f"Bearer {token}"}
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 200)

        user.status = "Locked"
        self.db.commit()

        res = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
