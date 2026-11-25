"""Schemas Pydantic cho Admin Order APIs.
Hỗ trợ:
- Lọc và theo dõi đơn hàng toàn hệ thống với nhiều tiêu chí.
- Xem chi tiết đơn hàng toàn diện (khách hàng, sản phẩm, thanh toán, audit log).
- Cập nhật trạng thái đơn theo quyền và quy tắc.
- Tra cứu lịch sử kiểm toán thao tác quan trọng của Admin (AdminOrderAuditLog).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.vendor_order import OrderStatusHistoryResponse


class AdminUpdateOrderStatusRequest(BaseModel):
    """Dữ liệu yêu cầu Admin cập nhật trạng thái đơn hàng."""
    status: str = Field(
        ...,
        description="Trạng thái mới cần chuyển đổi (CONFIRMED, PROCESSING, SHIPPED, DELIVERED, CANCELLED)",
        examples=["CONFIRMED"],
    )
    reason: str | None = Field(
        None,
        description="Lý do cập nhật (Bắt buộc nếu chuyển sang trạng thái CANCELLED)",
        examples=["Admin phê duyệt đơn hàng khẩn cấp"],
    )
    admin_note: str | None = Field(
        None,
        description="Ghi chú nghiệp vụ của Admin",
        examples=["Xác minh thông tin khách hàng hợp lệ qua điện thoại"],
    )


class AdminCancelOrderRequest(BaseModel):
    """Dữ liệu yêu cầu Admin hủy đơn hàng."""
    reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Lý do hủy đơn hàng (bắt buộc, tối thiểu 3 ký tự)",
        examples=["Đơn hàng vi phạm chính sách thanh toán của sàn"],
    )
    admin_note: str | None = Field(
        None,
        description="Ghi chú nội bộ của Admin",
    )


class AdminOrderAuditLogResponse(BaseModel):
    """Thông tin log thao tác quan trọng của Admin."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    order_code: str
    admin_id: int
    action: str
    previous_status: str | None = None
    new_status: str | None = None
    reason: str | None = None
    ip_address: str | None = None
    created_at: datetime


class AdminOrderItemResponse(BaseModel):
    """Thông tin chi tiết mục sản phẩm trong đơn hàng dành cho Admin."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int | None = None
    product_id: int | None = None
    product_name: str | None = None
    sku: str | None = None
    color: str | None = None
    size: str | None = None
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class AdminCustomerInfoResponse(BaseModel):
    """Thông tin tóm tắt khách hàng đặt đơn."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    status: str


class AdminPaymentResponse(BaseModel):
    """Thông tin thanh toán của đơn hàng."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    method: str
    amount: Decimal
    status: str
    transaction_reference: str | None = None
    attempt_number: int


class AdminOrderDetailResponse(BaseModel):
    """Thông tin chi tiết toàn diện của một đơn hàng trong hệ thống dành cho Admin."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_code: str
    customer_id: int
    customer: AdminCustomerInfoResponse | None = None
    store_id: int | None = None
    total_price: Decimal
    shipping_address: str
    status: str
    created_at: datetime
    updated_at: datetime
    items: list[AdminOrderItemResponse] = Field(default_factory=list)
    payment: AdminPaymentResponse | None = None
    audit_logs: list[AdminOrderAuditLogResponse] = Field(default_factory=list)
    status_history: list[OrderStatusHistoryResponse] = Field(default_factory=list)


class AdminOrderListResponse(BaseModel):
    """Danh sách đơn hàng toàn hệ thống kèm thông tin phân trang."""
    model_config = ConfigDict(from_attributes=True)

    items: list[AdminOrderDetailResponse] = Field(default_factory=list)
    total: int
    page: int
    limit: int
    total_pages: int


class AdminOrderActionResponse(BaseModel):
    """Phản hồi sau khi Admin thực hiện thao tác quan trọng trên đơn hàng."""
    model_config = ConfigDict(from_attributes=True)

    message: str = Field(..., description="Thông báo kết quả")
    order_code: str = Field(..., description="Mã đơn hàng")
    previous_status: str = Field(..., description="Trạng thái trước khi chuyển đổi")
    current_status: str = Field(..., description="Trạng thái hiện tại")
    reason: str | None = Field(None, description="Lý do hoặc ghi chú")
    audit_log_id: int = Field(..., description="Mã bản ghi Audit Log được tạo")
    updated_at: datetime = Field(..., description="Thời gian cập nhật")
