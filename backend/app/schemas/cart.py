"""Schemas Pydantic cho Cart và CartItem APIs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class CartItemAdd(BaseModel):
    """Dữ liệu gửi lên khi thêm sản phẩm vào giỏ."""
    variant_id: int = Field(..., gt=0, description="ID của biến thể sản phẩm")
    quantity: int = Field(1, gt=0, description="Số lượng muốn thêm (phải > 0)")


class CartItemUpdate(BaseModel):
    """Dữ liệu gửi lên khi cập nhật số lượng sản phẩm trong giỏ."""
    quantity: int = Field(..., gt=0, description="Số lượng cập nhật mới (phải > 0)")


class CartItemResponse(BaseModel):
    """Chi tiết từng mục sản phẩm trong giỏ hàng."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID của mục giỏ hàng (CartItem ID)")
    cart_id: int = Field(..., description="ID của giỏ hàng")
    variant_id: int = Field(..., description="ID của biến thể")
    product_id: int | None = Field(None, description="ID của sản phẩm gốc")
    product_name: str | None = Field(None, description="Tên sản phẩm")
    sku: str | None = Field(None, description="Mã SKU biến thể")
    color: str | None = Field(None, description="Màu sắc")
    size: str | None = Field(None, description="Kích cỡ")
    price: Decimal = Field(..., description="Đơn giá hiện tại")
    stock: int = Field(..., description="Số lượng tồn kho hiện tại")
    quantity: int = Field(..., description="Số lượng trong giỏ")
    line_total: Decimal = Field(..., description="Thành tiền = price * quantity")
    created_at: datetime
    updated_at: datetime


class CartResponse(BaseModel):
    """Thông tin tổng quan giỏ hàng của người dùng."""
    model_config = ConfigDict(from_attributes=True)

    cart_id: int = Field(..., description="ID giỏ hàng")
    user_id: int = Field(..., description="ID chủ sở hữu")
    status: str = Field(..., description="Trạng thái giỏ hàng")
    total_items: int = Field(0, description="Tổng số lượng sản phẩm trong giỏ")
    total_amount: Decimal = Field(Decimal("0.00"), description="Tổng giá trị giỏ hàng")
    items: list[CartItemResponse] = Field(default_factory=list, description="Danh sách các sản phẩm trong giỏ")


class CartActionMessage(BaseModel):
    """Phản hồi thông báo hành động giỏ hàng."""
    message: str
    cart: CartResponse

