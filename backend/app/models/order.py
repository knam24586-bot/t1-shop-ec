"""Model cho đơn hàng (Order) và quản lý trạng thái đơn."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.order_item import OrderItem
    from app.models.user import User


class OrderStatus(str, Enum):
    """Định nghĩa các trạng thái của đơn hàng trong vòng đời."""
    PENDING = "PENDING"          # Đơn hàng mới tạo, chờ xác nhận / thanh toán
    CONFIRMED = "CONFIRMED"      # Đã xác nhận đơn hàng
    PROCESSING = "PROCESSING"    # Đang đóng gói / chuẩn bị hàng
    SHIPPED = "SHIPPED"          # Đang vận chuyển
    DELIVERED = "DELIVERED"      # Đã giao thành công
    CANCELLED = "CANCELLED"      # Đơn hàng đã bị huỷ


# Quy tắc chuyển đổi trạng thái hợp lệ (State Machine Transition Map)
VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PENDING.value: {
        OrderStatus.CONFIRMED.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.CONFIRMED.value: {
        OrderStatus.PROCESSING.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.PROCESSING.value: {
        OrderStatus.SHIPPED.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.SHIPPED.value: {
        OrderStatus.DELIVERED.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.DELIVERED.value: set(),  # Trạng thái kết thúc, không thể đổi
    OrderStatus.CANCELLED.value: set(),  # Trạng thái kết thúc, không thể đổi
}


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        # Mã đơn duy nhất trên toàn hệ thống
        UniqueConstraint("order_code", name="uk_orders_code"),
        # Tổng tiền không được âm
        CheckConstraint("total_price >= 0", name="ck_orders_total_price_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Mã đơn: Chuỗi định danh duy nhất (VD: ORD-20261113-ABCD)
    order_code: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True, index=True
    )
    # Khách hàng đặt hàng
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    # Tổng tiền đơn hàng
    total_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    # Địa chỉ snapshot: Lưu nguyên vẹn địa chỉ giao hàng tại thời điểm đặt đơn
    shipping_address: Mapped[str] = mapped_column(String(255), nullable=False)
    # Trạng thái đơn hàng
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=OrderStatus.PENDING.value,
        server_default=OrderStatus.PENDING.value,
        index=True,
    )
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Quan hệ với khách hàng (User)
    customer: Mapped[User] = relationship("User")

    # Quan hệ 1-N với chi tiết đơn hàng (OrderItem)
    items: Mapped[list[OrderItem]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )

    # -------------------------------------------------------------
    # Các hàm nghiệp vụ: Trạng thái đơn và Tính toán
    # -------------------------------------------------------------
    @staticmethod
    def generate_order_code(prefix: str = "ORD") -> str:
        """Tự động sinh mã đơn duy nhất định dạng: ORD-YYYYMMDD-UUID."""
        date_str = datetime.now().strftime("%Y%m%d")
        short_id = uuid.uuid4().hex[:8].upper()
        return f"{prefix}-{date_str}-{short_id}"

    def can_transition_to(self, new_status: OrderStatus | str) -> bool:
        """Kiểm tra việc chuyển đổi sang trạng thái mới có hợp lệ không."""
        status_value = (
            new_status.value if isinstance(new_status, OrderStatus) else str(new_status)
        )
        allowed = VALID_STATUS_TRANSITIONS.get(self.status, set())
        return status_value in allowed

    def transition_to(self, new_status: OrderStatus | str) -> None:
        """Chuyển trạng thái đơn hàng theo quy tắc vòng đời."""
        status_value = (
            new_status.value if isinstance(new_status, OrderStatus) else str(new_status)
        )
        if not self.can_transition_to(status_value):
            raise ValueError(
                f"Không thể chuyển trạng thái đơn hàng từ '{self.status}' sang '{status_value}'."
            )
        self.status = status_value

    def calculate_total(self) -> Decimal:
        """Tính lại tổng tiền dựa trên danh sách các mục trong đơn hàng."""
        total = sum((item.line_total for item in self.items), Decimal("0.00"))
        self.total_price = total
        return total

