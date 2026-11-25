"""Model lưu vết kiểm toán (Audit Log) cho các thao tác quan trọng của Admin đối với đơn hàng.
Tiêu chí chấp nhận:
- Thao tác quan trọng của Admin (cập nhật trạng thái, can thiệp hủy đơn, ghi chú) đều được ghi log đầy đủ.
- Lưu trữ admin_id, order_id, order_code, action, previous_status, new_status, reason, ip_address, created_at.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.user import User


class AdminOrderAuditLog(Base):
    __tablename__ = "admin_order_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    order_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    admin_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    previous_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    order: Mapped[Order] = relationship("Order")
    admin: Mapped[User] = relationship("User")
