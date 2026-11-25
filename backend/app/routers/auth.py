"""Registration, JWT login, current account, and logout endpoints."""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.passwords import hash_password, verify_password
from app.core.tokens import create_access_token
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
    TokenResponse,
    UserAuthResponse,
    normalize_phone,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-account-password")
_PHONE_INPUT = re.compile(r"^[+0-9\s().-]+$")


def _find_user_by_identifier(db: Session, identifier: str) -> User | None:
    if "@" in identifier:
        return db.scalar(select(User).where(func.lower(User.email) == identifier))
    if not _PHONE_INPUT.fullmatch(identifier):
        return None
    try:
        phone = normalize_phone(identifier)
    except ValueError:
        return None
    return db.scalar(select(User).where(User.phone == phone))


@router.post(
    "/register",
    response_model=UserAuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký tài khoản khách hàng",
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    duplicate = db.scalar(
        select(User.id).where(
            or_(
                func.lower(User.email) == payload.email,
                User.phone == payload.phone,
            )
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email hoặc số điện thoại đã được đăng ký.",
        )

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role="CUSTOMER",
        status="Active",
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        logger.info("Registration rejected by unique constraint")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email hoặc số điện thoại đã được đăng ký.",
        ) from exc
    logger.info("User registered user_id=%s role=%s", user.id, user.role)
    return user


@router.post("/login", response_model=TokenResponse, summary="Đăng nhập và cấp JWT")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = _find_user_by_identifier(db, payload.identifier)
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_is_valid = verify_password(payload.password, password_hash)

    if user is None or not password_is_valid:
        logger.warning("Login rejected reason=invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email/số điện thoại hoặc mật khẩu không đúng.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.status.strip().casefold() != "active":
        logger.warning("Login rejected user_id=%s reason=inactive_status", user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khóa hoặc vô hiệu hóa.",
        )

    token, expires_in = create_access_token(user)
    logger.info("Login succeeded user_id=%s role=%s", user.id, user.role)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserAuthResponse.model_validate(user),
    )


@router.get("/me", response_model=UserAuthResponse, summary="Thông tin tài khoản hiện tại")
def read_current_account(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@router.post("/logout", response_model=LogoutResponse, summary="Thu hồi JWT hiện tại")
def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LogoutResponse:
    # Tăng phiên bản token sẽ thu hồi ngay mọi access token đã cấp trước đó.
    current_user.token_version += 1
    db.commit()
    logger.info("User logged out user_id=%s", current_user.id)
    return LogoutResponse()
