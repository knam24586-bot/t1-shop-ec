"""Model liên kết đơn hàng với cửa hàng (StoreOrder).
Cho phép xác định chính xác đơn hàng nào thuộc quyền quản lý của Store nào.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.store import Store


class StoreOrder(Base):
    __tablename__ = "store_orders"
    __table_args__ = (
        UniqueConstraint("order_id", name="uk_store_orders_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    order: Mapped[Order] = relationship("Order")
    store: Mapped[Store] = relationship("Store")
