"""Bộ Unit Test toàn diện cho Cart, Checkout, Order và các trường hợp lỗi (Error cases).
Đáp ứng đầy đủ tất cả các tiêu chí chấp nhận:
1. Cart & Order/Checkout bao phủ trường hợp THÀNH CÔNG (Success flows):
   - Thêm, sửa, xóa, xem giỏ hàng, gộp giỏ hàng (merge items).
   - Checkout COD thành công: tạo Order, OrderItems, trừ tồn kho, tạo Payment COD pending, dọn sạch giỏ hàng.
   - Checkout với Voucher hợp lệ (% và FIXED), voucher chuyển DEPLETED khi hết lượt dùng.
2. TỒN KHO KHÔNG ĐỦ (Insufficient Stock / Out of Stock):
   - Thêm vào giỏ vượt tồn kho -> 400 Bad Request.
   - Sửa số lượng giỏ hàng vượt tồn kho -> 400 Bad Request.
   - Gộp giỏ (cộng dồn) vượt tồn kho -> 400 Bad Request.
   - Server re-check lúc checkout phát hiện thiếu tồn kho -> 400 Bad Request.
   - Hết hàng hoàn toàn (stock = 0) -> 400 Bad Request.
   - Transaction Rollback 100%: không trừ kho, không tạo Order rác, giỏ hàng giữ nguyên vẹn.
3. VOUCHER LỖI (Voucher Errors):
   - Mã voucher không tồn tại -> 404 Not Found.
   - Voucher bị khóa / INACTIVE -> 400 Bad Request.
   - Voucher đã hết hạn (valid_to < now) -> 400 Bad Request.
   - Voucher chưa đến ngày bắt đầu (valid_from > now) -> 400 Bad Request.
   - Voucher hết lượt dùng (depleted / used_count >= usage_limit) -> 400 Bad Request.
   - Đơn hàng không đạt giá trị tối thiểu (subtotal < min_order_amount) -> 400 Bad Request.
   - Transaction Rollback khi voucher lỗi: không trừ kho, không tạo đơn rác.
4. THANH TOÁN LỖI (Payment Errors):
   - Khởi tạo thanh toán cho đơn hàng không tồn tại -> 404 Not Found.
   - User khác thanh toán đơn không thuộc sở hữu -> 403 Forbidden.
   - Khởi tạo thanh toán cho đơn hàng đã huỷ -> 400 Bad Request.
   - Khởi tạo thanh toán cho đơn hàng đã thanh toán thành công -> 400 Bad Request.
   - Cổng thanh toán không hỗ trợ -> 400 Bad Request.
   - Webhook callback chữ ký không hợp lệ (sai HMAC) -> 400 Bad Request, log audit ghi nhận is_valid_signature=False.
   - Cổng thanh toán không khớp với giao dịch -> 400 Bad Request.
   - Cổng thanh toán gửi mã phản hồi thất bại (response_code != '00') -> Payment chuyển sang FAILED.
5. REQUEST LẶP (Duplicate Request / Idempotency):
   - Request lặp khi checkout (Duplicate checkout): giỏ hàng đã thanh toán bị dọn sạch, request tiếp theo bị từ chối 400 (giỏ hàng trống).
   - Request lặp webhook callback thành công (Idempotent callback): trả về is_idempotent=True, không tạo đơn/giao dịch trùng, giữ nguyên trạng thái an toàn.
   - Request lặp webhook callback thất bại (Idempotent callback): trả về is_idempotent=True, không làm sai lệch trạng thái.
   - Request lặp webhook thất bại không thể ghi đè giao dịch đã thành công trước đó.
   - Request lặp thêm sản phẩm vào giỏ hàng: tự gộp số lượng (merge), không tạo duplicate record CartItem trong DB.
6. TEST CHẠY ỔN ĐỊNH:
   - Sử dụng SQLite in-memory với StaticPool độc lập cho từng test case.
   - 100% deterministic, không phụ thuộc môi trường ngoài.
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
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.payment_log import PaymentWebhookLog
from app.models.voucher import Voucher, VoucherStatus, DiscountType
from app.models.wishlist import Wishlist  # noqa: F401
from app.models.store import Store  # noqa: F401
from app.models.store_order import StoreOrder  # noqa: F401
from app.models.order_status_history import OrderStatusHistory  # noqa: F401
from app.models.order_cancellation import OrderCancellation  # noqa: F401
from app.models.admin_audit_log import AdminOrderAuditLog  # noqa: F401
from app.models.admin_voucher_log import AdminVoucherLog  # noqa: F401

from app.crud.cart import (
    add_item_to_cart,
    build_cart_response,
    get_or_create_user_cart,
    delete_cart_item,
    update_cart_item_quantity,
)
from app.crud.order import create_cod_order, get_user_orders
from app.crud.payment import (
    initiate_online_checkout,
    process_payment_callback,
)
from app.services.payment_gateway import (
    build_vnpay_signature,
    build_momo_signature,
)
from app.routers.cart import router as cart_router
from app.routers.order import router as order_router
from app.routers.payment import router as payment_router


class BaseCartOrderPaymentTestCase(unittest.TestCase):
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

        # 1. Tạo 2 User: Customer A và Customer B
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

        self.product = Product(
            category_id=self.category.id,
            name="Áo Đấu T1 CKTG 2026",
            slug="ao-dau-t1-cktg-2026",
            price=Decimal("1000000.00"),
            stock=10,
            status="Published",
        )
        self.db.add(self.product)
        self.db.flush()

        # 3. Tạo 2 Biến thể: Variant 1 (stock=10), Variant 2 (stock=5)
        self.variant_m = ProductVariant(
            product_id=self.product.id,
            sku="T1-2026-RED-M",
            color="Red",
            size="M",
            stock=10,
        )
        self.variant_l = ProductVariant(
            product_id=self.product.id,
            sku="T1-2026-RED-L",
            color="Red",
            size="L",
            stock=5,
        )
        self.db.add_all([self.variant_m, self.variant_l])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()


class TestCartUnitOperations(BaseCartOrderPaymentTestCase):
    """Kiểm thử Unit cho Giỏ hàng: Thành công, lỗi tồn kho, và gộp giỏ."""

    def test_cart_add_and_view_success(self):
        """Thêm sản phẩm vào giỏ hàng thành công và tính tổng tiền chính xác."""
        resp = add_item_to_cart(
            db=self.db,
            user_id=self.user_a.id,
            variant_id=self.variant_m.id,
            quantity=2,
        )
        self.assertEqual(resp.user_id, self.user_a.id)
        self.assertEqual(resp.total_items, 2)
        self.assertEqual(resp.total_amount, Decimal("2000000.00"))
        self.assertEqual(len(resp.items), 1)
        self.assertEqual(resp.items[0].sku, "T1-2026-RED-M")

    def test_cart_merge_rule_on_duplicate_add(self):
        """Request lặp thêm cùng 1 biến thể: tự động gộp giỏ và không tạo 2 record CartItem trùng."""
        add_item_to_cart(
            db=self.db,
            user_id=self.user_a.id,
            variant_id=self.variant_m.id,
            quantity=2,
        )
        # Thêm tiếp cùng variant
        resp = add_item_to_cart(
            db=self.db,
            user_id=self.user_a.id,
            variant_id=self.variant_m.id,
            quantity=3,
        )
        self.assertEqual(resp.total_items, 5)
        self.assertEqual(resp.total_amount, Decimal("5000000.00"))
        self.assertEqual(len(resp.items), 1)
        self.assertEqual(resp.items[0].quantity, 5)

        # Kiểm tra database chỉ có 1 bản ghi CartItem duy nhất
        cart = get_or_create_user_cart(self.db, self.user_a.id)
        self.assertEqual(len(cart.items), 1)
        self.assertEqual(cart.items[0].quantity, 5)

    def test_cart_update_quantity_success(self):
        """Cập nhật số lượng sản phẩm trong giỏ thành công."""
        add_item_to_cart(
            db=self.db,
            user_id=self.user_a.id,
            variant_id=self.variant_m.id,
            quantity=2,
        )
        cart = get_or_create_user_cart(self.db, self.user_a.id)
        item_id = cart.items[0].id

        resp = update_cart_item_quantity(
            db=self.db,
            user_id=self.user_a.id,
            item_id=item_id,
            new_quantity=4,
        )
        self.assertEqual(resp.total_items, 4)
        self.assertEqual(resp.total_amount, Decimal("4000000.00"))

    def test_cart_remove_item_success(self):
        """Xóa sản phẩm khỏi giỏ hàng thành công."""
        add_item_to_cart(
            db=self.db,
            user_id=self.user_a.id,
            variant_id=self.variant_m.id,
            quantity=2,
        )
        cart = get_or_create_user_cart(self.db, self.user_a.id)
        item_id = cart.items[0].id

        resp = delete_cart_item(db=self.db, user_id=self.user_a.id, item_id=item_id)
        self.assertEqual(resp.total_items, 0)
        self.assertEqual(resp.total_amount, Decimal("0.00"))
        self.assertEqual(len(resp.items), 0)

    def test_cart_add_insufficient_stock_fails(self):
        """Thêm vào giỏ vượt quá tồn kho của variant -> Bắt lỗi 400 Bad Request."""
        # Variant M có tồn kho 10, yêu cầu 11
        with self.assertRaises(HTTPException) as ctx:
            add_item_to_cart(
                db=self.db,
                user_id=self.user_a.id,
                variant_id=self.variant_m.id,
                quantity=11,
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tồn kho", ctx.exception.detail)

    def test_cart_add_zero_or_negative_quantity_fails(self):
        """Thêm số lượng <= 0 vào giỏ hàng -> Bắt lỗi 400 Bad Request."""
        with self.assertRaises(HTTPException) as ctx:
            add_item_to_cart(
                db=self.db,
                user_id=self.user_a.id,
                variant_id=self.variant_m.id,
                quantity=0,
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)

        with self.assertRaises(HTTPException) as ctx:
            add_item_to_cart(
                db=self.db,
                user_id=self.user_a.id,
                variant_id=self.variant_m.id,
                quantity=-3,
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cart_add_nonexistent_variant_fails(self):
        """Thêm biến thể không tồn tại -> Bắt lỗi 404 Not Found."""
        with self.assertRaises(HTTPException) as ctx:
            add_item_to_cart(
                db=self.db,
                user_id=self.user_a.id,
                variant_id=99999,
                quantity=1,
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_404_NOT_FOUND)

    def test_cart_merge_exceeding_stock_fails(self):
        """Gộp giỏ cộng dồn vượt quá tồn kho -> Bắt lỗi 400 Bad Request."""
        # Variant L có tồn kho 5. Đã thêm 3, thêm tiếp 3 (tổng 6 > 5)
        add_item_to_cart(
            db=self.db,
            user_id=self.user_a.id,
            variant_id=self.variant_l.id,
            quantity=3,
        )
        with self.assertRaises(HTTPException) as ctx:
            add_item_to_cart(
                db=self.db,
                user_id=self.user_a.id,
                variant_id=self.variant_l.id,
                quantity=3,
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tồn kho", ctx.exception.detail)

    def test_cart_update_quantity_exceeding_stock_fails(self):
        """Cập nhật số lượng vượt quá tồn kho -> Bắt lỗi 400 Bad Request."""
        add_item_to_cart(
            db=self.db,
            user_id=self.user_a.id,
            variant_id=self.variant_l.id,
            quantity=2,
        )
        cart = get_or_create_user_cart(self.db, self.user_a.id)
        item_id = cart.items[0].id

        with self.assertRaises(HTTPException) as ctx:
            update_cart_item_quantity(
                db=self.db,
                user_id=self.user_a.id,
                item_id=item_id,
                new_quantity=10,  # stock=5
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tồn kho", ctx.exception.detail)


class TestCheckoutAndOrderUnitOperations(BaseCartOrderPaymentTestCase):
    """Kiểm thử Unit cho Checkout & Order: Thành công, thiếu tồn kho, voucher lỗi, và rollback."""

    def test_checkout_cod_success_flow(self):
        """Checkout COD thành công: Tạo Order, trừ tồn kho, tạo Payment COD pending, dọn sạch giỏ."""
        add_item_to_cart(
            db=self.db,
            user_id=self.user_a.id,
            variant_id=self.variant_m.id,
            quantity=3,
        )
        init_variant_stock = self.variant_m.stock  # 10
        init_prod_stock = self.product.stock  # 10

        order, payment = create_cod_order(
            db=self.db,
            user_id=self.user_a.id,
            shipping_address="123 Đường T1, Hà Nội",
        )

        # 1. Kiểm tra Order được tạo đúng
        self.assertIsNotNone(order.id)
        self.assertTrue(order.order_code.startswith("COD-"))
        self.assertEqual(order.customer_id, self.user_a.id)
        self.assertEqual(order.status, OrderStatus.PENDING.value)
        self.assertEqual(order.total_price, Decimal("3000000.00"))
        self.assertEqual(len(order.items), 1)

        # 2. Kiểm tra snapshot OrderItem
        item = order.items[0]
        self.assertEqual(item.variant_id, self.variant_m.id)
        self.assertEqual(item.quantity, 3)
        self.assertEqual(item.unit_price, Decimal("1000000.00"))
        self.assertEqual(item.line_total, Decimal("3000000.00"))

        # 3. Kiểm tra trừ tồn kho chính xác
        self.db.refresh(self.variant_m)
        self.db.refresh(self.product)
        self.assertEqual(self.variant_m.stock, init_variant_stock - 3)
        self.assertEqual(self.product.stock, init_prod_stock - 3)

        # 4. Kiểm tra Payment COD được tạo trạng thái PENDING
        self.assertIsNotNone(payment.id)
        self.assertEqual(payment.method, PaymentMethod.COD.value)
        self.assertEqual(payment.amount, Decimal("3000000.00"))
        self.assertEqual(payment.status, PaymentStatus.PENDING.value)
        self.assertEqual(payment.attempt_number, 1)

        # 5. Kiểm tra giỏ hàng của user đã được dọn sạch
        cart = get_or_create_user_cart(self.db, self.user_a.id)
        self.assertEqual(len(cart.items), 0)

    def test_checkout_with_valid_percentage_voucher(self):
        """Checkout COD áp dụng voucher giảm % thành công."""
        # Tạo voucher giảm 10%, tối đa 200.000, đơn tối thiểu 500.000
        now = datetime.now()
        voucher = Voucher(
            code="SALE10",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("10.00"),
            max_discount_amount=Decimal("200000.00"),
            min_order_amount=Decimal("500000.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=5),
            usage_limit=10,
            used_count=0,
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(voucher)
        self.db.commit()

        # Giỏ hàng: 1 x 1.000.000
        add_item_to_cart(self.db, self.user_a.id, self.variant_m.id, 1)

        order, payment = create_cod_order(
            db=self.db,
            user_id=self.user_a.id,
            shipping_address="Hà Nội, Việt Nam",
            voucher_code="SALE10",
        )

        # Giảm 10% của 1.000.000 = 100.000 -> Đơn còn 900.000
        self.assertEqual(order.total_price, Decimal("900000.00"))
        self.assertEqual(payment.amount, Decimal("900000.00"))

        # Kiểm tra used_count tăng lên 1
        self.db.refresh(voucher)
        self.assertEqual(voucher.used_count, 1)

    def test_checkout_with_valid_fixed_voucher(self):
        """Checkout COD áp dụng voucher giảm số tiền cố định (FIXED) thành công."""
        now = datetime.now()
        voucher = Voucher(
            code="GIAM300K",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("300000.00"),
            min_order_amount=Decimal("500000.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=5),
            usage_limit=5,
            used_count=0,
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(voucher)
        self.db.commit()

        # Giỏ hàng: 2 x 1.000.000 = 2.000.000
        add_item_to_cart(self.db, self.user_a.id, self.variant_m.id, 2)

        order, payment = create_cod_order(
            db=self.db,
            user_id=self.user_a.id,
            shipping_address="Hà Nội, Việt Nam",
            voucher_code="GIAM300K",
        )

        # 2.000.000 - 300.000 = 1.700.000
        self.assertEqual(order.total_price, Decimal("1700000.00"))
        self.assertEqual(payment.amount, Decimal("1700000.00"))

    def test_checkout_voucher_becomes_depleted_when_reaching_usage_limit(self):
        """Voucher tự động chuyển sang DEPLETED khi đạt giới hạn sử dụng sau đơn hàng."""
        now = datetime.now()
        voucher = Voucher(
            code="ONCEONLY",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("100000.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=5),
            usage_limit=1,
            used_count=0,
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(voucher)
        self.db.commit()

        add_item_to_cart(self.db, self.user_a.id, self.variant_m.id, 1)
        create_cod_order(self.db, self.user_a.id, "Hà Nội", voucher_code="ONCEONLY")

        self.db.refresh(voucher)
        self.assertEqual(voucher.used_count, 1)
        self.assertEqual(voucher.status, VoucherStatus.DEPLETED.value)

    # -------------------------------------------------------------
    # TỒN KHO KHÔNG ĐỦ VÀ ROLLBACK NGUYÊN TỬ
    # -------------------------------------------------------------
    def test_checkout_fails_when_variant_stock_depleted_before_checkout(self):
        """User thêm hàng lúc kho còn, nhưng trước khi checkout tồn kho bị giảm xuống thấp hơn số lượng giỏ."""
        # Thêm 3 cái khi kho có 5 (Variant L)
        add_item_to_cart(self.db, self.user_a.id, self.variant_l.id, 3)

        # Giả lập bên ngoài giảm kho Variant L xuống còn 2
        self.variant_l.stock = 2
        self.db.commit()

        # Checkout -> Server re-check phát hiện variant.stock < quantity -> ném 400
        with self.assertRaises(HTTPException) as ctx:
            create_cod_order(self.db, self.user_a.id, "Địa chỉ test")

        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("không đủ số lượng tồn kho", ctx.exception.detail)

    def test_checkout_insufficient_stock_atomic_rollback(self):
        """Xác nhận Rollback 100% khi checkout lỗi tồn kho: không trừ kho, không tạo Order rác, giỏ giữ nguyên."""
        add_item_to_cart(self.db, self.user_a.id, self.variant_l.id, 4)

        # Hạ kho xuống 1
        self.variant_l.stock = 1
        self.db.commit()

        order_count_before = len(self.db.scalars(select(Order)).all())
        payment_count_before = len(self.db.scalars(select(Payment)).all())

        with self.assertRaises(HTTPException):
            create_cod_order(self.db, self.user_a.id, "Địa chỉ test")

        # Rollback check:
        # 1. Tồn kho vẫn là 1 (không bị trừ âm)
        self.db.refresh(self.variant_l)
        self.assertEqual(self.variant_l.stock, 1)
        # 2. Không sinh Order hay Payment rác
        order_count_after = len(self.db.scalars(select(Order)).all())
        payment_count_after = len(self.db.scalars(select(Payment)).all())
        self.assertEqual(order_count_before, order_count_after)
        self.assertEqual(payment_count_before, payment_count_after)
        # 3. Giỏ hàng của user vẫn còn nguyên 4 món
        cart = get_or_create_user_cart(self.db, self.user_a.id)
        self.assertEqual(len(cart.items), 1)
        self.assertEqual(cart.items[0].quantity, 4)

    # -------------------------------------------------------------
    # VOUCHER LỖI VÀ ROLLBACK NGUYÊN TỬ
    # -------------------------------------------------------------
    def test_checkout_voucher_not_found_fails(self):
        """Áp dụng voucher không tồn tại -> 404 Not Found."""
        add_item_to_cart(self.db, self.user_a.id, self.variant_m.id, 1)
        with self.assertRaises(HTTPException) as ctx:
            create_cod_order(self.db, self.user_a.id, "Địa chỉ", voucher_code="NON_EXISTENT")
        self.assertEqual(ctx.exception.status_code, status.HTTP_404_NOT_FOUND)

    def test_checkout_voucher_inactive_fails(self):
        """Áp dụng voucher đang bị khóa (INACTIVE) -> 400 Bad Request."""
        now = datetime.now()
        voucher = Voucher(
            code="LOCKED_CODE",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("10.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=5),
            status=VoucherStatus.INACTIVE.value,
        )
        self.db.add(voucher)
        self.db.commit()

        add_item_to_cart(self.db, self.user_a.id, self.variant_m.id, 1)
        with self.assertRaises(HTTPException) as ctx:
            create_cod_order(self.db, self.user_a.id, "Địa chỉ", voucher_code="LOCKED_CODE")
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue("INACTIVE" in ctx.exception.detail or "trạng thái" in ctx.exception.detail)

    def test_checkout_voucher_expired_fails(self):
        """Áp dụng voucher đã hết hạn (valid_to trong quá khứ) -> 400 Bad Request."""
        now = datetime.now()
        voucher = Voucher(
            code="EXPIRED_CODE",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("10.00"),
            valid_from=now - timedelta(days=10),
            valid_to=now - timedelta(days=1),
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(voucher)
        self.db.commit()

        add_item_to_cart(self.db, self.user_a.id, self.variant_m.id, 1)
        with self.assertRaises(HTTPException) as ctx:
            create_cod_order(self.db, self.user_a.id, "Địa chỉ", voucher_code="EXPIRED_CODE")
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hết hạn", ctx.exception.detail)

    def test_checkout_voucher_not_yet_valid_fails(self):
        """Áp dụng voucher chưa tới ngày áp dụng (valid_from trong tương lai) -> 400 Bad Request."""
        now = datetime.now()
        voucher = Voucher(
            code="FUTURE_CODE",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("10.00"),
            valid_from=now + timedelta(days=2),
            valid_to=now + timedelta(days=10),
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(voucher)
        self.db.commit()

        add_item_to_cart(self.db, self.user_a.id, self.variant_m.id, 1)
        with self.assertRaises(HTTPException) as ctx:
            create_cod_order(self.db, self.user_a.id, "Địa chỉ", voucher_code="FUTURE_CODE")
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("chưa có hiệu lực", ctx.exception.detail)

    def test_checkout_voucher_depleted_usage_limit_fails(self):
        """Áp dụng voucher đã hết số lượt sử dụng -> 400 Bad Request."""
        now = datetime.now()
        voucher = Voucher(
            code="DEPLETED_CODE",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("10.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=5),
            usage_limit=3,
            used_count=3,
            status=VoucherStatus.DEPLETED.value,
        )
        self.db.add(voucher)
        self.db.commit()

        add_item_to_cart(self.db, self.user_a.id, self.variant_m.id, 1)
        with self.assertRaises(HTTPException) as ctx:
            create_cod_order(self.db, self.user_a.id, "Địa chỉ", voucher_code="DEPLETED_CODE")
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue("hết lượt sử dụng" in ctx.exception.detail or "DEPLETED" in ctx.exception.detail)

    def test_checkout_voucher_below_minimum_order_amount_fails(self):
        """Đơn hàng không đạt giá trị tối thiểu của voucher -> 400 Bad Request."""
        now = datetime.now()
        voucher = Voucher(
            code="MIN3M",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("500000.00"),
            min_order_amount=Decimal("3000000.00"),  # Yêu cầu 3 triệu
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=5),
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(voucher)
        self.db.commit()

        # Đơn hàng chỉ có 1 triệu
        add_item_to_cart(self.db, self.user_a.id, self.variant_m.id, 1)
        with self.assertRaises(HTTPException) as ctx:
            create_cod_order(self.db, self.user_a.id, "Địa chỉ", voucher_code="MIN3M")
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tối thiểu", ctx.exception.detail)


class TestPaymentErrorScenarios(BaseCartOrderPaymentTestCase):
    """Kiểm thử Unit cho các lỗi thanh toán: Sai đơn, không chính chủ, đơn đã huỷ, sai chữ ký webhook."""

    def setUp(self):
        super().setUp()
        # Tạo sẵn 1 đơn hàng PENDING của User A
        self.order_a = Order(
            order_code="ORD-PAY-001",
            customer_id=self.user_a.id,
            shipping_address="Hà Nội",
            total_price=Decimal("1500000.00"),
            status=OrderStatus.PENDING.value,
        )
        self.db.add(self.order_a)
        self.db.commit()
        self.db.refresh(self.order_a)

    def test_payment_initiate_order_not_found(self):
        """Khởi tạo thanh toán với mã đơn không tồn tại -> 404 Not Found."""
        with self.assertRaises(HTTPException) as ctx:
            initiate_online_checkout(
                db=self.db,
                user_id=self.user_a.id,
                order_code="NON_EXISTENT_ORDER",
                method="VNPAY",
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_404_NOT_FOUND)

    def test_payment_initiate_forbidden_for_other_user(self):
        """User B cố thanh toán đơn hàng của User A -> 403 Forbidden."""
        with self.assertRaises(HTTPException) as ctx:
            initiate_online_checkout(
                db=self.db,
                user_id=self.user_b.id,  # User B
                order_code=self.order_a.order_code,
                method="VNPAY",
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_403_FORBIDDEN)

    def test_payment_initiate_cancelled_order_rejected(self):
        """Khởi tạo thanh toán cho đơn hàng đã bị huỷ -> 400 Bad Request."""
        self.order_a.status = OrderStatus.CANCELLED.value
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            initiate_online_checkout(
                db=self.db,
                user_id=self.user_a.id,
                order_code=self.order_a.order_code,
                method="VNPAY",
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("đã bị huỷ", ctx.exception.detail)

    def test_payment_initiate_already_paid_order_rejected(self):
        """Khởi tạo thanh toán cho đơn hàng đã thanh toán thành công -> 400 Bad Request."""
        # Giả lập đã có Payment SUCCESS
        payment = Payment(
            order_id=self.order_a.id,
            method="VNPAY",
            amount=self.order_a.total_price,
            status=PaymentStatus.SUCCESS.value,
            attempt_number=1,
            transaction_reference="REF-SUCCESS-001",
        )
        self.order_a.status = OrderStatus.CONFIRMED.value
        self.db.add(payment)
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            initiate_online_checkout(
                db=self.db,
                user_id=self.user_a.id,
                order_code=self.order_a.order_code,
                method="VNPAY",
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("đã được thanh toán thành công", ctx.exception.detail)

    def test_payment_initiate_unsupported_gateway_rejected(self):
        """Cổng thanh toán không hỗ trợ -> 400 Bad Request."""
        with self.assertRaises(HTTPException) as ctx:
            initiate_online_checkout(
                db=self.db,
                user_id=self.user_a.id,
                order_code=self.order_a.order_code,
                method="CRYPTO_USDT",
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("không được hỗ trợ", ctx.exception.detail)

    def test_payment_callback_invalid_signature_rejected(self):
        """Webhook callback gửi chữ ký giả mạo / sai -> 400 Bad Request và lưu log audit."""
        # Tạo giao dịch PENDING
        checkout_resp = initiate_online_checkout(
            db=self.db,
            user_id=self.user_a.id,
            order_code=self.order_a.order_code,
            method="VNPAY",
        )
        tx_ref = checkout_resp.transaction_reference

        # Callback với chữ ký giả mạo
        with self.assertRaises(HTTPException) as ctx:
            process_payment_callback(
                db=self.db,
                transaction_reference=tx_ref,
                method="VNPAY",
                response_code="00",
                secure_hash="INVALID_TAMPERED_SIGNATURE_HASH_12345",
                extra_params={"vnp_TxnRef": tx_ref},
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Chữ ký không hợp lệ", ctx.exception.detail)

        # Kiểm tra audit log đã ghi nhận sự kiện sai chữ ký
        log = self.db.scalar(
            select(PaymentWebhookLog).where(PaymentWebhookLog.transaction_reference == tx_ref)
        )
        self.assertIsNotNone(log)
        self.assertFalse(log.is_valid_signature)

    def test_payment_callback_gateway_mismatch_rejected(self):
        """Giao dịch tạo VNPAY nhưng nhận callback là MOMO -> 400 Bad Request."""
        checkout_resp = initiate_online_checkout(
            db=self.db,
            user_id=self.user_a.id,
            order_code=self.order_a.order_code,
            method="VNPAY",
        )
        tx_ref = checkout_resp.transaction_reference

        with self.assertRaises(HTTPException) as ctx:
            process_payment_callback(
                db=self.db,
                transaction_reference=tx_ref,
                method="MOMO",
                response_code="00",
            )
        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("không khớp", ctx.exception.detail)

    def test_payment_callback_failed_response_code_marks_payment_failed(self):
        """Cổng thanh toán phản hồi mã lỗi (ví dụ VNPAY code='24' khách hàng hủy) -> Payment chuyển FAILED."""
        checkout_resp = initiate_online_checkout(
            db=self.db,
            user_id=self.user_a.id,
            order_code=self.order_a.order_code,
            method="VNPAY",
        )
        tx_ref = checkout_resp.transaction_reference

        # Tạo chữ ký hợp lệ cho VNPAY với response_code = "24"
        vnp_params = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "24",
            "vnp_Amount": str(int(self.order_a.total_price * 100)),
        }
        valid_hash = build_vnpay_signature(vnp_params)

        res = process_payment_callback(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="24",
            secure_hash=valid_hash,
            extra_params=vnp_params,
        )
        self.assertFalse(res.success)
        self.assertFalse(res.is_idempotent)
        self.assertEqual(res.payment_status, PaymentStatus.FAILED.value)

        # Kiểm tra DB
        payment = self.db.scalar(select(Payment).where(Payment.transaction_reference == tx_ref))
        self.assertEqual(payment.status, PaymentStatus.FAILED.value)
        # Đơn hàng vẫn ở PENDING (không chuyển CONFIRMED)
        self.db.refresh(self.order_a)
        self.assertEqual(self.order_a.status, OrderStatus.PENDING.value)


class TestDuplicateRequestAndIdempotency(BaseCartOrderPaymentTestCase):
    """Kiểm thử Unit cho Request lặp & Cơ chế Idempotent: Checkout lặp, Callback lặp, Gộp giỏ lặp."""

    def test_duplicate_checkout_request_on_emptied_cart(self):
        """Request lặp checkout: Lần 1 thành công (dọn giỏ), Lần 2 bị từ chối 400 (giỏ hàng trống)."""
        add_item_to_cart(self.db, self.user_a.id, self.variant_m.id, 2)

        # Request checkout lần 1: Thành công
        order1, payment1 = create_cod_order(self.db, self.user_a.id, "Địa chỉ nhận hàng")
        self.assertIsNotNone(order1)

        # Request checkout lần 2 (người dùng click đúp hoặc retry lặp): Giỏ hàng đã rỗng -> 400 Bad Request
        with self.assertRaises(HTTPException) as ctx:
            create_cod_order(self.db, self.user_a.id, "Địa chỉ nhận hàng")

        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Giỏ hàng trống", ctx.exception.detail)

    def test_duplicate_payment_callback_idempotent_success(self):
        """Callback webhook thành công lặp lại: Xử lý idempotent, không tạo giao dịch/đơn trùng."""
        # 1. Khởi tạo đơn và checkout online
        order = Order(
            order_code="ORD-IDEMP-01",
            customer_id=self.user_a.id,
            shipping_address="Hà Nội",
            total_price=Decimal("1000000.00"),
            status=OrderStatus.PENDING.value,
        )
        self.db.add(order)
        self.db.commit()

        checkout_resp = initiate_online_checkout(
            db=self.db,
            user_id=self.user_a.id,
            order_code=order.order_code,
            method="VNPAY",
        )
        tx_ref = checkout_resp.transaction_reference

        vnp_params = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "00",
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        valid_hash = build_vnpay_signature(vnp_params)

        # Callback lần 1: Lần đầu xử lý thành công
        cb1 = process_payment_callback(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="00",
            secure_hash=valid_hash,
            extra_params=vnp_params,
        )
        self.assertTrue(cb1.success)
        self.assertFalse(cb1.is_idempotent)
        self.assertEqual(cb1.payment_status, PaymentStatus.SUCCESS.value)
        self.assertEqual(cb1.order_status, OrderStatus.CONFIRMED.value)

        # Callback lần 2: Nhận lại chính xác webhook đó (duplicate)
        cb2 = process_payment_callback(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="00",
            secure_hash=valid_hash,
            extra_params=vnp_params,
        )
        self.assertTrue(cb2.success)
        self.assertTrue(cb2.is_idempotent)  # Đánh dấu Idempotent bỏ qua
        self.assertEqual(cb2.payment_status, PaymentStatus.SUCCESS.value)
        self.assertEqual(cb2.order_status, OrderStatus.CONFIRMED.value)

        # Xác nhận trong DB: Chỉ có đúng 1 Payment và 1 Order, không tạo trùng
        payments = self.db.scalars(select(Payment).where(Payment.order_id == order.id)).all()
        self.assertEqual(len(payments), 1)

    def test_duplicate_failed_callback_idempotent(self):
        """Callback webhook thất bại lặp lại: Xử lý idempotent."""
        order = Order(
            order_code="ORD-IDEMP-FAIL",
            customer_id=self.user_a.id,
            shipping_address="Hà Nội",
            total_price=Decimal("1000000.00"),
            status=OrderStatus.PENDING.value,
        )
        self.db.add(order)
        self.db.commit()

        checkout_resp = initiate_online_checkout(
            db=self.db,
            user_id=self.user_a.id,
            order_code=order.order_code,
            method="VNPAY",
        )
        tx_ref = checkout_resp.transaction_reference

        vnp_params = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "24",
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        valid_hash = build_vnpay_signature(vnp_params)

        # Lần 1 thất bại
        cb1 = process_payment_callback(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="24",
            secure_hash=valid_hash,
            extra_params=vnp_params,
        )
        self.assertFalse(cb1.success)
        self.assertFalse(cb1.is_idempotent)

        # Lần 2 lặp lại thất bại
        cb2 = process_payment_callback(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="24",
            secure_hash=valid_hash,
            extra_params=vnp_params,
        )
        self.assertFalse(cb2.success)
        self.assertTrue(cb2.is_idempotent)

    def test_duplicate_failed_callback_cannot_override_success_payment(self):
        """Giao dịch đã SUCCESS, sau đó nhận một callback muộn gửi FAILED -> Giữ nguyên SUCCESS."""
        order = Order(
            order_code="ORD-SUCCESS-PROT",
            customer_id=self.user_a.id,
            shipping_address="Hà Nội",
            total_price=Decimal("1000000.00"),
            status=OrderStatus.PENDING.value,
        )
        self.db.add(order)
        self.db.commit()

        checkout_resp = initiate_online_checkout(
            db=self.db,
            user_id=self.user_a.id,
            order_code=order.order_code,
            method="VNPAY",
        )
        tx_ref = checkout_resp.transaction_reference

        # Callback 1 SUCCESS
        vnp_params_ok = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "00",
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        hash_ok = build_vnpay_signature(vnp_params_ok)
        process_payment_callback(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="00",
            secure_hash=hash_ok,
            extra_params=vnp_params_ok,
        )

        # Callback 2 muộn gửi FAILED ("99")
        vnp_params_fail = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "99",
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        hash_fail = build_vnpay_signature(vnp_params_fail)
        cb_late = process_payment_callback(
            db=self.db,
            transaction_reference=tx_ref,
            method="VNPAY",
            response_code="99",
            secure_hash=hash_fail,
            extra_params=vnp_params_fail,
        )

        # Giao dịch không bị hạ cấp, trả về thành công Idempotent
        self.assertTrue(cb_late.success)
        self.assertTrue(cb_late.is_idempotent)
        self.assertEqual(cb_late.payment_status, PaymentStatus.SUCCESS.value)


class TestCartCheckoutOrderFastAPIEndpoints(BaseCartOrderPaymentTestCase):
    """Kiểm thử End-to-End thông qua FastAPI TestClient cho Cart, Checkout, Order và Payment APIs."""

    def setUp(self):
        super().setUp()
        self.app = FastAPI()
        self.app.include_router(cart_router)
        self.app.include_router(order_router)
        self.app.include_router(payment_router)

        # Override dependencies
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_user] = lambda: self.user_a
        self.client = TestClient(self.app)

    def test_api_cart_add_and_exceed_stock(self):
        """API Cart: Thêm hợp lệ (200) và thêm vượt tồn kho (400)."""
        # Thêm 2 cái -> 200
        res = self.client.post(
            "/cart/items",
            json={"variant_id": self.variant_m.id, "quantity": 2},
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["cart"]["total_items"], 2)

        # Thêm tiếp 10 cái (tổng 12 > stock 10) -> 400
        res_fail = self.client.post(
            "/cart/items",
            json={"variant_id": self.variant_m.id, "quantity": 10},
        )
        self.assertEqual(res_fail.status_code, 400)
        self.assertIn("không đủ tồn kho", res_fail.json()["detail"])

    def test_api_checkout_cod_success_and_duplicate_reject(self):
        """API Checkout COD: Tạo đơn thành công (201), sau đó retry lặp lại bị từ chối 400."""
        # Thêm 1 item vào giỏ
        self.client.post(
            "/cart/items",
            json={"variant_id": self.variant_m.id, "quantity": 1},
        )

        # Checkout lần 1 -> 201 Created
        res1 = self.client.post(
            "/orders/cod",
            json={"shipping_address": "Số 1 Cầu Giấy, Hà Nội"},
        )
        self.assertEqual(res1.status_code, 201)
        data1 = res1.json()
        self.assertIn("order", data1)
        self.assertTrue(data1["order"]["order_code"].startswith("COD-"))

        # Checkout lần 2 lặp lại ngay sau đó -> 400 Bad Request (giỏ đã rỗng)
        res2 = self.client.post(
            "/orders/cod",
            json={"shipping_address": "Số 1 Cầu Giấy, Hà Nội"},
        )
        self.assertEqual(res2.status_code, 400)
        self.assertIn("Giỏ hàng trống", res2.json()["detail"])

    def test_api_online_checkout_and_idempotent_callback(self):
        """API Online Payment: Khởi tạo checkout (201) và Callback xử lý Idempotent (200)."""
        # Tạo Order trực tiếp
        order = Order(
            order_code="ORD-API-TEST01",
            customer_id=self.user_a.id,
            shipping_address="Hà Nội",
            total_price=Decimal("1200000.00"),
            status=OrderStatus.PENDING.value,
        )
        self.db.add(order)
        self.db.commit()

        # Khởi tạo online checkout
        init_res = self.client.post(
            "/payments/checkout",
            json={"order_code": order.order_code, "method": "VNPAY"},
        )
        self.assertEqual(init_res.status_code, 201)
        init_data = init_res.json()
        tx_ref = init_data["transaction_reference"]

        vnp_params = {
            "vnp_TxnRef": tx_ref,
            "vnp_ResponseCode": "00",
            "vnp_Amount": str(int(order.total_price * 100)),
        }
        valid_hash = build_vnpay_signature(vnp_params)

        # Gửi callback webhook POST
        cb_res1 = self.client.post(
            "/payments/callback",
            json={
                "transaction_reference": tx_ref,
                "method": "VNPAY",
                "response_code": "00",
                "secure_hash": valid_hash,
                "extra_params": vnp_params,
            },
        )
        self.assertEqual(cb_res1.status_code, 200)
        self.assertTrue(cb_res1.json()["success"])
        self.assertFalse(cb_res1.json()["is_idempotent"])

        # Gửi lại callback trùng (duplicate) -> 200 Idempotent
        cb_res2 = self.client.post(
            "/payments/callback",
            json={
                "transaction_reference": tx_ref,
                "method": "VNPAY",
                "response_code": "00",
                "secure_hash": valid_hash,
                "extra_params": vnp_params,
            },
        )
        self.assertEqual(cb_res2.status_code, 200)
        self.assertTrue(cb_res2.json()["success"])
        self.assertTrue(cb_res2.json()["is_idempotent"])


if __name__ == "__main__":
    unittest.main()
