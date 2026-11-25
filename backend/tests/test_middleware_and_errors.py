"""Tests for tracing middleware, unified validation/system errors, and safe logging."""
from __future__ import annotations

import logging
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app


class _MemoryLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


class TestMiddlewareAndErrors(unittest.TestCase):
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

        def override_get_db():
            session = Session(self.engine)
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db

        # Attach a temporary crash route if not yet added for testing unhandled 500s.
        if not any(getattr(r, "path", None) == "/api/__test_crash" for r in app.routes):
            @app.get("/api/__test_crash")
            def _test_crash():
                raise RuntimeError("SECRET_DB_DSN=mysql://root:supersecret@localhost/db")

        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.JWT_SECRET_KEY = self._orig_secret

    def test_validation_error_format_does_not_leak_sensitive_input(self):
        secret_pw = "MySuperSecretPassword!99"
        res = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "T1 User",
                "email": "bad-email",
                "phone": "0901234567",
                "password": secret_pw,
            },
        )
        self.assertEqual(res.status_code, 422)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")
        self.assertTrue(body["request_id"])
        self.assertEqual(res.headers.get("X-Request-ID"), body["request_id"])
        self.assertIsInstance(body["error"]["details"], list)
        self.assertNotIn(secret_pw, res.text)
        self.assertFalse(body["error"]["details"][0]["message"].startswith("Value error, "))

    def test_unhandled_exception_masks_stack_trace_and_secrets(self):
        res = self.client.get("/api/__test_crash")
        self.assertEqual(res.status_code, 500)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "INTERNAL_ERROR")
        self.assertEqual(body["error"]["message"], "Đã xảy ra lỗi hệ thống.")
        self.assertIsNone(body["error"]["details"])
        self.assertTrue(body["request_id"])
        self.assertEqual(res.headers.get("X-Request-ID"), body["request_id"])
        self.assertNotIn("Traceback", res.text)
        self.assertNotIn("supersecret", res.text)
        self.assertNotIn("RuntimeError", res.text)

    def test_misconfigured_jwt_secret_does_not_leak_in_http_response(self):
        settings.JWT_SECRET_KEY = "short"
        res = self.client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer abc.def.ghi"},
        )
        self.assertEqual(res.status_code, 503)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "SERVICE_UNAVAILABLE")
        self.assertEqual(body["error"]["message"], "Đã xảy ra lỗi hệ thống.")
        self.assertNotIn("JWT_SECRET_KEY", res.text)
        self.assertNotIn("short", res.text)

    def test_request_logging_records_tracing_info_without_secrets(self):
        api_logger = logging.getLogger("t1shop.api")
        handler = _MemoryLogHandler()
        api_logger.addHandler(handler)
        try:
            res = self.client.get(
                "/api/categories",
                headers={"Authorization": "Bearer secret-jwt-token-value"},
            )
            self.assertEqual(res.status_code, 200)
            req_id = res.headers.get("X-Request-ID")
            self.assertTrue(req_id)

            joined = "\n".join(handler.records)
            self.assertIn(f"request_id={req_id}", joined)
            self.assertIn("method=GET", joined)
            self.assertIn("path=/api/categories", joined)
            self.assertIn("status=200", joined)
            self.assertIn("duration_ms=", joined)
            self.assertNotIn("secret-jwt-token-value", joined)
        finally:
            api_logger.removeHandler(handler)

    def test_protected_routes_require_jwt_on_main_app(self):
        protected_endpoints = [
            ("GET", "/api/cart"),
            ("GET", "/api/wishlist"),
            ("GET", "/api/orders"),
            ("GET", "/api/customer/orders"),
            ("GET", "/api/vendor/orders"),
            ("GET", "/api/stores/me"),
            ("GET", "/api/inventory"),
            ("GET", "/api/payments/logs/TXN-1"),
            ("GET", "/api/payments/transaction/TXN-1"),
        ]
        for method, path in protected_endpoints:
            res = self.client.request(method, path, headers={"X-User-Id": "1"})
            self.assertEqual(res.status_code, 401, msg=f"{method} {path} should require JWT")
            self.assertEqual(res.json()["error"]["code"], "UNAUTHENTICATED")


if __name__ == "__main__":
    unittest.main()
