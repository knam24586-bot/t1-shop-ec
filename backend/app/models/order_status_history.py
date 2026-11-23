"""Model lưu vết lịch sử chuyển đổi trạng thái đơn hàng (OrderStatusHistory).
Lưu lại:
- order_id, order_code, store_id
- previous_status, new_status
- reason (bắt buộc khi từ chối/hủy đơn)
- changed_by_role (VENDOR, ADMIN, CUSTOMER, SYSTEM)
- changed_by_user_id
- created_at
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.order import Order


class OrderStatusHistory(Base):
    __tablename__ = "order_status_histories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    order_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    store_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    previous_status: Mapped[str] = mapped_column(String(30), nullable=False)
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_by_role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="VENDOR", server_default="VENDOR"
    )
    changed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    order: Mapped[Order] = relationship("Order")
