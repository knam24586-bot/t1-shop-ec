"""Schemas Pydantic cho Vendor Order APIs.
Hỗ trợ:
- Xem danh sách và chi tiết đơn hàng thuộc Store.
- Xác nhận đơn (Confirm: PENDING -> CONFIRMED).
- Từ chối đơn (Reject: PENDING -> CANCELLED kèm lý do).
- Cập nhật trạng thái đơn theo State Machine.
- Tra cứu lịch sử chuyển đổi trạng thái (OrderStatusHistory).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class VendorOrderRejectRequest(BaseModel):
    """Dữ liệu yêu cầu từ chối đơn hàng của Vendor."""
    reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Lý do từ chối/hủy đơn hàng (bắt buộc, tối thiểu 3 ký tự)",
        examples=["Hết hàng trong kho hoặc cửa hàng tạm nghỉ"],
    )


class VendorOrderUpdateStatusRequest(BaseModel):
    """Dữ liệu yêu cầu cập nhật trạng thái đơn hàng theo State Machine."""
    status: str = Field(
        ...,
        description="Trạng thái mới (CONFIRMED, PROCESSING, SHIPPED, DELIVERED, CANCELLED)",
        examples=["PROCESSING"],
    )
    reason: str | None = Field(
        None,
        description="Lý do cập nhật (Bắt buộc nếu chuyển sang trạng thái CANCELLED)",
        examples=["Đã chuẩn bị xong hàng, chuyển sang đơn vị vận chuyển"],
    )


class OrderStatusHistoryResponse(BaseModel):
    """Thông tin lịch sử chuyển trạng thái của đơn hàng."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    order_code: str
    store_id: int | None = None
    previous_status: str
    new_status: str
    reason: str | None = None
    changed_by_role: str
    changed_by_user_id: int | None = None
    created_at: datetime


class VendorOrderItemResponse(BaseModel):
    """Thông tin sản phẩm trong đơn hàng của Store."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int | None = None
    variant_id: int | None = None
    product_name: str | None = None
    sku: str | None = None
    color: str | None = None
    size: str | None = None
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class VendorOrderResponse(BaseModel):
    """Thông tin chi tiết một đơn hàng thuộc Store dành cho Vendor."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_code: str
    store_id: int | None = None
    customer_id: int
    total_price: Decimal
    shipping_address: str
    status: str
    created_at: datetime
    updated_at: datetime
    items: list[VendorOrderItemResponse] = Field(default_factory=list)
    history: list[OrderStatusHistoryResponse] = Field(default_factory=list)


class VendorOrderListResponse(BaseModel):
    """Danh sách đơn hàng của Store kèm thông tin phân trang."""
    model_config = ConfigDict(from_attributes=True)

    items: list[VendorOrderResponse] = Field(default_factory=list)
    total: int
    page: int
    limit: int
    total_pages: int


class VendorOrderActionResponse(BaseModel):
    """Phản hồi sau khi Vendor xác nhận, từ chối hoặc cập nhật trạng thái đơn hàng."""
    model_config = ConfigDict(from_attributes=True)

    message: str = Field(..., description="Thông báo kết quả thao tác")
    order_code: str = Field(..., description="Mã đơn hàng")
    previous_status: str = Field(..., description="Trạng thái trước khi chuyển đổi")
    current_status: str = Field(..., description="Trạng thái mới sau khi chuyển đổi")
    reason: str | None = Field(None, description="Lý do thao tác nếu có")
    history_id: int | None = Field(None, description="ID bản ghi lịch sử trạng thái")
    updated_at: datetime = Field(..., description="Thời gian cập nhật")
