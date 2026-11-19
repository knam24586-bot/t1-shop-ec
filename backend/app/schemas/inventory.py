"""Schema cho API quản lý tồn kho."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InventoryReceive(BaseModel):
    quantity: int = Field(gt=0, le=1_000_000)
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class InventoryAdjust(BaseModel):
    quantity: int = Field(ne=0, ge=-1_000_000, le=1_000_000)
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class InventorySet(BaseModel):
    stock: int = Field(ge=0, le=1_000_000)
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class InventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    variant_id: int
    sku: str
    product_id: int
    product_name: str
    stock: int


class InventoryMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int
    movement_type: str
    quantity: int
    stock_before: int
    stock_after: int
    reason: str | None
    created_at: datetime
