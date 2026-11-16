"""Bộ kiểm thử cho SQLAlchemy Model Payment và trạng thái giao dịch.
Kiểm tra tất cả các tiêu chí chấp nhận:
1. Payment lưu đầy đủ: order, method, amount, status, transaction_reference, timestamps.
2. Hỗ trợ nhiều lần thử thanh toán (multiple payment attempts) cho cùng 1 đơn hàng.
3. Quản lý trạng thái giao dịch: PENDING, SUCCESS, FAILED, CANCELLED, REFUNDED.
4. Ràng buộc mã tham chiếu giao dịch duy nhất (transaction_reference unique).
5. Ràng buộc amount > 0 và attempt_number >= 1 (ở cả Python validation và DB CheckConstraint).
6. Cascade delete khi xoá đơn hàng.
"""
import unittest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from app.db.session import Base
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.variant import ProductVariant  # noqa: F401
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem  # noqa: F401
from app.models.payment import Payment, PaymentStatus, PaymentMethod


class TestPaymentModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        # Sử dụng SQLite in-memory để kiểm thử độc lập
        self.engine = create_engine("sqlite:///:memory:", echo=False)

        # Bật foreign keys cho SQLite để kiểm tra ON DELETE CASCADE ở tầng Database
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        # Dữ liệu nền tảng: User và Order
        self.user = User(
            full_name="Keria",
            email="keria@t1.gg",
            password_hash="hashed_keria_pw",
            role="CUSTOMER",
            status="Active",
        )
        self.session.add(self.user)
        self.session.flush()

        self.order = Order(
            order_code=Order.generate_order_code(),
            customer_id=self.user.id,
            shipping_address="Hà Nội, Việt Nam",
            total_price=Decimal("1200000.00"),
            status=OrderStatus.PENDING.value,
        )
        self.session.add(self.order)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # -------------------------------------------------------------
    # 1. TIÊU CHÍ: Lưu đầy đủ order, method, amount, status, transaction_reference
    # -------------------------------------------------------------
    def test_payment_fields_and_relationships(self):
        """Payment phải lưu: order, method, amount, status, transaction_reference và timestamps."""
        txn_ref = Payment.generate_transaction_ref(PaymentMethod.VNPAY, self.order.id, 1)

        payment = Payment(
            order_id=self.order.id,
            method=PaymentMethod.VNPAY.value,
            amount=self.order.total_price,
            status=PaymentStatus.PENDING.value,
            transaction_reference=txn_ref,
            attempt_number=1,
        )
        self.session.add(payment)
        self.session.commit()

        # Kiểm tra truy vấn lại
        saved = self.session.scalar(select(Payment).where(Payment.id == payment.id))
        self.assertIsNotNone(saved)
        self.assertEqual(saved.order_id, self.order.id)
        self.assertEqual(saved.method, "VNPAY")
        self.assertEqual(saved.amount, Decimal("1200000.00"))
        self.assertEqual(saved.status, PaymentStatus.PENDING.value)
        self.assertEqual(saved.transaction_reference, txn_ref)
        self.assertEqual(saved.attempt_number, 1)
        self.assertIsNotNone(saved.created_at)
        self.assertIsNotNone(saved.updated_at)
        self.assertEqual(saved.order.order_code, self.order.order_code)

    # -------------------------------------------------------------
    # 2. TIÊU CHÍ: Hỗ trợ nhiều lần thử theo thiết kế (Multi-Attempt)
    # -------------------------------------------------------------
    def test_payment_supports_multiple_attempts_for_single_order(self):
        """Thiết kế hỗ trợ nhiều lần thử: Khách thử VNPAY thất bại -> Thử lại bằng MOMO thành công."""
        # Lần thử 1 (Attempt 1): Chọn VNPAY nhưng giao dịch bị lỗi/hết tiền
        ref_attempt_1 = Payment.generate_transaction_ref(PaymentMethod.VNPAY, self.order.id, 1)
        payment_1 = Payment(
            order_id=self.order.id,
            method=PaymentMethod.VNPAY.value,
            amount=self.order.total_price,
            attempt_number=1,
            transaction_reference=ref_attempt_1,
        )
        self.session.add(payment_1)
        self.session.commit()

        # Giả lập cổng thanh toán trả về thất bại
        payment_1.mark_as_failed(reason="Thẻ không đủ số dư")
        self.session.commit()

        self.assertEqual(payment_1.status, PaymentStatus.FAILED.value)
        self.assertTrue(payment_1.can_retry())

        # Lần thử 2 (Attempt 2): Khách thử lại với ví MoMo
        payment_2 = payment_1.create_retry_attempt(new_method=PaymentMethod.MOMO)
        self.assertEqual(payment_2.attempt_number, 2)
        self.assertEqual(payment_2.method, "MOMO")
        self.assertEqual(payment_2.status, PaymentStatus.PENDING.value)
        self.session.add(payment_2)
        self.session.commit()

        # Lần thử 2 thành công
        ref_attempt_2 = Payment.generate_transaction_ref(PaymentMethod.MOMO, self.order.id, 2)
        payment_2.mark_as_success(transaction_reference=ref_attempt_2)
        self.session.commit()

        # Kiểm tra lịch sử giao dịch: Cùng 1 đơn hàng có đủ 2 lần thử
        all_attempts = self.session.scalars(
            select(Payment)
            .where(Payment.order_id == self.order.id)
            .order_by(Payment.attempt_number)
        ).all()

        self.assertEqual(len(all_attempts), 2)
        self.assertEqual(all_attempts[0].attempt_number, 1)
        self.assertEqual(all_attempts[0].method, "VNPAY")
        self.assertEqual(all_attempts[0].status, PaymentStatus.FAILED.value)

        self.assertEqual(all_attempts[1].attempt_number, 2)
        self.assertEqual(all_attempts[1].method, "MOMO")
        self.assertEqual(all_attempts[1].status, PaymentStatus.SUCCESS.value)

    def test_payment_attempt_duplicate_prevented(self):
        """Không cho phép 2 lần thử trùng số thứ tự (attempt_number) trên cùng 1 đơn hàng."""
        p1 = Payment(
            order_id=self.order.id,
            method="COD",
            amount=Decimal("500000.00"),
            attempt_number=1,
        )
        self.session.add(p1)
        self.session.commit()

        # Cố ý tạo thêm attempt_number = 1 cho cùng đơn hàng
        p2 = Payment(
            order_id=self.order.id,
            method="VNPAY",
            amount=Decimal("500000.00"),
            attempt_number=1,
        )
        self.session.add(p2)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    # -------------------------------------------------------------
    # 3. TIÊU CHÍ: Quản lý trạng thái giao dịch & Transaction Reference duy nhất
    # -------------------------------------------------------------
    def test_payment_status_lifecycle_and_cancellation(self):
        """Kiểm tra huỷ giao dịch và chuyển trạng thái."""
        payment = Payment(
            order_id=self.order.id,
            method=PaymentMethod.VNPAY.value,
            amount=self.order.total_price,
            attempt_number=1,
        )
        self.session.add(payment)
        self.session.commit()

        # Người dùng huỷ thanh toán
        payment.mark_as_cancelled()
        self.session.commit()
        self.assertEqual(payment.status, PaymentStatus.CANCELLED.value)
        self.assertTrue(payment.can_retry())

        # Giao dịch đã thành công thì không thể thử lại
        payment.status = PaymentStatus.SUCCESS.value
        self.assertFalse(payment.can_retry())
        with self.assertRaises(ValueError):
            payment.create_retry_attempt()

    def test_transaction_reference_unique_constraint(self):
        """Mã tham chiếu giao dịch từ cổng thanh toán phải là duy nhất trên toàn hệ thống."""
        duplicate_ref = "TXN-REF-SHARED-123456"

        p1 = Payment(
            order_id=self.order.id,
            method="VNPAY",
            amount=Decimal("300000.00"),
            attempt_number=1,
            transaction_reference=duplicate_ref,
        )
        self.session.add(p1)
        self.session.commit()

        # Giao dịch khác dùng trùng mã tham chiếu -> Lỗi IntegrityError
        p2 = Payment(
            order_id=self.order.id,
            method="VNPAY",
            amount=Decimal("300000.00"),
            attempt_number=2,
            transaction_reference=duplicate_ref,
        )
        self.session.add(p2)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    # -------------------------------------------------------------
    # 4. TIÊU CHÍ: Ràng buộc số tiền amount > 0 và attempt >= 1
    # -------------------------------------------------------------
    def test_payment_amount_must_be_positive(self):
        """Số tiền thanh toán phải > 0."""
        # Amount = 0
        with self.assertRaises(ValueError):
            Payment(order_id=self.order.id, method="COD", amount=Decimal("0.00"), attempt_number=1)

        # Amount < 0
        with self.assertRaises(ValueError):
            Payment(order_id=self.order.id, method="COD", amount=Decimal("-10000.00"), attempt_number=1)

    def test_payment_attempt_number_must_be_at_least_one(self):
        """Số thứ tự lần thử phải >= 1."""
        with self.assertRaises(ValueError):
            Payment(order_id=self.order.id, method="COD", amount=Decimal("100000.00"), attempt_number=0)

    # -------------------------------------------------------------
    # 5. TIÊU CHÍ: Cascade Delete khi xoá đơn hàng
    # -------------------------------------------------------------
    def test_order_deletion_cascades_payments(self):
        """Khi đơn hàng Order bị xoá, các bản ghi Payment liên quan phải tự động bị dọn sạch."""
        p1 = Payment(order_id=self.order.id, method="VNPAY", amount=Decimal("500000.00"), attempt_number=1)
        p2 = Payment(order_id=self.order.id, method="MOMO", amount=Decimal("500000.00"), attempt_number=2)
        self.session.add_all([p1, p2])
        self.session.commit()

        self.assertEqual(len(self.session.scalars(select(Payment).where(Payment.order_id == self.order.id)).all()), 2)

        # Xoá đơn hàng
        self.session.delete(self.order)
        self.session.commit()

        # Kiểm tra toàn bộ payments của đơn hàng đã bị xoá
        remaining = self.session.scalars(select(Payment).where(Payment.order_id == self.order.id)).all()
        self.assertEqual(len(remaining), 0)


if __name__ == "__main__":
    unittest.main()
