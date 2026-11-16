"""Model cho mã giảm giá (Voucher) và quy tắc giảm giá."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.session import Base


class DiscountType(str, Enum):
    """Kiểu giảm giá của Voucher."""
    PERCENTAGE = "PERCENTAGE"        # Giảm theo tỷ lệ phần trăm (VD: 10%, 20%)
    FIXED_AMOUNT = "FIXED_AMOUNT"    # Giảm theo số tiền cố định (VD: 50.000đ, 100.000đ)


class VoucherStatus(str, Enum):
    """Trạng thái của Voucher."""
    ACTIVE = "ACTIVE"        # Đang kích hoạt, sẵn sàng sử dụng
    INACTIVE = "INACTIVE"    # Đang tạm ngưng bởi quản trị viên
    EXPIRED = "EXPIRED"      # Đã hết hạn sử dụng
    DEPLETED = "DEPLETED"    # Đã hết số lượt sử dụng


class Voucher(Base):
    __tablename__ = "vouchers"
    __table_args__ = (
        # Mã voucher duy nhất
        UniqueConstraint("code", name="uk_vouchers_code"),
        # Giá trị giảm phải > 0
        CheckConstraint("discount_value > 0", name="ck_vouchers_discount_value_positive"),
        # Giá trị đơn tối thiểu không được âm
        CheckConstraint("min_order_amount >= 0", name="ck_vouchers_min_order_amount_nonnegative"),
        # Thời gian kết thúc phải sau hoặc bằng thời gian bắt đầu
        CheckConstraint("valid_to >= valid_from", name="ck_vouchers_date_range"),
        # Số lượt đã dùng không âm
        CheckConstraint("used_count >= 0", name="ck_vouchers_used_count_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Mã voucher duy nhất (VD: T1CHAMPION, SUMMER2026)
    code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )

    # Tên và mô tả voucher
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Kiểu giảm giá: PERCENTAGE hoặc FIXED_AMOUNT
    discount_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DiscountType.PERCENTAGE.value,
        server_default=DiscountType.PERCENTAGE.value,
    )

    # Giá trị giảm: Tỷ lệ % (1-100) hoặc Số tiền cố định (> 0)
    discount_value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )

    # Mức giảm tối đa (Áp dụng khi discount_type là PERCENTAGE, ví dụ giảm 20% tối đa 100.000đ)
    max_discount_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    # Điều kiện áp dụng: Giá trị đơn hàng tối thiểu
    min_order_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    # Thời hạn hiệu lực
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Giới hạn số lượt dùng (None = Không giới hạn)
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Số lượt đã sử dụng
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Trạng thái voucher
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=VoucherStatus.ACTIVE.value,
        server_default=VoucherStatus.ACTIVE.value,
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

    def __init__(self, **kwargs):
        kwargs.setdefault("status", VoucherStatus.ACTIVE.value)
        kwargs.setdefault("min_order_amount", Decimal("0.00"))
        kwargs.setdefault("discount_type", DiscountType.PERCENTAGE.value)
        kwargs.setdefault("used_count", 0)
        super().__init__(**kwargs)

    # -------------------------------------------------------------
    # Validations ở tầng Model
    # -------------------------------------------------------------
    @validates("code")
    def validate_code(self, key: str, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Mã voucher không được để trống.")
        return value.strip().upper()

    @validates("discount_value")
    def validate_discount_value(self, key: str, value: Decimal | float | int) -> Decimal:
        val = Decimal(str(value))
        if val <= 0:
            raise ValueError(f"Giá trị giảm giá phải lớn hơn 0 (nhận được {value}).")
        if self.discount_type == DiscountType.PERCENTAGE.value and val > Decimal("100.00"):
            raise ValueError(f"Giảm giá phần trăm không được vượt quá 100% (nhận được {value}%).")
        return val

    @validates("min_order_amount")
    def validate_min_order_amount(self, key: str, value: Decimal | float | int) -> Decimal:
        val = Decimal(str(value))
        if val < 0:
            raise ValueError(f"Giá trị đơn hàng tối thiểu không được âm (nhận được {value}).")
        return val

    @validates("max_discount_amount")
    def validate_max_discount_amount(self, key: str, value: Decimal | float | int | None) -> Decimal | None:
        if value is None:
            return None
        val = Decimal(str(value))
        if val <= 0:
            raise ValueError(f"Mức giảm tối đa phải lớn hơn 0 (nhận được {value}).")
        return val

    @validates("usage_limit")
    def validate_usage_limit(self, key: str, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError(f"Giới hạn lượt dùng phải từ 1 trở lên (nhận được {value}).")
        return value

    @validates("used_count")
    def validate_used_count(self, key: str, value: int) -> int:
        if value is None or value < 0:
            raise ValueError(f"Số lượt đã dùng không được âm (nhận được {value}).")
        return value

    # -------------------------------------------------------------
    # Quy tắc kiểm tra tính hợp lệ & Tính toán giảm giá
    # -------------------------------------------------------------
    def is_valid_for_order(
        self,
        order_amount: Decimal | float | int,
        current_time: datetime | None = None,
    ) -> tuple[bool, str]:
        """Kiểm tra toàn diện xem voucher có đủ điều kiện áp dụng cho đơn hàng hay không."""
        now = current_time or datetime.now()
        amount = Decimal(str(order_amount))

        # 1. Kiểm tra trạng thái hoạt động
        if self.status != VoucherStatus.ACTIVE.value:
            return False, f"Voucher đang ở trạng thái '{self.status}', không thể sử dụng."

        # 2. Kiểm tra thời hạn: Chưa đến ngày bắt đầu
        if now < self.valid_from:
            return False, f"Voucher chưa có hiệu lực (bắt đầu từ {self.valid_from.strftime('%d/%m/%Y %H:%M')})."

        # 3. Kiểm tra thời hạn: Đã quá ngày kết thúc
        if now > self.valid_to:
            return False, f"Voucher đã hết hạn sử dụng từ ngày {self.valid_to.strftime('%d/%m/%Y %H:%M')}."

        # 4. Kiểm tra giới hạn lượt dùng
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False, "Voucher đã hết lượt sử dụng."

        # 5. Kiểm tra điều kiện giá trị đơn hàng tối thiểu
        if amount < self.min_order_amount:
            return (
                False,
                f"Đơn hàng trị giá {amount:,.0f}đ chưa đạt giá trị tối thiểu {self.min_order_amount:,.0f}đ để áp dụng voucher.",
            )

        return True, "Voucher hợp lệ."

    def calculate_discount(
        self,
        order_amount: Decimal | float | int,
        current_time: datetime | None = None,
    ) -> Decimal:
        """Quy tắc tính số tiền giảm giá dựa trên kiểu voucher:
        - FIXED_AMOUNT: Giảm trực tiếp discount_value (không vượt quá tổng tiền đơn).
        - PERCENTAGE: Giảm theo tỷ lệ % (order_amount * discount_value / 100),
          có chặn trần max_discount_amount nếu được cấu hình.
        """
        amount = Decimal(str(order_amount))
        is_valid, reason = self.is_valid_for_order(amount, current_time)
        if not is_valid:
            raise ValueError(f"Không thể áp dụng voucher: {reason}")

        if self.discount_type == DiscountType.FIXED_AMOUNT.value:
            discount = min(self.discount_value, amount)
        elif self.discount_type == DiscountType.PERCENTAGE.value:
            discount = (amount * self.discount_value) / Decimal("100.00")
            if self.max_discount_amount is not None:
                discount = min(discount, self.max_discount_amount)
            discount = min(discount, amount)
        else:
            raise ValueError(f"Kiểu giảm giá '{self.discount_type}' không được hỗ trợ.")

        # Làm tròn 2 chữ số thập phân
        return discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def apply(
        self,
        order_amount: Decimal | float | int,
        current_time: datetime | None = None,
    ) -> Decimal:
        """Áp dụng voucher cho đơn hàng:
        - Tính số tiền giảm giá.
        - Tăng số lượt đã sử dụng used_count lên 1.
        - Tự động chuyển trạng thái DEPLETED nếu chạm giới hạn lượt dùng.
        """
        discount = self.calculate_discount(order_amount, current_time)
        self.used_count += 1

        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            self.status = VoucherStatus.DEPLETED.value

        return discount
