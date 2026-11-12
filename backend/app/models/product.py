"""Model cho bảng sản phẩm."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.category import Category

if TYPE_CHECKING:
    from app.models.variant import ProductVariant


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    stock: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Published", server_default="Published"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    category: Mapped[Category] = relationship(back_populates="products")
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )
