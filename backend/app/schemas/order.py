from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class CheckoutRequest(BaseModel):
    shipping_address: str = Field(min_length=8, max_length=255)
    payment_method: str = "COD"

    @field_validator("shipping_address")
    @classmethod
    def validate_address(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 8:
            raise ValueError("Địa chỉ giao hàng cần ít nhất 8 ký tự.")
        return normalized

    @field_validator("payment_method")
    @classmethod
    def cod_only(cls, value: str) -> str:
        if value.upper() != "COD":
            raise ValueError("Hiện chỉ hỗ trợ thanh toán khi nhận hàng (COD).")
        return "COD"


class OrderItemResponse(BaseModel):
    id: int
    product_id: int | None
    variant_id: int | None
    product_name: str | None
    sku: str | None
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class OrderResponse(BaseModel):
    id: int
    order_code: str
    status: str
    total_price: Decimal
    shipping_address: str
    payment_method: str
    payment_status: str
    created_at: datetime
    items: list[OrderItemResponse]
