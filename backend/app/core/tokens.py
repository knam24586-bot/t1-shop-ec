"""Create and validate short-lived JWT access tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from uuid import uuid4

import jwt
from fastapi import HTTPException, status
from jwt import ExpiredSignatureError, InvalidTokenError

from app.core.config import settings
from app.models.user import User

logger = logging.getLogger("t1shop.auth")


def _signing_key() -> str:
    key = settings.JWT_SECRET_KEY.strip()
    if len(key) < 32:
        logger.error("JWT_SECRET_KEY is missing or shorter than 32 characters.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hệ thống xác thực chưa sẵn sàng.",
        )
    if settings.JWT_ALGORITHM != "HS256":
        logger.error("Unsupported JWT_ALGORITHM configured: %s", settings.JWT_ALGORITHM)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hệ thống xác thực chưa sẵn sàng.",
        )
    return key


def create_access_token(user: User) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    lifetime = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expires_at = now + lifetime
    claims = {
        "sub": str(user.id),
        "role": user.role.upper(),
        "ver": user.token_version,
        "type": "access",
        "jti": uuid4().hex,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(claims, _signing_key(), algorithm="HS256")
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            _signing_key(),
            algorithms=["HS256"],
            options={
                "require": ["sub", "role", "ver", "type", "jti", "iat", "exp"]
            },
        )
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token đã hết hạn.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token không hợp lệ.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if claims.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Loại access token không hợp lệ.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims
