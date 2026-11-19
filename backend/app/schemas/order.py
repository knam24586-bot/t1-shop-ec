"""Schemas Pydantic cho Order APIs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class CreateCODOrderRequest(BaseModel):
    """Dữ liệu gửi lên khi tạo đơn hàng COD từ giỏ hàng hiện tại."""
    shipping_address: str = Field(
        ...,
        min_length=5,
        description="Địa chỉ giao hàng snapshot (bắt buộc, tối thiểu 5 ký tự)",
        examples=["Số 10 Nguyễn Trãi, Thanh Xuân, Hà Nội"],
    )
    voucher_code: str | None = Field(
        None,
        description="Mã giảm giá áp dụng (nếu có)",
        examples=["T1CHAMPION"],
    )
    note: str | None = Field(
        None,
        description="Ghi chú giao hàng",
        examples=["Giao trong giờ hành chính"],
    )


class OrderItemResponse(BaseModel):
    """Thông tin từng mục sản phẩm trong đơn hàng."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int | None = None
    product_id: int | None = None
    product_name: str | None = None
    sku: str | None = None
    color: str | None = None
    size: str | None = None
    unit_price: Decimal = Field(..., description="Đơn giá snapshot tại thời điểm tạo đơn")
    quantity: int = Field(..., description="Số lượng đặt mua")
    line_total: Decimal = Field(..., description="Thành tiền = unit_price * quantity")


class PaymentSummaryResponse(BaseModel):
    """Thông tin thanh toán của đơn hàng."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    method: str
    amount: Decimal
    status: str
    transaction_reference: str | None = None
    attempt_number: int


class OrderResponse(BaseModel):
    """Thông tin tổng quan và chi tiết đơn hàng sau khi tạo."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_code: str
    customer_id: int
    total_price: Decimal = Field(..., description="Tổng giá trị đơn hàng sau khi trừ giảm giá")
    shipping_address: str = Field(..., description="Địa chỉ giao hàng snapshot")
    status: str = Field(..., description="Trạng thái đơn hàng (PENDING, CONFIRMED...)")
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse] = Field(default_factory=list)
    payment: PaymentSummaryResponse | None = None


class CreateOrderActionMessage(BaseModel):
    """Phản hồi thông báo kết quả tạo đơn hàng."""
    message: str
    order: OrderResponse

