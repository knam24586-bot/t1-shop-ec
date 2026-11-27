"""Bộ kiểm thử cho Payment Fail, Callback lặp (Idempotent), Hủy đơn và Giải phóng hàng đúng một lần.
Tiêu chí chấp nhận:
1. Payment callback xử lý idempotent:
   - Callback SUCCESS lặp lại: Trả về is_idempotent=True, giữ nguyên trạng thái CONFIRMED/SUCCESS, không tạo giao dịch/đơn trùng.
   - Callback FAILED lặp lại: Trả về is_idempotent=True, giữ nguyên FAILED, không hoàn tồn kho lần 2.
   - Callback FAILED gửi muộn sau khi giao dịch đã SUCCESS: Không hạ cấp giao dịch, không giải phóng hàng sai.
2. Thất bại / hết hạn giải phóng hàng đúng một lần:
   - Khi thanh toán online thất bại (mã phản hồi khác '00') hoặc hết hạn (expired/timeout),
     đơn hàng chuyển sang CANCELLED và giải phóng tồn kho cho các biến thể và sản phẩm.
   - Bảo đảm hoàn tồn đúng 1 lần: Gọi lặp lại không cộng dồn tồn kho.
3. Hủy đơn tuân thủ State Machine:
   - Cho phép hủy ở PENDING hoặc CONFIRMED.
   - Chặn hủy đơn đã giao (DELIVERED) hoặc đang giao (SHIPPED) -> 400 Bad Request.
   - Chặn hủy đơn đã hủy (CANCELLED) -> 400 Bad Request.
   - Lưu lý do hủy và lịch sử chuyển trạng thái (OrderStatusHistory).
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.core.deps import get_current_user
from app.db.session import Base, get_db

# Import toàn bộ model để cấu hình mapper hoàn chỉnh tránh lỗi liên kết
from app.models.category import Category
from app.models.product import Product
from app.models.variant import ProductVariant
from app.models.user import User
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.order import Order, OrderStatus, VALID_STATUS_TRANSITIONS
from app.models.order_item import OrderItem
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.payment_log import PaymentWebhookLog
from app.models.order_cancellation import OrderCancellation
from app.models.order_status_history import OrderStatusHistory
from app.models.voucher import Voucher  # noqa: F401
from app.models.wishlist import Wishlist  # noqa: F401
from app.models.store import Store  # noqa: F401
from app.models.store_order import StoreOrder  # noqa: F401
from app.models.admin_audit_log import AdminOrderAuditLog  # noqa: F401
from app.models.admin_voucher_log import AdminVoucherLog  # noqa: F401

from app.crud.payment_lifecycle import (
    cancel_order_with_state_machine_guard,
    get_order_state_transitions,
    handle_expired_payment_and_release_stock,
    handle_payment_callback_lifecycle,
    release_order_inventory_exactly_once,
)
from app.routers.payment_lifecycle import router as payment_lifecycle_router
from app.services.payment_gateway import (
    build_vnpay_signature,
    build_momo_signature,
)


class BasePaymentLifecycleTestCase(unittest.TestCase):
    """Lớp nền cung cấp Database SQLite in-memory và dữ liệu mẫu độc lập cho từng bài test."""

    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        # 1. Tạo 2 User: Customer A (Faker) và Customer B (Oner)
        self.user_a = User(
            full_name="Faker Lee",
            email="faker@t1.gg",
            password_hash="pw_faker",
            role="CUSTOMER",
            status="Active",
        )
        self.user_b = User(
            full_name="Oner Mun",
            email="oner@t1.gg",
            password_hash="pw_oner",
            role="CUSTOMER",
            status="Active",
        )
        self.db.add_all([self.user_a, self.user_b])
        self.db.flush()

        # 2. Tạo Category & Product
        self.category = Category(name="Áo Đấu T1", slug="ao-dau-t1", status="Active")
        self.db.add(self.category)
        self.db.flush()

        # Sản phẩm: ban đầu có 50 cái trong kho
        self.product = Product(
            category_id=self.category.id,
            name="Áo Đấu T1 CKTG 2026",
            slug="ao-dau-t1-cktg-2026",
            price=Decimal("1000000.00"),
            stock=50,
            status="Published",
        )
        self.db.add(self.product)
        self.db.flush()

        # Biến thể M: ban đầu có 20 cái trong kho
        self.variant_m = ProductVariant(
            product_id=self.product.id,
            sku="T1-2026-RED-M",
            color="Red",
            size="M",
            stock=20,
        )
        # Biến thể L: ban đầu có 15 cái trong kho
        self.variant_l = ProductVariant(
            product_id=self.product.id,
            sku="T1-2026-RED-L",
            color="Red",
            size="L",
            stock=15,
        )
        self.db.add_all([self.variant_m, self.variant_l])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def create_sample_order(
        self,
        customer_id: int,
        order_status: str = OrderStatus.PENDING.value,
        variant_m_qty: int = 2,
        variant_l_qty: int = 1,
    ) -> tuple[Order, Payment]:
        """Tạo đơn hàng mẫu kèm các OrderItem và Payment PENDING tương ứng."""
        # Trừ tồn kho tương ứng khi đơn hàng được tạo
        self.variant_m.stock -= variant_m_qty
        self.variant_l.stock -= variant_l_qty
        self.product.stock -= (variant_m_qty + variant_l_qty)

        total = (Decimal("1000000.00") * variant_m_qty) + (Decimal("1000000.00") * variant_l_qty)
        order = Order(
            order_code=Order.generate_order_code("VNPAY"),
            customer_id=customer_id,
            shipping_address="T1 Basecamp, Seoul",
            total_price=total,
            status=order_status,
        )
        self.db.add(order)
        self.db.flush()

        item1 = OrderItem(
            order_id=order.id,
            variant_id=self.variant_m.id,
            product_id=self.product.id,
            unit_price=Decimal("1000000.00"),
            quantity=variant_m_qty,
            line_total=Decimal("1000000.00") * variant_m_qty,
        )
        item2 = OrderItem(
            order_id=order.id,
            variant_id=self.variant_l.id,
            product_id=self.product.id,
            unit_price=Decimal("1000000.00"),
            quantity=variant_l_qty,
            line_total=Decimal("1000000.00") * variant_l_qty,
        )
        self.db.add_all([item1, item2])
        self.db.flush()

        tx_ref = Payment.generate_transaction_ref(PaymentMethod.VNPAY, order.id, 1)
        payment = Payment(
            order_id=order.id,
            method=PaymentMethod.VNPAY.value,
            amount=total,
            status=PaymentStatus.PENDING.value,
            attempt_number=1,
            transaction_reference=tx_ref,
        )
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(payment)
        return order, payment


class TestPaymentCallbackIdempotency(BasePaymentLifecycleTestCase):
    """Kiểm thử Tiêu chí: Payment callback xử lý Idempotent (chống trùng lặp an toàn)."""

    def test_callback_success_idempotent_processing(self):
        """Callback thành công lặp lại nhiều lần: Trả về is_idempotent=True, không tạo đơn/giao dịch trùng."""
        order, payment = self.create_sample_order(self.user_a.id)
        tx_ref = payment.transaction_reference

        vnp_params = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "00",
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        valid_hash = build_vnpay_signature(vnp_params)

        # Lần 1: Nhận callback SUCCESS lần đầu
        res1 = handle_payment_callback_lifecycle(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="00",
            secure_hash=valid_hash,
            extra_params=vnp_params,
        )
        self.assertTrue(res1.success)
        self.assertFalse(res1.is_idempotent)
        self.assertEqual(res1.payment_status, PaymentStatus.SUCCESS.value)
        self.assertEqual(res1.order_status, OrderStatus.CONFIRMED.value)

        # Lần 2: Nhận lại chính xác callback SUCCESS đó (duplicate webhook)
        res2 = handle_payment_callback_lifecycle(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="00",
            secure_hash=valid_hash,
            extra_params=vnp_params,
        )
        self.assertTrue(res2.success)
        self.assertTrue(res2.is_idempotent)
        self.assertEqual(res2.payment_status, PaymentStatus.SUCCESS.value)
        self.assertEqual(res2.order_status, OrderStatus.CONFIRMED.value)

        # Lần 3: Thử lại lần nữa
        res3 = handle_payment_callback_lifecycle(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="00",
            secure_hash=valid_hash,
            extra_params=vnp_params,
        )
        self.assertTrue(res3.is_idempotent)

        # Kiểm tra DB chỉ có đúng 1 Payment và 1 Order, không bị sinh duplicate
        all_payments = self.db.scalars(select(Payment).where(Payment.order_id == order.id)).all()
        self.assertEqual(len(all_payments), 1)

    def test_callback_failure_idempotent_no_duplicate_stock_release(self):
        """Callback thất bại lặp lại: Xử lý idempotent, KHÔNG hoàn tồn kho lần 2."""
        order, payment = self.create_sample_order(self.user_a.id, variant_m_qty=2, variant_l_qty=1)
        # Tồn kho hiện tại: M = 20 - 2 = 18; L = 15 - 1 = 14; Prod = 50 - 3 = 47
        self.assertEqual(self.variant_m.stock, 18)
        self.assertEqual(self.variant_l.stock, 14)
        self.assertEqual(self.product.stock, 47)

        tx_ref = payment.transaction_reference
        vnp_params = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "24",  # Người dùng hủy giao dịch
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        valid_hash = build_vnpay_signature(vnp_params)

        # Lần 1: Nhận callback thất bại -> Chuyển FAILED, Order CANCELLED, hoàn tồn kho lần 1
        res1 = handle_payment_callback_lifecycle(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="24",
            secure_hash=valid_hash,
            extra_params=vnp_params,
        )
        self.assertFalse(res1.success)
        self.assertFalse(res1.is_idempotent)
        self.assertTrue(res1.inventory_released)
        self.assertEqual(res1.restocked_items_count, 3)

        # Tồn kho sau lần hoàn 1: M = 20, L = 15, Prod = 50
        self.db.refresh(self.variant_m)
        self.db.refresh(self.variant_l)
        self.db.refresh(self.product)
        self.assertEqual(self.variant_m.stock, 20)
        self.assertEqual(self.variant_l.stock, 15)
        self.assertEqual(self.product.stock, 50)

        # Lần 2: Nhận lại callback thất bại lặp (duplicate callback)
        res2 = handle_payment_callback_lifecycle(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="24",
            secure_hash=valid_hash,
            extra_params=vnp_params,
        )
        self.assertFalse(res2.success)
        self.assertTrue(res2.is_idempotent)
        self.assertFalse(res2.inventory_released)  # Không hoàn tồn thêm lần nào nữa!
        self.assertEqual(res2.restocked_items_count, 0)

        # Tồn kho sau lần 2 vẫn là 20, 15, 50 (TUYỆT ĐỐI KHÔNG BỊ CỘNG DỒN THÀNH 22, 16, 53)
        self.db.refresh(self.variant_m)
        self.db.refresh(self.variant_l)
        self.db.refresh(self.product)
        self.assertEqual(self.variant_m.stock, 20)
        self.assertEqual(self.variant_l.stock, 15)
        self.assertEqual(self.product.stock, 50)

    def test_late_failed_callback_cannot_override_success_payment(self):
        """Callback thất bại gửi muộn sau khi giao dịch đã SUCCESS: Không hạ cấp giao dịch, không hoàn tồn sai."""
        order, payment = self.create_sample_order(self.user_a.id, variant_m_qty=2, variant_l_qty=1)
        tx_ref = payment.transaction_reference

        # Callback 1 SUCCESS
        vnp_params_ok = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "00",
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        hash_ok = build_vnpay_signature(vnp_params_ok)
        handle_payment_callback_lifecycle(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="00",
            secure_hash=hash_ok,
            extra_params=vnp_params_ok,
        )

        stock_m_before = self.variant_m.stock  # 18
        stock_l_before = self.variant_l.stock  # 14

        # Callback 2 muộn gửi thất bại (code="99")
        vnp_params_fail = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "99",
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        hash_fail = build_vnpay_signature(vnp_params_fail)
        res_late = handle_payment_callback_lifecycle(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="99",
            secure_hash=hash_fail,
            extra_params=vnp_params_fail,
        )

        # Hệ thống bảo vệ Idempotent, giữ nguyên SUCCESS
        self.assertTrue(res_late.success)
        self.assertTrue(res_late.is_idempotent)
        self.assertEqual(res_late.payment_status, PaymentStatus.SUCCESS.value)
        self.assertEqual(res_late.order_status, OrderStatus.CONFIRMED.value)
        self.assertFalse(res_late.inventory_released)

        # Tồn kho không bị hoàn sai
        self.db.refresh(self.variant_m)
        self.db.refresh(self.variant_l)
        self.assertEqual(self.variant_m.stock, stock_m_before)
        self.assertEqual(self.variant_l.stock, stock_l_before)


class TestPaymentFailureAndStockRelease(BasePaymentLifecycleTestCase):
    """Kiểm thử Tiêu chí: Payment thất bại giải phóng hàng đúng một lần."""

    def test_payment_failure_releases_stock_and_records_history(self):
        """Thanh toán thất bại chuyển đơn PENDING -> CANCELLED, hoàn tồn và lưu OrderStatusHistory."""
        order, payment = self.create_sample_order(self.user_a.id, variant_m_qty=3, variant_l_qty=2)
        tx_ref = payment.transaction_reference

        vnp_params = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "51",  # Tài khoản không đủ số dư
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        valid_hash = build_vnpay_signature(vnp_params)

        res = handle_payment_callback_lifecycle(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="51",
            secure_hash=valid_hash,
            extra_params=vnp_params,
        )

        self.assertFalse(res.success)
        self.assertEqual(res.order_status, OrderStatus.CANCELLED.value)
        self.assertEqual(res.payment_status, PaymentStatus.FAILED.value)
        self.assertTrue(res.inventory_released)
        self.assertEqual(res.restocked_items_count, 5)

        # Kiểm tra tồn kho được hoàn trả chính xác
        self.db.refresh(self.variant_m)
        self.db.refresh(self.variant_l)
        self.db.refresh(self.product)
        self.assertEqual(self.variant_m.stock, 20)
        self.assertEqual(self.variant_l.stock, 15)
        self.assertEqual(self.product.stock, 50)

        # Kiểm tra bản ghi OrderCancellation
        cancellation = self.db.scalar(select(OrderCancellation).where(OrderCancellation.order_id == order.id))
        self.assertIsNotNone(cancellation)
        self.assertTrue(cancellation.inventory_restocked)
        self.assertEqual(cancellation.cancelled_by, "GATEWAY")

        # Kiểm tra bản ghi OrderStatusHistory
        history = self.db.scalar(
            select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id)
        )
        self.assertIsNotNone(history)
        self.assertEqual(history.previous_status, "PENDING")
        self.assertEqual(history.new_status, "CANCELLED")
        self.assertEqual(history.changed_by_role, "GATEWAY")

    def test_payment_failure_invalid_signature_does_not_release_stock(self):
        """Callback chữ ký không hợp lệ bị từ chối 400, tuyệt đối KHÔNG giải phóng hàng."""
        order, payment = self.create_sample_order(self.user_a.id, variant_m_qty=2, variant_l_qty=1)
        tx_ref = payment.transaction_reference

        init_m_stock = self.variant_m.stock
        init_l_stock = self.variant_l.stock

        with self.assertRaises(HTTPException) as ctx:
            handle_payment_callback_lifecycle(
                db=self.db,
                transaction_reference=tx_ref,
                method="VNPAY",
                response_code="51",
                secure_hash="TAMPERED_FAKE_HASH_0000000",
                extra_params={"vnp_TxnRef": tx_ref},
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Chữ ký không hợp lệ", ctx.exception.detail)

        # Tồn kho và trạng thái đơn hàng giữ nguyên vẹn
        self.db.refresh(self.variant_m)
        self.db.refresh(self.variant_l)
        self.db.refresh(order)
        self.assertEqual(self.variant_m.stock, init_m_stock)
        self.assertEqual(self.variant_l.stock, init_l_stock)
        self.assertEqual(order.status, OrderStatus.PENDING.value)


class TestPaymentExpirationAndStockRelease(BasePaymentLifecycleTestCase):
    """Kiểm thử Tiêu chí: Hết hạn thanh toán (Expired / Timeout) giải phóng hàng đúng một lần."""

    def test_expire_payment_releases_stock_and_transitions_order(self):
        """Xử lý hết hạn đơn PENDING: Order chuyển CANCELLED, giải phóng tồn kho đúng 1 lần."""
        order, payment = self.create_sample_order(self.user_a.id, variant_m_qty=4, variant_l_qty=2)
        # Kho trước khi hết hạn: M = 16, L = 13, Prod = 44
        self.assertEqual(self.variant_m.stock, 16)
        self.assertEqual(self.variant_l.stock, 13)
        self.assertEqual(self.product.stock, 44)

        res = handle_expired_payment_and_release_stock(
            db=self.db,
            transaction_reference=payment.transaction_reference,
            reason="Quá hạn thanh toán 15 phút",
        )

        self.assertEqual(res.order_status, OrderStatus.CANCELLED.value)
        self.assertFalse(res.is_idempotent)
        self.assertTrue(res.inventory_released)
        self.assertEqual(res.restocked_items_count, 6)

        # Tồn kho được hoàn đầy đủ: M = 20, L = 15, Prod = 50
        self.db.refresh(self.variant_m)
        self.db.refresh(self.variant_l)
        self.db.refresh(self.product)
        self.assertEqual(self.variant_m.stock, 20)
        self.assertEqual(self.variant_l.stock, 15)
        self.assertEqual(self.product.stock, 50)

    def test_duplicate_expire_payment_is_idempotent(self):
        """Yêu cầu hết hạn lặp lại (retry/duplicate): Xử lý idempotent, KHÔNG hoàn tồn kho lần 2."""
        order, payment = self.create_sample_order(self.user_a.id, variant_m_qty=2, variant_l_qty=1)

        # Hết hạn lần 1
        res1 = handle_expired_payment_and_release_stock(
            db=self.db,
            order_code=order.order_code,
        )
        self.assertTrue(res1.inventory_released)
        self.assertFalse(res1.is_idempotent)

        # Hết hạn lần 2 (lặp lại)
        res2 = handle_expired_payment_and_release_stock(
            db=self.db,
            order_code=order.order_code,
        )
        self.assertFalse(res2.inventory_released)
        self.assertTrue(res2.is_idempotent)
        self.assertEqual(res2.restocked_items_count, 0)

        # Tồn kho không bị cộng dư
        self.db.refresh(self.variant_m)
        self.db.refresh(self.variant_l)
        self.db.refresh(self.product)
        self.assertEqual(self.variant_m.stock, 20)
        self.assertEqual(self.variant_l.stock, 15)
        self.assertEqual(self.product.stock, 50)

    def test_cannot_expire_delivered_or_paid_order(self):
        """Không thể xử lý hết hạn cho đơn hàng đã giao (DELIVERED) hoặc đã thanh toán thành công."""
        # Đơn DELIVERED
        order_delivered, _ = self.create_sample_order(self.user_a.id, order_status=OrderStatus.DELIVERED.value)
        with self.assertRaises(HTTPException) as ctx1:
            handle_expired_payment_and_release_stock(db=self.db, order_code=order_delivered.order_code)
        self.assertEqual(ctx1.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("DELIVERED", ctx1.exception.detail)

        # Đơn có Payment SUCCESS
        order_paid, payment_paid = self.create_sample_order(self.user_a.id, order_status=OrderStatus.CONFIRMED.value)
        payment_paid.status = PaymentStatus.SUCCESS.value
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx2:
            handle_expired_payment_and_release_stock(db=self.db, order_code=order_paid.order_code)
        self.assertEqual(ctx2.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("đã thành công", ctx2.exception.detail)


class TestOrderCancellationStateMachine(BasePaymentLifecycleTestCase):
    """Kiểm thử Tiêu chí: Hủy đơn tuân thủ State Machine và giải phóng hàng đúng một lần."""

    def test_cancel_pending_order_allowed_by_state_machine(self):
        """Hủy đơn từ PENDING: Tuân thủ State Machine, giải phóng hàng và lưu OrderCancellation."""
        order, _ = self.create_sample_order(self.user_a.id, order_status=OrderStatus.PENDING.value, variant_m_qty=2)

        res = cancel_order_with_state_machine_guard(
            db=self.db,
            order_code=order.order_code,
            reason="Khách hàng đổi ý muốn đổi size",
            user_id=self.user_a.id,
            cancelled_by="CUSTOMER",
        )

        self.assertEqual(res.previous_status, OrderStatus.PENDING.value)
        self.assertEqual(res.current_status, OrderStatus.CANCELLED.value)
        self.assertTrue(res.inventory_released)

        # Kiểm tra tồn kho được giải phóng
        self.db.refresh(self.variant_m)
        self.assertEqual(self.variant_m.stock, 20)

    def test_cancel_confirmed_order_allowed_by_state_machine(self):
        """Hủy đơn từ CONFIRMED: Tuân thủ State Machine, giải phóng hàng."""
        order, _ = self.create_sample_order(self.user_a.id, order_status=OrderStatus.CONFIRMED.value, variant_l_qty=3)

        res = cancel_order_with_state_machine_guard(
            db=self.db,
            order_code=order.order_code,
            reason="Khách hủy trước khi chuẩn bị hàng",
            user_id=self.user_a.id,
            cancelled_by="CUSTOMER",
        )
        self.assertEqual(res.previous_status, OrderStatus.CONFIRMED.value)
        self.assertEqual(res.current_status, OrderStatus.CANCELLED.value)
        self.assertTrue(res.inventory_released)

        self.db.refresh(self.variant_l)
        self.assertEqual(self.variant_l.stock, 15)

    def test_cancel_delivered_order_strictly_rejected(self):
        """Chặn tuyệt đối việc hủy đơn đã giao (DELIVERED) -> 400 Bad Request."""
        order, _ = self.create_sample_order(self.user_a.id, order_status=OrderStatus.DELIVERED.value)

        with self.assertRaises(HTTPException) as ctx:
            cancel_order_with_state_machine_guard(
                db=self.db,
                order_code=order.order_code,
                reason="Muốn hủy đơn đã nhận",
                user_id=self.user_a.id,
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("DELIVERED", ctx.exception.detail)
        self.assertIn("không được phép hủy trái quy tắc", ctx.exception.detail)

    def test_cancel_shipped_order_strictly_rejected(self):
        """Chặn việc hủy đơn đang giao hàng (SHIPPED) -> 400 Bad Request."""
        order, _ = self.create_sample_order(self.user_a.id, order_status=OrderStatus.SHIPPED.value)

        with self.assertRaises(HTTPException) as ctx:
            cancel_order_with_state_machine_guard(
                db=self.db,
                order_code=order.order_code,
                reason="Hủy khi đang giao",
                user_id=self.user_a.id,
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("SHIPPED", ctx.exception.detail)

    def test_cancel_already_cancelled_order_rejected_no_duplicate_restock(self):
        """Chặn việc hủy lại đơn đã hủy (CANCELLED) -> 400 Bad Request, tồn kho không bị hoàn 2 lần."""
        order, _ = self.create_sample_order(self.user_a.id, order_status=OrderStatus.PENDING.value, variant_m_qty=2)

        # Hủy lần 1 thành công
        cancel_order_with_state_machine_guard(
            db=self.db,
            order_code=order.order_code,
            reason="Hủy lần 1 hợp lệ",
            user_id=self.user_a.id,
        )
        self.db.refresh(self.variant_m)
        self.assertEqual(self.variant_m.stock, 20)

        # Cố tình gọi hủy lần 2
        with self.assertRaises(HTTPException) as ctx:
            cancel_order_with_state_machine_guard(
                db=self.db,
                order_code=order.order_code,
                reason="Cố hủy lần 2",
                user_id=self.user_a.id,
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Không thể hủy lại", ctx.exception.detail)

        # Tồn kho không bị cộng thêm
        self.db.refresh(self.variant_m)
        self.assertEqual(self.variant_m.stock, 20)

    def test_cancel_order_requires_valid_reason(self):
        """Hủy đơn bắt buộc phải có lý do tối thiểu 3 ký tự."""
        order, _ = self.create_sample_order(self.user_a.id)

        with self.assertRaises(HTTPException) as ctx_empty:
            cancel_order_with_state_machine_guard(
                db=self.db,
                order_code=order.order_code,
                reason="",
                user_id=self.user_a.id,
            )
        self.assertEqual(ctx_empty.exception.status_code, status.HTTP_400_BAD_REQUEST)

        with self.assertRaises(HTTPException) as ctx_short:
            cancel_order_with_state_machine_guard(
                db=self.db,
                order_code=order.order_code,
                reason="ko",
                user_id=self.user_a.id,
            )
        self.assertEqual(ctx_short.exception.status_code, status.HTTP_400_BAD_REQUEST)

    def test_state_machine_transitions_query(self):
        """Kiểm tra API truy vấn các bước chuyển tiếp hợp lệ theo State Machine."""
        order_pending, _ = self.create_sample_order(self.user_a.id, order_status=OrderStatus.PENDING.value)
        resp = get_order_state_transitions(db=self.db, order_code=order_pending.order_code)
        self.assertEqual(resp.current_status, "PENDING")
        self.assertFalse(resp.is_terminal)
        self.assertIn("CONFIRMED", resp.allowed_next_statuses)
        self.assertIn("CANCELLED", resp.allowed_next_statuses)

        order_delivered, _ = self.create_sample_order(self.user_a.id, order_status=OrderStatus.DELIVERED.value)
        resp_del = get_order_state_transitions(db=self.db, order_code=order_delivered.order_code)
        self.assertEqual(resp_del.current_status, "DELIVERED")
        self.assertTrue(resp_del.is_terminal)
        self.assertEqual(len(resp_del.allowed_next_statuses), 0)


class TestPaymentLifecycleFastAPIEndpoints(BasePaymentLifecycleTestCase):
    """Kiểm thử End-to-End các API endpoint của Payment Lifecycle qua FastAPI TestClient."""

    def setUp(self):
        super().setUp()
        self.app = FastAPI()
        self.app.include_router(payment_lifecycle_router)

        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_user] = lambda: self.user_a
        self.client = TestClient(self.app)

    def test_api_callback_with_release_success_and_idempotent(self):
        """API Callback: Thanh toán thành công (200), nhận lại lặp lại (200 Idempotent)."""
        order, payment = self.create_sample_order(self.user_a.id)
        tx_ref = payment.transaction_reference

        vnp_params = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "00",
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        valid_hash = build_vnpay_signature(vnp_params)

        # Lần 1
        res1 = self.client.post(
            "/payments/callback-with-release",
            json={
                "transaction_reference": tx_ref,
                "method": "VNPAY",
                "response_code": "00",
                "secure_hash": valid_hash,
                "extra_params": vnp_params,
            },
        )
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertTrue(data1["success"])
        self.assertFalse(data1["is_idempotent"])

        # Lần 2 (trùng)
        res2 = self.client.post(
            "/payments/callback-with-release",
            json={
                "transaction_reference": tx_ref,
                "method": "VNPAY",
                "response_code": "00",
                "secure_hash": valid_hash,
                "extra_params": vnp_params,
            },
        )
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(data2["success"])
        self.assertTrue(data2["is_idempotent"])

    def test_api_callback_failure_releases_inventory(self):
        """API Callback: Thất bại giải phóng hàng đúng 1 lần."""
        order, payment = self.create_sample_order(self.user_a.id, variant_m_qty=2)
        tx_ref = payment.transaction_reference

        vnp_params = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "24",
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        valid_hash = build_vnpay_signature(vnp_params)

        res = self.client.post(
            "/payments/callback-with-release",
            json={
                "transaction_reference": tx_ref,
                "method": "VNPAY",
                "response_code": "24",
                "secure_hash": valid_hash,
                "extra_params": vnp_params,
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["success"])
        self.assertTrue(data["inventory_released"])
        self.assertEqual(data["order_status"], "CANCELLED")

    def test_api_expire_payment_and_idempotent(self):
        """API Expire Payment: Hết hạn giải phóng tồn kho (200), retry là idempotent (200)."""
        order, payment = self.create_sample_order(self.user_a.id)

        # Lần 1
        res1 = self.client.post(
            "/payments/expire",
            json={"order_code": order.order_code, "reason": "Hết hạn thanh toán"},
        )
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertTrue(data1["inventory_released"])
        self.assertFalse(data1["is_idempotent"])

        # Lần 2 (retry)
        res2 = self.client.post(
            "/payments/expire",
            json={"order_code": order.order_code},
        )
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertFalse(data2["inventory_released"])
        self.assertTrue(data2["is_idempotent"])

    def test_api_cancel_order_state_machine_guard(self):
        """API Cancel Order: Hợp lệ (200) và chặn DELIVERED (400)."""
        # Đơn PENDING -> 200 OK
        order_pending, _ = self.create_sample_order(self.user_a.id)
        res_ok = self.client.post(
            "/payments/cancel-order",
            json={"order_code": order_pending.order_code, "reason": "Không muốn mua nữa"},
        )
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.json()["current_status"], "CANCELLED")

        # Đơn DELIVERED -> 400 Bad Request
        order_delivered, _ = self.create_sample_order(self.user_a.id, order_status=OrderStatus.DELIVERED.value)
        res_fail = self.client.post(
            "/payments/cancel-order",
            json={"order_code": order_delivered.order_code, "reason": "Hủy đơn đã nhận"},
        )
        self.assertEqual(res_fail.status_code, 400)
        self.assertIn("không được phép hủy trái quy tắc", res_fail.json()["detail"])

    def test_api_state_transitions(self):
        """API State Transitions: Trả về danh sách chuyển đổi hợp lệ."""
        order, _ = self.create_sample_order(self.user_a.id)
        res = self.client.get(f"/payments/state-transitions/{order.order_code}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["current_status"], "PENDING")
        self.assertIn("CONFIRMED", data["allowed_next_statuses"])


if __name__ == "__main__":
    unittest.main()
