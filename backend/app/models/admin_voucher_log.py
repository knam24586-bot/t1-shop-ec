"""Model lưu vết kiểm toán các thao tác quản trị Voucher của Admin (tạo, sửa, khóa, mở khóa)."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.voucher import Voucher


class AdminVoucherLog(Base):
    __tablename__ = "admin_voucher_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    voucher_id: Mapped[int] = mapped_column(
        ForeignKey("vouchers.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    voucher_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    admin_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    voucher: Mapped[Voucher] = relationship("Voucher")
    admin: Mapped[User] = relationship("User")
