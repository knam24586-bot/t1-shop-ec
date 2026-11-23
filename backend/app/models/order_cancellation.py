"""Model lưu vết hủy đơn hàng (OrderCancellation) và giải phóng tồn kho.
Đảm bảo:
1. Lưu lý do hủy đơn (reason).
2. Lưu người thực hiện hủy và thời gian hủy.
3. Ràng buộc unique order_id để đảm bảo mỗi đơn hàng chỉ có tối đa 1 bản ghi hủy.
4. Đánh dấu trạng thái giải phóng tồn kho (inventory_restocked) để bảo đảm hoàn tồn đúng 1 lần.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.user import User


class OrderCancellation(Base):
    __tablename__ = "order_cancellations"
    __table_args__ = (
        UniqueConstraint("order_id", name="uk_order_cancellations_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    order_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    cancelled_by: Mapped[str] = mapped_column(
        String(50), nullable=False, default="CUSTOMER", server_default="CUSTOMER"
    )
    inventory_restocked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    cancelled_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    order: Mapped[Order] = relationship("Order")
    user: Mapped[User] = relationship("User")
