"""Model cho người dùng (User)."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.cart import Cart


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="CUSTOMER", server_default="CUSTOMER"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Active", server_default="Active"
    )
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Quan hệ 1-1 với giỏ hàng: 1 user chỉ có tối đa 1 cart (uselist=False)
    cart: Mapped[Cart | None] = relationship(
        "Cart",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

