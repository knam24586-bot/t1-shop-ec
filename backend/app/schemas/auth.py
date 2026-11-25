"""Validated request and response models for account authentication."""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@.]{2,63}$")
_PHONE_SEPARATORS = re.compile(r"[\s().-]")


def normalize_phone(value: str) -> str:
    normalized = _PHONE_SEPARATORS.sub("", value.strip())
    if not re.fullmatch(r"\+?[0-9]{7,15}", normalized):
        raise ValueError("Số điện thoại không đúng định dạng.")
    return normalized


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: str = Field(min_length=6, max_length=255)
    phone: str = Field(min_length=7, max_length=30)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Họ tên phải có ít nhất 2 ký tự.")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("Email không đúng định dạng.")
        return normalized

    @field_validator("phone")
    @classmethod
    def normalize_and_validate_phone(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if value.strip() != value or not value:
            raise ValueError("Mật khẩu không được để trống hoặc có khoảng trắng ở đầu/cuối.")
        return value


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip().lower()


class UserAuthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    phone: str | None
    role: str
    status: str
    store_id: int | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserAuthResponse


class LogoutResponse(BaseModel):
    success: bool = True
    message: str = "Đã đăng xuất."
