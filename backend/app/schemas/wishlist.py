"""Schemas Pydantic cho Wishlist APIs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class WishlistAddRequest(BaseModel):
    """Dữ liệu gửi lên khi thêm sản phẩm vào Wishlist."""
    product_id: int = Field(..., gt=0, description="ID của sản phẩm muốn thêm vào danh sách yêu thích")


class WishlistItemCreate(WishlistAddRequest):
    """Alias cho WishlistAddRequest."""
    pass


class WishlistProductResponse(BaseModel):
    """Thông tin tóm tắt sản phẩm trong Wishlist."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    price: Decimal
    stock: int
    image_url: str | None = None
    status: str


class WishlistItemResponse(BaseModel):
    """Phản hồi thông tin một mục trong Wishlist."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID của mục wishlist")
    user_id: int = Field(..., description="ID của người dùng sở hữu")
    product_id: int = Field(..., description="ID của sản phẩm")
    created_at: datetime = Field(..., description="Thời gian thêm vào wishlist")

    # Chi tiết sản phẩm đi kèm (thuận tiện cho frontend hiển thị)
    product_name: str | None = Field(None, description="Tên sản phẩm")
    product_slug: str | None = Field(None, description="Slug sản phẩm")
    product_price: Decimal | None = Field(None, description="Giá sản phẩm")
    product_stock: int | None = Field(None, description="Tồn kho sản phẩm")
    product_image_url: str | None = Field(None, description="Hình ảnh sản phẩm")
    product_status: str | None = Field(None, description="Trạng thái sản phẩm")
    product: WishlistProductResponse | None = Field(None, description="Đối tượng sản phẩm đầy đủ")


class WishlistResponse(BaseModel):
    """Thông tin tổng quan danh sách yêu thích."""
    model_config = ConfigDict(from_attributes=True)

    total_items: int = Field(..., description="Tổng số sản phẩm trong wishlist")
    items: list[WishlistItemResponse] = Field(default_factory=list, description="Danh sách các mục yêu thích")


class WishlistActionMessage(BaseModel):
    """Phản hồi thông báo hành động thêm/xóa trong wishlist."""
    message: str = Field(..., description="Thông báo kết quả thao tác")
    item: WishlistItemResponse | None = Field(None, description="Chi tiết mục được thêm/xử lý (nếu có)")

