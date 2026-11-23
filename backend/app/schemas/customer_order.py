"""Schemas Pydantic cho Customer Order APIs.
Đảm bảo:
- Hỗ trợ xem danh sách (list) và chi tiết (detail) đơn hàng.
- Hỗ trợ phân trang (pagination) đầy đủ.
- Dữ liệu trả về chỉ chứa thông tin dành cho khách hàng, tuyệt đối KHÔNG chứa
  thông tin nội bộ (như password_hash, raw payment webhook payload, audit logs,
  ip_address, internal notes, secret credentials).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class CustomerOrderItemResponse(BaseModel):
    """Thông tin từng mục sản phẩm trong đơn hàng dành cho khách hàng."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Mã định danh của mục đơn hàng")
    product_id: int | None = Field(None, description="Mã sản phẩm")
    variant_id: int | None = Field(None, description="Mã biến thể")
    product_name: str | None = Field(None, description="Tên sản phẩm")
    sku: str | None = Field(None, description="Mã phân loại SKU sản phẩm")
    color: str | None = Field(None, description="Màu sắc sản phẩm")
    size: str | None = Field(None, description="Kích thước sản phẩm")
    image_url: str | None = Field(None, description="Hình ảnh sản phẩm")
    unit_price: Decimal = Field(..., description="Đơn giá snapshot tại thời điểm mua")
    quantity: int = Field(..., description="Số lượng đặt mua")
    line_total: Decimal = Field(..., description="Tổng tiền cho mục này = unit_price * quantity")


class CustomerOrderPaymentResponse(BaseModel):
    """Thông tin thanh toán công khai dành cho khách hàng (không lộ secret hay logs nội bộ)."""
    model_config = ConfigDict(from_attributes=True)

    method: str = Field(..., description="Phương thức thanh toán (COD, VNPAY, MOMO...)")
    amount: Decimal = Field(..., description="Số tiền cần thanh toán")
    status: str = Field(..., description="Trạng thái thanh toán (PENDING, SUCCESS, FAILED...)")
    transaction_reference: str | None = Field(None, description="Mã tham chiếu giao dịch hiển thị cho khách")


class CustomerOrderSummaryResponse(BaseModel):
    """Thông tin tóm tắt một đơn hàng trong danh sách của khách hàng."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Mã số đơn hàng")
    order_code: str = Field(..., description="Mã đơn hàng định danh công khai")
    total_price: Decimal = Field(..., description="Tổng giá trị đơn hàng sau giảm giá")
    shipping_address: str = Field(..., description="Địa chỉ nhận hàng snapshot")
    status: str = Field(..., description="Trạng thái đơn hàng (PENDING, CONFIRMED, DELIVERED...)")
    created_at: datetime = Field(..., description="Thời gian tạo đơn hàng")
    updated_at: datetime = Field(..., description="Thời gian cập nhật gần nhất")
    total_items: int = Field(default=0, description="Tổng số lượng sản phẩm trong đơn hàng")
    items: list[CustomerOrderItemResponse] = Field(default_factory=list, description="Danh sách sản phẩm trong đơn")
    payment: CustomerOrderPaymentResponse | None = Field(None, description="Thông tin thanh toán")


class CustomerOrderDetailResponse(BaseModel):
    """Thông tin chi tiết một đơn hàng của khách hàng."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Mã số đơn hàng")
    order_code: str = Field(..., description="Mã đơn hàng định danh công khai")
    total_price: Decimal = Field(..., description="Tổng giá trị đơn hàng sau giảm giá")
    shipping_address: str = Field(..., description="Địa chỉ giao hàng snapshot")
    status: str = Field(..., description="Trạng thái đơn hàng")
    created_at: datetime = Field(..., description="Thời gian tạo đơn hàng")
    updated_at: datetime = Field(..., description="Thời gian cập nhật gần nhất")
    total_items: int = Field(default=0, description="Tổng số lượng sản phẩm trong đơn")
    items: list[CustomerOrderItemResponse] = Field(default_factory=list, description="Chi tiết các sản phẩm trong đơn")
    payment: CustomerOrderPaymentResponse | None = Field(None, description="Thông tin thanh toán")


class CustomerOrderPaginationResponse(BaseModel):
    """Cấu trúc dữ liệu phân trang cho danh sách đơn hàng của khách hàng."""
    model_config = ConfigDict(from_attributes=True)

    items: list[CustomerOrderSummaryResponse] = Field(
        default_factory=list, description="Danh sách đơn hàng trên trang hiện tại"
    )
    orders: list[CustomerOrderSummaryResponse] = Field(
        default_factory=list, description="Alias tương thích cho items"
    )
    total: int = Field(..., description="Tổng số đơn hàng thỏa mãn điều kiện")
    total_orders: int = Field(..., description="Alias tương thích cho total")
    page: int = Field(..., description="Trang hiện tại (bắt đầu từ 1)")
    limit: int = Field(..., description="Số lượng đơn hàng tối đa trên mỗi trang")
    page_size: int = Field(..., description="Alias tương thích cho limit")
    total_pages: int = Field(..., description="Tổng số trang có sẵn")
    has_next: bool = Field(..., description="Có trang tiếp theo hay không")
    has_prev: bool = Field(..., description="Có trang trước đó hay không")
