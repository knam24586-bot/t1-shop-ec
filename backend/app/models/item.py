"""Model cho bảng items."""
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )