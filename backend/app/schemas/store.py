"""Schema request/response cho Store API."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StoreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, min_length=1, max_length=30)

    @field_validator("name", "email", "phone", "address", "status")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class StoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str | None
    phone: str | None
    address: str | None
    status: str
    created_at: datetime
