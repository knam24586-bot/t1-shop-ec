"""Model cho chi tiết đơn hàng (OrderItem)."""
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
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
        index=True,
    )
    # Đơn giá snapshot tại thời điểm mua (không thay đổi khi giá sản phẩm đổi)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Số lượng mua
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # Thành tiền = unit_price * quantity
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Quan hệ N-1 với Order
    order: Mapped[Order] = relationship("Order", back_populates="items")

    # Quan hệ N-1 với Product
    product: Mapped[Product | None] = relationship("Product")

    @validates("quantity")
    def validate_quantity(self, key: str, value: int) -> int:
        if value is None or value <= 0:
            raise ValueError(f"Số lượng mục đơn hàng phải lớn hơn 0 (nhận được {value})")
        return value

    @staticmethod
    def create_item(
        order: Order,
        unit_price: Decimal,
        quantity: int = 1,
        product_id: int | None = None,
    ) -> OrderItem:
        """Tạo mục đơn hàng và tự động tính line_total."""
        if quantity <= 0:
            raise ValueError(f"Số lượng phải lớn hơn 0 (nhận được {quantity})")
        line_total = unit_price * Decimal(quantity)
        item = OrderItem(
            order=order,
            product_id=product_id,
            unit_price=unit_price,
            quantity=quantity,
            line_total=line_total,
        )
        return item

