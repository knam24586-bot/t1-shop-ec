"""Schemas Pydantic cho Order Cancellation APIs."""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CancelOrderRequest(BaseModel):
    """Dữ liệu yêu cầu hủy đơn hàng."""
    reason: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Lý do hủy đơn hàng (bắt buộc, tối thiểu 3 ký tự)",
        examples=["Tôi đặt nhầm kích cỡ, muốn hủy để đặt lại"],
    )


class CancelOrderByCodeRequest(BaseModel):
    """Dữ liệu yêu cầu hủy đơn hàng khi truyền mã đơn trong request body."""
    order_code: str = Field(..., min_length=3, description="Mã đơn hàng cần hủy")
    reason: str = Field(..., min_length=3, max_length=500, description="Lý do hủy đơn hàng")


class OrderCancellationInfoResponse(BaseModel):
    """Thông tin chi tiết về việc hủy đơn hàng đã lưu."""
    model_config = ConfigDict(from_attributes=True)

    order_id: int = Field(..., description="ID của đơn hàng")
    order_code: str = Field(..., description="Mã đơn hàng")
    user_id: int = Field(..., description="ID người dùng đã hủy")
    reason: str = Field(..., description="Lý do hủy đơn")
    cancelled_by: str = Field(..., description="Người hủy (CUSTOMER, ADMIN...)")
    inventory_restocked: bool = Field(..., description="Trạng thái đã hoàn trả tồn kho chưa")
    cancelled_at: datetime = Field(..., description="Thời điểm hủy đơn")


class CancelOrderResponse(BaseModel):
    """Phản hồi sau khi hủy đơn hàng và hoàn tồn thành công."""
    model_config = ConfigDict(from_attributes=True)

    message: str = Field(..., description="Thông báo kết quả thao tác")
    order_code: str = Field(..., description="Mã đơn hàng đã hủy")
    previous_status: str = Field(..., description="Trạng thái trước khi hủy")
    current_status: str = Field(..., description="Trạng thái hiện tại sau khi hủy (CANCELLED)")
    reason: str = Field(..., description="Lý do hủy đơn đã lưu vào hệ thống")
    cancelled_at: datetime = Field(..., description="Thời điểm hủy đơn")
    inventory_restocked: bool = Field(..., description="Xác nhận tồn kho đã được giải phóng")
    restocked_items_count: int = Field(..., description="Tổng số lượng sản phẩm đã hoàn vào kho")
