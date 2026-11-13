"""Model cho thanh toán (Payment) và quản lý trạng thái giao dịch."""
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
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.order import Order


class PaymentStatus(str, Enum):
    """Trạng thái của một giao dịch thanh toán."""
    PENDING = "PENDING"          # Đang chờ xử lý / chờ xác nhận từ cổng thanh toán
    SUCCESS = "SUCCESS"          # Giao dịch thanh toán thành công
    FAILED = "FAILED"            # Giao dịch thất bại (lỗi thẻ, hết tiền, timeout...)
    CANCELLED = "CANCELLED"      # Người dùng chủ động huỷ giao dịch
    REFUNDED = "REFUNDED"        # Đã hoàn tiền cho giao dịch


class PaymentMethod(str, Enum):
    """Các phương thức thanh toán hỗ trợ."""
    COD = "COD"                  # Thanh toán khi nhận hàng
    VNPAY = "VNPAY"              # Cổng thanh toán VNPAY
    MOMO = "MOMO"                # Ví điện tử MoMo
    ZALOPAY = "ZALOPAY"          # Ví điện tử ZaloPay
    BANK_TRANSFER = "BANK_TRANSFER"  # Chuyển khoản ngân hàng
    CREDIT_CARD = "CREDIT_CARD"  # Thẻ tín dụng / ghi nợ quốc tế


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        # Thiết kế hỗ trợ nhiều lần thử:
        # Mỗi đơn hàng có thể có nhiều lần thử (attempt_number 1, 2, 3...)
        # và số thứ tự lần thử trong cùng một đơn hàng là duy nhất
        UniqueConstraint("order_id", "attempt_number", name="uk_payments_order_attempt"),
        # Mã tham chiếu giao dịch là duy nhất (nếu có)
        UniqueConstraint("transaction_reference", name="uk_payments_transaction_ref"),
        # Số tiền thanh toán phải lớn hơn 0
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        # Số thứ tự lần thử phải từ 1 trở lên
        CheckConstraint("attempt_number >= 1", name="ck_payments_attempt_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Đơn hàng cần thanh toán (1 đơn hàng có thể có nhiều lần thử thanh toán)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )

    # Phương thức thanh toán (COD, VNPAY, MOMO...)
    method: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Số tiền thanh toán
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Trạng thái giao dịch
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=PaymentStatus.PENDING.value,
        server_default=PaymentStatus.PENDING.value,
        index=True,
    )

    # Mã tham chiếu giao dịch từ cổng thanh toán (hoặc mã đối soát nội bộ)
    transaction_reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )

    # Số thứ tự của lần thử thanh toán (Attempt 1, 2, 3...)
    attempt_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
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

    # Quan hệ N-1 với đơn hàng Order (Đơn hướng, không sửa file order.py có sẵn)
    order: Mapped[Order] = relationship("Order")

    # -------------------------------------------------------------
    # Validations
    # -------------------------------------------------------------
    @validates("amount")
    def validate_amount(self, key: str, value: Decimal | float | int) -> Decimal:
        val = Decimal(str(value))
        if val <= 0:
            raise ValueError(f"Số tiền thanh toán phải lớn hơn 0 (nhận được {value})")
        return val

    @validates("attempt_number")
    def validate_attempt_number(self, key: str, value: int) -> int:
        if value is None or value < 1:
            raise ValueError(f"Số thứ tự lần thử phải lớn hơn hoặc bằng 1 (nhận được {value})")
        return value

    # -------------------------------------------------------------
    # Các hàm nghiệp vụ: Trạng thái giao dịch & Hỗ trợ thử lại (Retry)
    # -------------------------------------------------------------
    @staticmethod
    def generate_transaction_ref(
        method: PaymentMethod | str,
        order_id: int,
        attempt_number: int = 1,
    ) -> str:
        """Tự động sinh mã tham chiếu giao dịch đối soát duy nhất.
        Định dạng: METHOD-ORD{order_id}-ATT{attempt_number}-YYYYMMDDHHMMSS-UUID
        """
        method_str = method.value if isinstance(method, PaymentMethod) else str(method).upper()
        date_str = datetime.now().strftime("%Y%m%d%H%M%S")
        short_id = uuid.uuid4().hex[:6].upper()
        return f"{method_str}-ORD{order_id}-ATT{attempt_number}-{date_str}-{short_id}"

    def mark_as_success(self, transaction_reference: str | None = None) -> None:
        """Đánh dấu giao dịch thanh toán thành công."""
        self.status = PaymentStatus.SUCCESS.value
        if transaction_reference:
            self.transaction_reference = transaction_reference

    def mark_as_failed(self, reason: str | None = None) -> None:
        """Đánh dấu giao dịch thanh toán thất bại."""
        self.status = PaymentStatus.FAILED.value

    def mark_as_cancelled(self) -> None:
        """Đánh dấu giao dịch bị người dùng huỷ bỏ."""
        self.status = PaymentStatus.CANCELLED.value

    def can_retry(self) -> bool:
        """Kiểm tra xem đơn hàng có thể tạo lần thử thanh toán tiếp theo hay không.
        Chỉ cho phép thử lại khi lần thử hiện tại thất bại (FAILED) hoặc bị huỷ (CANCELLED).
        """
        return self.status in {PaymentStatus.FAILED.value, PaymentStatus.CANCELLED.value}

    def create_retry_attempt(
        self,
        new_method: PaymentMethod | str | None = None,
        new_amount: Decimal | float | int | None = None,
    ) -> Payment:
        """Tạo lần thử thanh toán tiếp theo (attempt_number tự tăng 1).
        Hỗ trợ đổi phương thức thanh toán mới hoặc giữ nguyên.
        """
        if not self.can_retry():
            raise ValueError(
                f"Không thể thử lại thanh toán khi giao dịch hiện tại đang ở trạng thái '{self.status}'."
            )

        method = new_method if new_method is not None else self.method
        method_str = method.value if isinstance(method, PaymentMethod) else str(method)
        amount = Decimal(str(new_amount)) if new_amount is not None else self.amount
        next_attempt = self.attempt_number + 1

        retry_payment = Payment(
            order_id=self.order_id,
            method=method_str,
            amount=amount,
            attempt_number=next_attempt,
            status=PaymentStatus.PENDING.value,
        )
        return retry_payment

