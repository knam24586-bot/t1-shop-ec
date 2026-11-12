"""Model cho biến thể sản phẩm (ProductVariant)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.cart_item import CartItem
    from app.models.product import Product


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint("stock >= 0", name="ck_product_variants_stock_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    color: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stock: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")

    product: Mapped[Product] = relationship(back_populates="variants")
    cart_items: Mapped[list[CartItem]] = relationship(
        "CartItem",
        back_populates="variant",
        cascade="all, delete-orphan",
    )
