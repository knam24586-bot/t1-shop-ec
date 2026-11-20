"""Schemas Pydantic cho Payment và Online Checkout APIs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class OnlineCheckoutRequest(BaseModel):
    """Dữ liệu yêu cầu khởi tạo thanh toán trực tuyến."""
    order_code: str = Field(..., min_length=5, description="Mã đơn hàng cần thanh toán (VD: ORD-20261120-ABCD)")
    method: str = Field(..., description="Cổng thanh toán online (VNPAY, MOMO, ZALOPAY, BANK_TRANSFER, CREDIT_CARD)")
    return_url: str | None = Field(None, description="URL chuyển hướng sau khi thanh toán xong trên cổng")


class OnlineCheckoutResponse(BaseModel):
    """Kết quả khởi tạo giao dịch thanh toán online."""
    model_config = ConfigDict(from_attributes=True)

    payment_id: int = Field(..., description="ID của bản ghi thanh toán trong DB")
    order_id: int = Field(..., description="ID đơn hàng")
    order_code: str = Field(..., description="Mã đơn hàng")
    method: str = Field(..., description="Phương thức thanh toán được chọn")
    amount: Decimal = Field(..., description="Số tiền cần thanh toán")
    status: str = Field(..., description="Trạng thái giao dịch (luôn là PENDING khi vừa khởi tạo)")
    transaction_reference: str = Field(..., description="Mã tham chiếu đối soát duy nhất")
    attempt_number: int = Field(..., description="Lần thử thanh toán thứ mấy của đơn")
    payment_url: str = Field(..., description="Đường dẫn chuyển hướng người dùng sang cổng thanh toán")
    payment_token: str = Field(..., description="Token giao dịch của cổng thanh toán")
    gateway_name: str = Field(..., description="Tên cổng thanh toán")
    created_at: datetime = Field(..., description="Thời điểm khởi tạo giao dịch")
    expires_at: datetime = Field(..., description="Thời hạn hiệu lực của URL thanh toán (sau thời gian này link hết hạn)")


class PaymentCallbackRequest(BaseModel):
    """Dữ liệu callback / IPN từ cổng thanh toán gửi về."""
    transaction_reference: str = Field(..., description="Mã tham chiếu đối soát của giao dịch")
    method: str = Field(..., description="Cổng thanh toán gửi callback")
    response_code: str = Field("00", description="Mã phản hồi từ cổng ('00' là thành công)")
    secure_hash: str | None = Field(None, description="Chữ ký hash để xác thực tính toàn vẹn")


class PaymentCallbackResponse(BaseModel):
    """Kết quả xử lý callback thanh toán."""
    success: bool
    message: str
    order_code: str
    order_status: str
    payment_status: str
    transaction_reference: str

