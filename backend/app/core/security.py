"""Password hashing and compact HS256 JWT helpers using the Python standard library."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.core.config import settings

PASSWORD_HASH_ITERATIONS = 600_000


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        salt = _b64url_decode(salt_text)
        expected = _b64url_decode(digest_text)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError):
        return False


def create_access_token(user_id: int) -> tuple[str, int]:
    now = int(time.time())
    expires_in = max(1, settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES) * 60
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": settings.JWT_ISSUER,
        "sub": str(user_id),
        "iat": now,
        "exp": now + expires_in,
    }
    signing_input = f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode())}.{_b64url_encode(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(
        settings.JWT_SECRET.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}", expires_in


def decode_access_token(token: str) -> dict[str, Any] | None:
    if len(token) > 4096:
        return None
    try:
        header_part, payload_part, signature_part = token.split(".", 2)
        signing_input = f"{header_part}.{payload_part}"
        supplied_signature = _b64url_decode(signature_part)
        expected_signature = hmac.new(
            settings.JWT_SECRET.encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None

        header = json.loads(_b64url_decode(header_part))
        payload = json.loads(_b64url_decode(payload_part))
        if not isinstance(header, dict) or header.get("alg") != "HS256":
            return None
        if not isinstance(payload, dict) or payload.get("iss") != settings.JWT_ISSUER:
            return None
        if not isinstance(payload.get("exp"), int) or payload["exp"] <= int(time.time()):
            return None
        if not isinstance(payload.get("sub"), str) or not payload["sub"].isdigit():
            return None
        return payload
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return None
