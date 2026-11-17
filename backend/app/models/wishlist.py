"""Model cho bảng danh sách yêu thích (Wishlist)."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.user import User


class Wishlist(Base):
    __tablename__ = "wishlists"
    __table_args__ = (
        # Ràng buộc duy nhất: Một user không thể thêm cùng 1 sản phẩm nhiều lần vào wishlist
        UniqueConstraint("user_id", "product_id", name="uk_wishlist_user_product"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships (lazy="joined" để nạp sẵn product khi query, tránh DetachedInstanceError)
    user: Mapped[User] = relationship("User")
    product: Mapped[Product] = relationship("Product", lazy="joined")

    def __repr__(self) -> str:
        return f"<Wishlist id={self.id} user_id={self.user_id} product_id={self.product_id}>"


# Alias thuận tiện
WishlistItem = Wishlist
