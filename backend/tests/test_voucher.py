"""Bộ kiểm thử cho SQLAlchemy Model Voucher và quy tắc giảm giá.
Kiểm tra tất cả các tiêu chí chấp nhận:
1. Voucher có code duy nhất (uk_vouchers_code), tự động chuẩn hóa uppercase.
2. Kiểm tra thời hạn hiệu lực (chưa bắt đầu, đang hiệu lực, đã hết hạn).
3. Kiểu và giá trị giảm: PERCENTAGE (có max_discount_amount) và FIXED_AMOUNT (không vượt quá tổng tiền đơn).
4. Điều kiện áp dụng: Giá trị đơn tối thiểu (min_order_amount) và giới hạn lượt dùng (usage_limit).
5. Quản lý trạng thái: ACTIVE, INACTIVE, DEPLETED.
6. Kiểm tra các giá trị hợp lệ (validations: code rỗng, discount_value > 100%, số tiền âm...).
"""
import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from app.db.session import Base
from app.models.category import Category  # noqa: F401
from app.models.product import Product  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.variant import ProductVariant  # noqa: F401
from app.models.order import Order  # noqa: F401
from app.models.order_item import OrderItem  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.voucher import Voucher, DiscountType, VoucherStatus


class TestVoucherModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        self.now = datetime(2026, 11, 14, 12, 0, 0)
        self.valid_from = self.now - timedelta(days=2)
        self.valid_to = self.now + timedelta(days=10)

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # -------------------------------------------------------------
    # 1. TIÊU CHÍ: Code duy nhất & Chuẩn hóa
    # -------------------------------------------------------------
    def test_voucher_code_unique_constraint(self):
        """Mã voucher phải là duy nhất trên toàn hệ thống."""
        v1 = Voucher(
            code="T1WIN",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("10.00"),
            valid_from=self.valid_from,
            valid_to=self.valid_to,
        )
        self.session.add(v1)
        self.session.commit()

        # Thử tạo voucher thứ 2 có cùng mã code -> Phải văng IntegrityError
        v2 = Voucher(
            code="t1win",  # Sẽ được chuẩn hóa thành T1WIN
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("50000.00"),
            valid_from=self.valid_from,
            valid_to=self.valid_to,
        )
        self.session.add(v2)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    def test_voucher_code_normalization_and_non_empty(self):
        """Code tự động strip khoảng trắng và viết hoa."""
        v = Voucher(
            code="  faker2026  ",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("20000.00"),
            valid_from=self.valid_from,
            valid_to=self.valid_to,
        )
        self.assertEqual(v.code, "FAKER2026")

        # Code rỗng văng lỗi
        with self.assertRaises(ValueError):
            Voucher(
                code="   ",
                discount_type=DiscountType.FIXED_AMOUNT.value,
                discount_value=Decimal("20000.00"),
                valid_from=self.valid_from,
                valid_to=self.valid_to,
            )

    # -------------------------------------------------------------
    # 2. TIÊU CHÍ: Thời hạn (valid_from, valid_to)
    # -------------------------------------------------------------
    def test_voucher_validity_time_range(self):
        """Kiểm tra thời hạn voucher: Chưa tới ngày, trong thời hạn, và đã hết hạn."""
        voucher = Voucher(
            code="FLASH_SALE",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("15.00"),
            valid_from=datetime(2026, 11, 10, 0, 0, 0),
            valid_to=datetime(2026, 11, 20, 23, 59, 59),
        )
        self.session.add(voucher)
        self.session.commit()

        # 1. Thời điểm trước khi bắt đầu (9/11/2026) -> Chưa có hiệu lực
        time_before = datetime(2026, 11, 9, 10, 0, 0)
        is_valid, reason = voucher.is_valid_for_order(500000, current_time=time_before)
        self.assertFalse(is_valid)
        self.assertIn("chưa có hiệu lực", reason)
        with self.assertRaises(ValueError):
            voucher.calculate_discount(500000, current_time=time_before)

        # 2. Thời điểm trong thời hạn (15/11/2026) -> Hợp lệ
        time_active = datetime(2026, 11, 15, 12, 0, 0)
        is_valid, _ = voucher.is_valid_for_order(500000, current_time=time_active)
        self.assertTrue(is_valid)
        discount = voucher.calculate_discount(500000, current_time=time_active)
        self.assertEqual(discount, Decimal("75000.00"))  # 15% của 500,000

        # 3. Thời điểm sau khi kết thúc (25/11/2026) -> Hết hạn
        time_after = datetime(2026, 11, 25, 10, 0, 0)
        is_valid, reason = voucher.is_valid_for_order(500000, current_time=time_after)
        self.assertFalse(is_valid)
        self.assertIn("hết hạn sử dụng", reason)

    # -------------------------------------------------------------
    # 3. TIÊU CHÍ: Kiểu và giá trị giảm (PERCENTAGE vs FIXED_AMOUNT)
    # -------------------------------------------------------------
    def test_percentage_discount_with_max_cap(self):
        """Voucher phần trăm có mức giảm tối đa (Cap)."""
        voucher = Voucher(
            code="SALE20",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("20.00"),          # Giảm 20%
            max_discount_amount=Decimal("150000.00"),  # Tối đa 150.000đ
            valid_from=self.valid_from,
            valid_to=self.valid_to,
        )

        # Đơn 500.000đ -> 20% = 100.000đ (< 150.000đ) -> Giảm 100.000đ
        d1 = voucher.calculate_discount(Decimal("500000.00"), current_time=self.now)
        self.assertEqual(d1, Decimal("100000.00"))

        # Đơn 1.000.000đ -> 20% = 200.000đ (> 150.000đ) -> Giảm trần 150.000đ
        d2 = voucher.calculate_discount(Decimal("1000000.00"), current_time=self.now)
        self.assertEqual(d2, Decimal("150000.00"))

    def test_fixed_amount_discount_capped_by_order_amount(self):
        """Voucher số tiền cố định không được vượt quá tổng tiền đơn hàng."""
        voucher = Voucher(
            code="GIAM100K",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("100000.00"),
            valid_from=self.valid_from,
            valid_to=self.valid_to,
        )

        # Đơn 300.000đ -> Giảm đủ 100.000đ
        d1 = voucher.calculate_discount(Decimal("300000.00"), current_time=self.now)
        self.assertEqual(d1, Decimal("100000.00"))

        # Đơn 60.000đ -> Chỉ giảm tối đa 60.000đ (không làm âm đơn hàng)
        d2 = voucher.calculate_discount(Decimal("60000.00"), current_time=self.now)
        self.assertEqual(d2, Decimal("60000.00"))

    # -------------------------------------------------------------
    # 4. TIÊU CHÍ: Điều kiện áp dụng (min_order_amount, usage_limit)
    # -------------------------------------------------------------
    def test_min_order_amount_condition(self):
        """Đơn hàng phải đạt giá trị tối thiểu mới được áp dụng voucher."""
        voucher = Voucher(
            code="MIN500K",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("50000.00"),
            min_order_amount=Decimal("500000.00"),
            valid_from=self.valid_from,
            valid_to=self.valid_to,
        )

        # Đơn 400.000đ (< 500.000đ) -> Bị từ chối
        is_valid, reason = voucher.is_valid_for_order(Decimal("400000.00"), current_time=self.now)
        self.assertFalse(is_valid)
        self.assertIn("chưa đạt giá trị tối thiểu", reason)
        with self.assertRaises(ValueError):
            voucher.calculate_discount(Decimal("400000.00"), current_time=self.now)

        # Đơn 500.000đ (bằng mức tối thiểu) -> Hợp lệ
        is_valid, _ = voucher.is_valid_for_order(Decimal("500000.00"), current_time=self.now)
        self.assertTrue(is_valid)
        self.assertEqual(voucher.calculate_discount(Decimal("500000.00"), current_time=self.now), Decimal("50000.00"))

    def test_usage_limit_and_depletion(self):
        """Kiểm soát lượt sử dụng: Khi dùng hết lượt, voucher tự chuyển sang DEPLETED."""
        voucher = Voucher(
            code="LIMITED2",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("20000.00"),
            usage_limit=2,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
        )
        self.session.add(voucher)
        self.session.commit()

        # Lần dùng 1: Thành công, used_count = 1
        d1 = voucher.apply(Decimal("100000.00"), current_time=self.now)
        self.assertEqual(d1, Decimal("20000.00"))
        self.assertEqual(voucher.used_count, 1)
        self.assertEqual(voucher.status, VoucherStatus.ACTIVE.value)

        # Lần dùng 2: Thành công, chạm ngưỡng limit = 2 -> status đổi sang DEPLETED
        d2 = voucher.apply(Decimal("100000.00"), current_time=self.now)
        self.assertEqual(d2, Decimal("20000.00"))
        self.assertEqual(voucher.used_count, 2)
        self.assertEqual(voucher.status, VoucherStatus.DEPLETED.value)

        # Lần dùng 3: Bị chặn vì đã hết lượt dùng
        is_valid, reason = voucher.is_valid_for_order(Decimal("100000.00"), current_time=self.now)
        self.assertFalse(is_valid)
        with self.assertRaises(ValueError):
            voucher.apply(Decimal("100000.00"), current_time=self.now)

    # -------------------------------------------------------------
    # 5. TIÊU CHÍ: Trạng thái voucher (Status)
    # -------------------------------------------------------------
    def test_inactive_voucher_cannot_be_used(self):
        """Voucher INACTIVE bị chặn sử dụng."""
        voucher = Voucher(
            code="PAUSED",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("10.00"),
            status=VoucherStatus.INACTIVE.value,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
        )
        is_valid, reason = voucher.is_valid_for_order(200000, current_time=self.now)
        self.assertFalse(is_valid)
        self.assertIn("INACTIVE", reason)

    # -------------------------------------------------------------
    # 6. TIÊU CHÍ: Kiểm tra giá trị hợp lệ (Model Validations)
    # -------------------------------------------------------------
    def test_validations_discount_value(self):
        """Kiểm tra validation giá trị giảm: > 0 và phần trăm <= 100%."""
        # Giá trị giảm <= 0 văng lỗi
        with self.assertRaises(ValueError):
            Voucher(
                code="ZERO",
                discount_type=DiscountType.PERCENTAGE.value,
                discount_value=Decimal("0.00"),
                valid_from=self.valid_from,
                valid_to=self.valid_to,
            )

        # Giảm phần trăm > 100% văng lỗi
        with self.assertRaises(ValueError):
            Voucher(
                code="OVER100",
                discount_type=DiscountType.PERCENTAGE.value,
                discount_value=Decimal("150.00"),
                valid_from=self.valid_from,
                valid_to=self.valid_to,
            )

    def test_validations_negative_amounts_and_limits(self):
        """Kiểm tra số tiền tối thiểu và giới hạn không hợp lệ."""
        # min_order_amount âm
        with self.assertRaises(ValueError):
            Voucher(
                code="NEG_MIN",
                discount_type=DiscountType.FIXED_AMOUNT.value,
                discount_value=Decimal("10000.00"),
                min_order_amount=Decimal("-1000.00"),
                valid_from=self.valid_from,
                valid_to=self.valid_to,
            )

        # usage_limit < 1
        with self.assertRaises(ValueError):
            Voucher(
                code="ZERO_LIMIT",
                discount_type=DiscountType.FIXED_AMOUNT.value,
                discount_value=Decimal("10000.00"),
                usage_limit=0,
                valid_from=self.valid_from,
                valid_to=self.valid_to,
            )


if __name__ == "__main__":
    unittest.main()

