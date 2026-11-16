"""Model cho chi tiết đơn hàng (OrderItem) với cơ chế snapshot giá và số lượng."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.product import Product
    from app.models.variant import ProductVariant


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_nonnegative"),
        CheckConstraint("line_total >= 0", name="ck_order_items_line_total_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    # Khóa ngoại liên kết tới biến thể sản phẩm (ProductVariant)
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
        index=True,
    )
    # Khóa ngoại liên kết tới sản phẩm gốc (Product)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
        index=True,
    )

    # Đơn giá snapshot tại thời điểm đặt đơn (bất biến dù giá Product sau này thay đổi)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Số lượng đặt mua (> 0)
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    # Thành tiền snapshot = unit_price * quantity
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Quan hệ N-1 với Order
    order: Mapped[Order] = relationship("Order", back_populates="items")

    # Quan hệ N-1 với Variant (ProductVariant)
    variant: Mapped[ProductVariant | None] = relationship("ProductVariant")

    # Quan hệ N-1 với Product gốc
    product: Mapped[Product | None] = relationship("Product")

    @validates("quantity")
    def validate_quantity(self, key: str, value: int) -> int:
        if value is None or value <= 0:
            raise ValueError(f"Số lượng mục đơn hàng phải lớn hơn 0 (nhận được {value})")
        return value

    @validates("unit_price")
    def validate_unit_price(self, key: str, value: Decimal | float | int) -> Decimal:
        val = Decimal(str(value))
        if val < 0:
            raise ValueError(f"Đơn giá snapshot không được âm (nhận được {value})")
        return val

    @classmethod
    def from_variant(
        cls,
        order: Order,
        variant: ProductVariant,
        quantity: int = 1,
        unit_price: Decimal | None = None,
    ) -> OrderItem:
        """Tạo OrderItem từ ProductVariant, tự động snapshot giá và tính line_total.

        - unit_price: Nếu không truyền, snapshot giá hiện tại từ variant.product.price.
        - Dữ liệu này được lưu cố định và KHÔNG bị thay đổi khi giá Product thay đổi sau đó.
        """
        if quantity <= 0:
            raise ValueError(f"Số lượng phải lớn hơn 0 (nhận được {quantity})")

        # Snapshot giá: lấy giá tại thời điểm chốt đơn
        if unit_price is None:
            if hasattr(variant, "product") and variant.product is not None:
                price_snapshot = Decimal(str(variant.product.price))
            else:
                raise ValueError("Không thể xác định đơn giá snapshot từ ProductVariant.")
        else:
            price_snapshot = Decimal(str(unit_price))

        line_total_snapshot = price_snapshot * Decimal(quantity)

        item = cls(
            order=order,
            variant_id=variant.id,
            product_id=variant.product_id,
            unit_price=price_snapshot,
            quantity=quantity,
            line_total=line_total_snapshot,
        )
        return item

    @classmethod
    def create_item(
        cls,
        order: Order,
        unit_price: Decimal | float | int,
        quantity: int = 1,
        variant_id: int | None = None,
        product_id: int | None = None,
    ) -> OrderItem:
        """Tạo mục đơn hàng tuỳ biến với đơn giá snapshot chỉ định."""
        if quantity <= 0:
            raise ValueError(f"Số lượng phải lớn hơn 0 (nhận được {quantity})")

        price_snapshot = Decimal(str(unit_price))
        line_total_snapshot = price_snapshot * Decimal(quantity)

        item = cls(
            order=order,
            variant_id=variant_id,
            product_id=product_id,
            unit_price=price_snapshot,
            quantity=quantity,
            line_total=line_total_snapshot,
        )
        return item
