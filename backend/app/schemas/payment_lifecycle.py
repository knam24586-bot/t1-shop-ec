"""Schemas Pydantic cho Payment Lifecycle: Payment fail, callback lặp, hủy đơn và giải phóng hàng.
Tiêu chí chấp nhận:
1. Payment callback xử lý idempotent.
2. Thất bại/hết hạn giải phóng hàng đúng một lần.
3. Hủy đơn tuân thủ state machine.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class PaymentLifecycleCallbackRequest(BaseModel):
    """Dữ liệu callback / IPN từ cổng thanh toán có yêu cầu tự động giải phóng tồn kho khi thất bại."""
    transaction_reference: str = Field(..., description="Mã tham chiếu đối soát của giao dịch")
    method: str = Field(..., description="Cổng thanh toán gửi callback (VNPAY, MOMO, ZALOPAY...)")
    response_code: str = Field("00", description="Mã phản hồi từ cổng ('00' là thành công, mã khác là thất bại)")
    secure_hash: str | None = Field(None, description="Chữ ký HMAC xác thực tính toàn vẹn")
    extra_params: dict[str, Any] | None = Field(None, description="Các tham số bổ sung từ cổng thanh toán")


class PaymentLifecycleCallbackResponse(BaseModel):
    """Kết quả xử lý callback thanh toán kèm thông tin giải phóng tồn kho."""
    model_config = ConfigDict(from_attributes=True)

    success: bool = Field(..., description="Trạng thái xử lý thanh toán thành công hay thất bại")
    is_idempotent: bool = Field(False, description="Đánh dấu callback là request lặp đã được ghi nhận trước đó")
    message: str = Field(..., description="Thông báo kết quả xử lý")
    order_code: str = Field(..., description="Mã đơn hàng liên quan")
    order_status: str = Field(..., description="Trạng thái hiện tại của đơn hàng sau khi xử lý")
    payment_status: str = Field(..., description="Trạng thái hiện tại của giao dịch thanh toán")
    transaction_reference: str = Field(..., description="Mã tham chiếu giao dịch")
    inventory_released: bool = Field(False, description="Xác nhận tồn kho đã được giải phóng/hoàn lại trong lần gọi này")
    restocked_items_count: int = Field(0, description="Số lượng sản phẩm đã được hoàn lại vào kho")


class ExpirePaymentRequest(BaseModel):
    """Dữ liệu yêu cầu xử lý hết hạn thanh toán và giải phóng tồn kho."""
    transaction_reference: str | None = Field(None, description="Mã tham chiếu giao dịch cần hết hạn")
    order_code: str | None = Field(None, description="Mã đơn hàng cần hết hạn thanh toán")
    reason: str = Field("Giao dịch thanh toán trực tuyến đã hết hạn", description="Lý do hết hạn")


class ExpirePaymentResponse(BaseModel):
    """Kết quả xử lý thanh toán hết hạn và giải phóng tồn kho."""
    model_config = ConfigDict(from_attributes=True)

    message: str = Field(..., description="Thông báo kết quả thao tác")
    order_code: str = Field(..., description="Mã đơn hàng")
    payment_status: str = Field(..., description="Trạng thái thanh toán (CANCELLED/FAILED)")
    order_status: str = Field(..., description="Trạng thái đơn hàng (CANCELLED)")
    is_idempotent: bool = Field(False, description="Xác nhận yêu cầu hết hạn là thao tác lặp")
    inventory_released: bool = Field(False, description="Xác nhận hàng đã được giải phóng đúng một lần")
    restocked_items_count: int = Field(0, description="Tổng số lượng sản phẩm được hoàn vào kho")
    expired_at: datetime = Field(..., description="Thời điểm xử lý hết hạn")


class StateMachineCancelOrderRequest(BaseModel):
    """Dữ liệu yêu cầu hủy đơn hàng theo State Machine."""
    order_code: str = Field(..., min_length=3, description="Mã đơn hàng cần hủy")
    reason: str = Field(..., min_length=3, max_length=500, description="Lý do hủy đơn hàng (tối thiểu 3 ký tự)")
    cancelled_by: str = Field("CUSTOMER", description="Vai trò người thực hiện hủy: CUSTOMER, VENDOR, ADMIN, SYSTEM")


class StateMachineCancelOrderResponse(BaseModel):
    """Phản hồi sau khi hủy đơn hàng tuân thủ State Machine."""
    model_config = ConfigDict(from_attributes=True)

    message: str = Field(..., description="Thông báo kết quả")
    order_code: str = Field(..., description="Mã đơn hàng đã hủy")
    previous_status: str = Field(..., description="Trạng thái trước khi hủy")
    current_status: str = Field(..., description="Trạng thái sau khi hủy (CANCELLED)")
    reason: str = Field(..., description="Lý do hủy đơn")
    cancelled_by: str = Field(..., description="Người/Vai trò thực hiện hủy")
    inventory_released: bool = Field(..., description="Xác nhận tồn kho được giải phóng đúng một lần")
    restocked_items_count: int = Field(..., description="Số lượng sản phẩm đã hoàn tồn")
    cancelled_at: datetime = Field(..., description="Thời điểm hủy đơn")


class OrderStateTransitionsResponse(BaseModel):
    """Thông tin về các trạng thái hợp lệ có thể chuyển tiếp theo State Machine."""
    order_code: str = Field(..., description="Mã đơn hàng")
    current_status: str = Field(..., description="Trạng thái hiện tại của đơn hàng")
    allowed_next_statuses: list[str] = Field(..., description="Danh sách trạng thái tiếp theo hợp lệ theo State Machine")
    is_terminal: bool = Field(..., description="Đơn hàng đã ở trạng thái kết thúc (DELIVERED hoặc CANCELLED) hay chưa")
