"""Model cho chi tiết sản phẩm trong giỏ hàng (CartItem)."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.cart import Cart
    from app.models.variant import ProductVariant


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        # Ràng buộc duy nhất đảm bảo mỗi biến thể chỉ xuất hiện 1 lần trong 1 giỏ hàng
        UniqueConstraint("cart_id", "variant_id", name="uk_cart_item_cart_variant"),
        # Ràng buộc kiểm tra số lượng phải > 0 ở mức Database
        CheckConstraint("quantity > 0", name="ck_cart_items_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cart_id: Mapped[int] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Quan hệ N-1 với Cart
    cart: Mapped[Cart] = relationship("Cart", back_populates="items")

    # Quan hệ N-1 với Variant (ProductVariant)
    variant: Mapped[ProductVariant] = relationship(
        "ProductVariant", back_populates="cart_items"
    )

    @validates("quantity")
    def validate_quantity(self, key: str, value: int) -> int:
        """Tiêu chí chấp nhận: Số lượng CartItem phải > 0."""
        if value is None or value <= 0:
            raise ValueError(
                f"Số lượng sản phẩm trong giỏ hàng phải lớn hơn 0 (nhận được {value})"
            )
        return value
