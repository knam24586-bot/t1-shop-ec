"""Model cho giỏ hàng người dùng (Cart)."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.cart_item import CartItem
    from app.models.user import User


class Cart(Base):
    __tablename__ = "carts"
    __table_args__ = (
        UniqueConstraint("user_id", name="uk_carts_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="Active", server_default="Active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Quan hệ 1-1 với chủ sở hữu (User)
    user: Mapped[User] = relationship("User", back_populates="cart")

    # Quan hệ 1-N với chi tiết giỏ hàng (CartItem)
    items: Mapped[list[CartItem]] = relationship(
        "CartItem",
        back_populates="cart",
        cascade="all, delete-orphan",
    )

    # ---------------------------------------------------------
    # Các hàm nghiệp vụ: Kiểm soát item trùng theo quy tắc gộp giỏ
    # ---------------------------------------------------------
    def add_item(self, variant_id: int, quantity: int = 1) -> CartItem:
        """Quy tắc gộp giỏ (Cart Merge Rule):
        - Nếu variant_id đã tồn tại trong giỏ hàng: cộng dồn số lượng (gộp giỏ).
        - Nếu variant_id chưa có trong giỏ hàng: tạo mới CartItem.
        - Ràng buộc: số lượng > 0.
        """
        if quantity <= 0:
            raise ValueError(
                f"Số lượng thêm vào giỏ phải lớn hơn 0 (nhận được {quantity})"
            )

        for item in self.items:
            if item.variant_id == variant_id:
                item.quantity += quantity
                return item

        from app.models.cart_item import CartItem

        new_item = CartItem(cart=self, variant_id=variant_id, quantity=quantity)
        self.items.append(new_item)
        return new_item

    def update_item_quantity(self, variant_id: int, quantity: int) -> CartItem:
        """Cập nhật số lượng của một biến thể trong giỏ hàng.
        Yêu cầu số lượng > 0.
        """
        if quantity <= 0:
            raise ValueError(
                f"Số lượng cập nhật phải lớn hơn 0 (nhận được {quantity})"
            )

        for item in self.items:
            if item.variant_id == variant_id:
                item.quantity = quantity
                return item

        raise ValueError(f"Không tìm thấy biến thể {variant_id} trong giỏ hàng.")

    def remove_item(self, variant_id: int) -> bool:
        """Xoá một biến thể khỏi giỏ hàng."""
        for item in self.items:
            if item.variant_id == variant_id:
                self.items.remove(item)
                return True
        return False

    def merge_cart(self, source_items: list[CartItem]) -> None:
        """Quy tắc gộp giỏ hàng (ví dụ: giỏ hàng vãng lai khi đăng nhập):
        Duyệt qua danh sách item từ giỏ hàng nguồn, nếu trùng biến thể thì cộng dồn số lượng.
        """
        for item in source_items:
            self.add_item(variant_id=item.variant_id, quantity=item.quantity)
