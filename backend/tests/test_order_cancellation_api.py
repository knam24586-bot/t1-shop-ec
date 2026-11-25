"""Bộ kiểm thử cho chức năng Hủy đơn hàng, Cập nhật trạng thái và Giải phóng tồn kho.
Kiểm tra toàn diện tất cả các tiêu chí chấp nhận:
1. CHỈ HỦY ĐƠN Ở TRẠNG THÁI CHO PHÉP:
   - Cho phép hủy đơn ở trạng thái PENDING hoặc CONFIRMED.
   - Chặn hủy đơn đang vận chuyển (SHIPPED).
   - Chặn hủy đơn đã hủy (CANCELLED).
2. LƯU LÝ DO:
   - Bắt buộc phải có lý do hủy (reason >= 3 ký tự).
   - Lý do được lưu trữ trong DB và có thể tra cứu lại.
3. GIẢI PHÓNG/HOÀN TỒN ĐÚNG MỘT LẦN:
   - Tồn kho của variant và product được hoàn đúng số lượng đã đặt.
   - Thử hủy lần 2 -> Bị từ chối, tồn kho KHÔNG bị cộng dồn lần 2.
   - Hỗ trợ đơn có nhiều mặt hàng (multi-items).
4. ĐƠN ĐÃ GIAO KHÔNG BỊ HỦY TRÁI QUY TẮC:
   - Đơn ở trạng thái DELIVERED tuyệt đối không được phép hủy.
   - Trạng thái và tồn kho giữ nguyên vẹn.
5. USER ISOLATION:
   - User B không thể hủy đơn của User A.
"""
from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.tokens import create_access_token
from app.db.session import Base, get_db
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.category import Category
from app.models.order import Order, OrderStatus
from app.models.order_cancellation import OrderCancellation
from app.models.order_item import OrderItem
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.product import Product
from app.models.user import User
from app.models.variant import ProductVariant
from app.models.wishlist import Wishlist  # noqa: F401
from app.routers.order_cancellation import (
    orders_cancellation_router,
    router as customer_cancellation_router,
)


class TestOrderCancellationAPIs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        self._orig_secret = settings.JWT_SECRET_KEY
        settings.JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-characters-long"
        # Database SQLite in-memory dùng StaticPool
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        # 1. Tạo 2 User: User A (Faker) và User B (Oner)
        self.user_a = User(
            full_name="Lee Sang-hyeok (Faker)",
            email="faker@t1.gg",
            password_hash="pw_hash_faker",
            role="CUSTOMER",
            status="Active",
        )
        self.user_b = User(
            full_name="Mun Hyeon-jun (Oner)",
            email="oner@t1.gg",
            password_hash="pw_hash_oner",
            role="CUSTOMER",
            status="Active",
        )
        self.category = Category(name="Áo Đấu T1", slug="ao-dau-t1", status="Active")
        self.db.add_all([self.user_a, self.user_b, self.category])
        self.db.flush()

        # 2. Tạo Product và Variants với tồn kho xác định
        self.product = Product(
            category_id=self.category.id,
            name="Áo Đấu T1 2026",
            slug="ao-dau-t1-2026",
            price=Decimal("900000.00"),
            stock=50,
            status="Published",
        )
        self.db.add(self.product)
        self.db.flush()

        # Variant M: Tồn kho = 20
        self.variant_m = ProductVariant(
            product_id=self.product.id,
            sku="T1-JERSEY-M",
            color="Red",
            size="M",
            stock=20,
        )
        # Variant L: Tồn kho = 15
        self.variant_l = ProductVariant(
            product_id=self.product.id,
            sku="T1-JERSEY-L",
            color="Red",
            size="L",
            stock=15,
        )
        self.db.add_all([self.variant_m, self.variant_l])
        self.db.commit()

        # 3. Khởi tạo FastAPI App gắn router
        self.app = FastAPI()
        self.app.include_router(customer_cancellation_router, prefix="/api")
        self.app.include_router(customer_cancellation_router)
        self.app.include_router(orders_cancellation_router, prefix="/api")
        self.app.include_router(orders_cancellation_router)

        def override_get_db():
            session = Session(self.engine)
            try:
                yield session
            finally:
                session.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def _auth_headers(self, user: User) -> dict[str, str]:
        token, _ = create_access_token(user)
        return {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.JWT_SECRET_KEY = self._orig_secret

    def _create_order_with_stock_deduction(
        self,
        user_id: int,
        order_code: str,
        items_spec: list[tuple[ProductVariant, int, Decimal]],
        status: str = OrderStatus.PENDING.value,
    ) -> Order:
        """Helper tạo đơn hàng và mô phỏng việc trừ tồn kho ban đầu khi tạo đơn."""
        total_price = Decimal("0.00")
        for variant, qty, price in items_spec:
            # Trừ tồn kho như khi tạo đơn
            variant.stock -= qty
            if variant.product and variant.product.stock is not None:
                variant.product.stock = max(0, variant.product.stock - qty)
            total_price += price * qty

        now = datetime.now()
        order = Order(
            order_code=order_code,
            customer_id=user_id,
            shipping_address="Số 10 Nguyễn Trãi, Thanh Xuân, Hà Nội",
            total_price=total_price,
            status=status,
            created_at=now,
            updated_at=now,
        )
        self.db.add(order)
        self.db.flush()

        for variant, qty, price in items_spec:
            item = OrderItem(
                order_id=order.id,
                variant_id=variant.id,
                product_id=variant.product_id,
                unit_price=price,
                quantity=qty,
                line_total=price * qty,
            )
            self.db.add(item)

        payment = Payment(
            order_id=order.id,
            method=PaymentMethod.COD.value,
            amount=total_price,
            status=PaymentStatus.PENDING.value,
            attempt_number=1,
            transaction_reference=f"REF-{order_code}",
        )
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(order)
        return order

    # =========================================================================
    # 1. TIÊU CHÍ: CHỈ HỦY ĐƠN Ở TRẠNG THÁI CHO PHÉP & CẬP NHẬT TRẠNG THÁI
    # =========================================================================

    def test_cancel_order_in_pending_status_success(self):
        """Đơn hàng ở trạng thái PENDING -> Hủy thành công, chuyển sang CANCELLED."""
        # Variant M ban đầu có 20, mua 2 -> còn 18
        order = self._create_order_with_stock_deduction(
            user_id=self.user_a.id,
            order_code="ORD-PENDING-01",
            items_spec=[(self.variant_m, 2, Decimal("900000.00"))],
            status=OrderStatus.PENDING.value,
        )
        self.assertEqual(self.db.get(ProductVariant, self.variant_m.id).stock, 18)

        payload = {"reason": "Tôi đặt nhầm sản phẩm, muốn hủy để chọn lại"}
        res = self.client.post(
            f"/api/customer/orders/{order.order_code}/cancel",
            json=payload,
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["order_code"], "ORD-PENDING-01")
        self.assertEqual(data["previous_status"], OrderStatus.PENDING.value)
        self.assertEqual(data["current_status"], OrderStatus.CANCELLED.value)
        self.assertEqual(data["reason"], payload["reason"])
        self.assertTrue(data["inventory_restocked"])
        self.assertEqual(data["restocked_items_count"], 2)

        # Kiểm tra Database: Trạng thái Order là CANCELLED
        self.db.expire_all()
        order_db = self.db.get(Order, order.id)
        self.assertEqual(order_db.status, OrderStatus.CANCELLED.value)

        # Payment cũng chuyển thành CANCELLED
        payment_db = self.db.scalar(select(Payment).where(Payment.order_id == order.id))
        self.assertEqual(payment_db.status, PaymentStatus.CANCELLED.value)

    def test_cancel_order_in_confirmed_status_success(self):
        """Đơn hàng ở trạng thái CONFIRMED -> Hủy thành công."""
        order = self._create_order_with_stock_deduction(
            user_id=self.user_a.id,
            order_code="ORD-CONFIRMED-01",
            items_spec=[(self.variant_m, 1, Decimal("900000.00"))],
            status=OrderStatus.CONFIRMED.value,
        )

        payload = {"reason": "Không còn nhu cầu mua nữa"}
        res = self.client.post(
            f"/api/customer/orders/{order.order_code}/cancel",
            json=payload,
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["current_status"], OrderStatus.CANCELLED.value)

    def test_reject_cancel_shipped_order(self):
        """Đơn hàng đang vận chuyển (SHIPPED) -> Từ chối hủy (400 Bad Request)."""
        order = self._create_order_with_stock_deduction(
            user_id=self.user_a.id,
            order_code="ORD-SHIPPED-01",
            items_spec=[(self.variant_m, 1, Decimal("900000.00"))],
            status=OrderStatus.SHIPPED.value,
        )
        stock_before = self.db.get(ProductVariant, self.variant_m.id).stock

        res = self.client.post(
            f"/api/customer/orders/{order.order_code}/cancel",
            json={"reason": "Hủy đơn hàng đang giao"},
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("vận chuyển", res.json()["detail"].lower())

        # Tồn kho và trạng thái không đổi
        self.db.expire_all()
        self.assertEqual(self.db.get(Order, order.id).status, OrderStatus.SHIPPED.value)
        self.assertEqual(self.db.get(ProductVariant, self.variant_m.id).stock, stock_before)

    # =========================================================================
    # 2. TIÊU CHÍ: ĐƠN ĐÃ GIAO KHÔNG BỊ HỦY TRÁI QUY TẮC
    # =========================================================================

    def test_delivered_order_cannot_be_cancelled(self):
        """Đơn đã giao (DELIVERED) TUYỆT ĐỐI không bị hủy trái quy tắc."""
        order = self._create_order_with_stock_deduction(
            user_id=self.user_a.id,
            order_code="ORD-DELIVERED-01",
            items_spec=[(self.variant_m, 3, Decimal("900000.00"))],
            status=OrderStatus.DELIVERED.value,
        )
        variant_stock_before = self.db.get(ProductVariant, self.variant_m.id).stock
        product_stock_before = self.db.get(Product, self.product.id).stock

        res = self.client.post(
            f"/api/customer/orders/{order.order_code}/cancel",
            json={"reason": "Đã nhận hàng nhưng muốn hủy đơn"},
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res.status_code, 400)
        detail_msg = res.json()["detail"].lower()
        self.assertIn("giao thành công", detail_msg)
        self.assertIn("delivered", detail_msg)

        # Kiểm tra tính toàn vẹn: Trạng thái và tồn kho giữ nguyên 100%
        self.db.expire_all()
        order_db = self.db.get(Order, order.id)
        self.assertEqual(order_db.status, OrderStatus.DELIVERED.value)
        self.assertEqual(self.db.get(ProductVariant, self.variant_m.id).stock, variant_stock_before)
        self.assertEqual(self.db.get(Product, self.product.id).stock, product_stock_before)

        # Không có bản ghi OrderCancellation nào được tạo
        cancellations = self.db.scalars(
            select(OrderCancellation).where(OrderCancellation.order_id == order.id)
        ).all()
        self.assertEqual(len(cancellations), 0)

    # =========================================================================
    # 3. TIÊU CHÍ: GIẢI PHÓNG/HOÀN TỒN ĐÚNG MỘT LẦN
    # =========================================================================

    def test_inventory_restocked_exactly_once_on_duplicate_cancel(self):
        """Tồn kho chỉ được hoàn ĐÚNG MỘT LẦN, cố tình hủy lần 2 không cộng thêm tồn kho."""
        initial_variant_stock = self.variant_m.stock  # 20
        initial_product_stock = self.product.stock    # 50

        # Đặt 4 áo Size M: Tồn kho variant = 16, product = 46
        order = self._create_order_with_stock_deduction(
            user_id=self.user_a.id,
            order_code="ORD-ONCE-01",
            items_spec=[(self.variant_m, 4, Decimal("900000.00"))],
            status=OrderStatus.PENDING.value,
        )
        self.assertEqual(self.db.get(ProductVariant, self.variant_m.id).stock, 16)
        self.assertEqual(self.db.get(Product, self.product.id).stock, 46)

        # 1. Hủy lần 1: Thành công 200 OK -> Tồn kho được hoàn lại đầy đủ (+4)
        payload = {"reason": "Hủy đơn lần thứ nhất"}
        res1 = self.client.post(
            f"/api/customer/orders/{order.order_code}/cancel",
            json=payload,
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res1.status_code, 200)

        # Kiểm tra tồn kho sau lần 1: đã trở về 20 và 50
        self.db.expire_all()
        self.assertEqual(self.db.get(ProductVariant, self.variant_m.id).stock, initial_variant_stock)
        self.assertEqual(self.db.get(Product, self.product.id).stock, initial_product_stock)

        # 2. Thử gọi hủy lần 2: Phải bị từ chối 400 Bad Request
        res2 = self.client.post(
            f"/api/customer/orders/{order.order_code}/cancel",
            json={"reason": "Cố tình gọi hủy lần thứ hai để hack tồn kho"},
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res2.status_code, 400)
        self.assertIn("cancelled", res2.json()["detail"].lower())

        # KIỂM CHỨNG QUAN TRỌNG: Tồn kho KHÔNG bị cộng thêm lần 2 (vẫn giữ nguyên 20 và 50, không phải 24 hay 54)
        self.db.expire_all()
        self.assertEqual(
            self.db.get(ProductVariant, self.variant_m.id).stock,
            initial_variant_stock,
            "LỖI: Tồn kho bị hoàn lại nhiều lần khi gọi hủy lặp lại!",
        )
        self.assertEqual(
            self.db.get(Product, self.product.id).stock,
            initial_product_stock,
            "LỖI: Tồn kho sản phẩm gốc bị hoàn lại nhiều lần!",
        )

    def test_inventory_restocked_multiple_items_order(self):
        """Hoàn tồn chính xác cho đơn hàng có nhiều mặt hàng (multi-items)."""
        # Mua 2 áo Size M (20 -> 18) và 3 áo Size L (15 -> 12), tổng product trừ 5 (50 -> 45)
        order = self._create_order_with_stock_deduction(
            user_id=self.user_a.id,
            order_code="ORD-MULTI-ITEMS",
            items_spec=[
                (self.variant_m, 2, Decimal("900000.00")),
                (self.variant_l, 3, Decimal("900000.00")),
            ],
            status=OrderStatus.PENDING.value,
        )
        self.assertEqual(self.db.get(ProductVariant, self.variant_m.id).stock, 18)
        self.assertEqual(self.db.get(ProductVariant, self.variant_l.id).stock, 12)
        self.assertEqual(self.db.get(Product, self.product.id).stock, 45)

        res = self.client.post(
            f"/api/customer/orders/{order.order_code}/cancel",
            json={"reason": "Hủy đơn hàng có nhiều mặt hàng"},
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["restocked_items_count"], 5)

        # Cả 2 biến thể và sản phẩm đều được hoàn tồn đúng
        self.db.expire_all()
        self.assertEqual(self.db.get(ProductVariant, self.variant_m.id).stock, 20)
        self.assertEqual(self.db.get(ProductVariant, self.variant_l.id).stock, 15)
        self.assertEqual(self.db.get(Product, self.product.id).stock, 50)

    # =========================================================================
    # 4. TIÊU CHÍ: LƯU LÝ DO HỦY VÀ TRA CỨU
    # =========================================================================

    def test_save_cancellation_reason_and_query(self):
        """Lý do hủy đơn được lưu chính xác và có thể tra cứu qua API."""
        order = self._create_order_with_stock_deduction(
            user_id=self.user_a.id,
            order_code="ORD-REASON-01",
            items_spec=[(self.variant_m, 1, Decimal("900000.00"))],
            status=OrderStatus.PENDING.value,
        )

        cancellation_reason = "Tôi muốn thay đổi phương thức thanh toán sang VNPAY"
        res_cancel = self.client.post(
            f"/api/customer/orders/{order.order_code}/cancel",
            json={"reason": cancellation_reason},
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res_cancel.status_code, 200)
        self.assertEqual(res_cancel.json()["reason"], cancellation_reason)

        # Tra cứu lại lý do hủy qua endpoint /cancellation
        res_info = self.client.get(
            f"/api/customer/orders/{order.order_code}/cancellation",
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res_info.status_code, 200)
        info_data = res_info.json()
        self.assertEqual(info_data["order_code"], "ORD-REASON-01")
        self.assertEqual(info_data["reason"], cancellation_reason)
        self.assertEqual(info_data["cancelled_by"], "CUSTOMER")
        self.assertTrue(info_data["inventory_restocked"])

    def test_reject_empty_or_too_short_reason(self):
        """Lý do rỗng hoặc quá ngắn (< 3 ký tự) bị từ chối 400 hoặc 422."""
        order = self._create_order_with_stock_deduction(
            user_id=self.user_a.id,
            order_code="ORD-VAL-01",
            items_spec=[(self.variant_m, 1, Decimal("900000.00"))],
            status=OrderStatus.PENDING.value,
        )

        # Lý do rỗng
        res_empty = self.client.post(
            f"/api/customer/orders/{order.order_code}/cancel",
            json={"reason": "   "},
            headers=self._auth_headers(self.user_a),
        )
        self.assertIn(res_empty.status_code, [400, 422])

        # Lý do chỉ có 2 ký tự
        res_short = self.client.post(
            f"/api/customer/orders/{order.order_code}/cancel",
            json={"reason": "Ko"},
            headers=self._auth_headers(self.user_a),
        )
        self.assertIn(res_short.status_code, [400, 422])

        # Đơn hàng vẫn giữ nguyên PENDING
        self.db.expire_all()
        self.assertEqual(self.db.get(Order, order.id).status, OrderStatus.PENDING.value)

    # =========================================================================
    # 5. TIÊU CHÍ: USER ISOLATION (KHÁCH HÀNG CHỈ HỦY ĐƠN THUỘC VỀ MÌNH)
    # =========================================================================

    def test_user_cannot_cancel_other_user_order(self):
        """User B không thể hủy đơn hàng của User A (trả về 404 Not Found)."""
        order_a = self._create_order_with_stock_deduction(
            user_id=self.user_a.id,
            order_code="ORD-FAKER-01",
            items_spec=[(self.variant_m, 1, Decimal("900000.00"))],
            status=OrderStatus.PENDING.value,
        )
        stock_before = self.db.get(ProductVariant, self.variant_m.id).stock

        # User B cố tình gửi request hủy đơn của User A
        res = self.client.post(
            f"/api/customer/orders/{order_a.order_code}/cancel",
            json={"reason": "User B cố tình hủy đơn của User A"},
            headers=self._auth_headers(self.user_b),
        )
        self.assertEqual(res.status_code, 404)

        # Đơn của User A vẫn giữ nguyên PENDING, tồn kho không bị ảnh hưởng
        self.db.expire_all()
        self.assertEqual(self.db.get(Order, order_a.id).status, OrderStatus.PENDING.value)
        self.assertEqual(self.db.get(ProductVariant, self.variant_m.id).stock, stock_before)

    # =========================================================================
    # 6. KIỂM TRA ROUTER PHỤ /orders/{order_code}/cancel VÀ BODY REQUEST
    # =========================================================================

    def test_alias_cancel_endpoints(self):
        """Kiểm tra endpoint phụ /orders/{order_code}/cancel và /orders/cancel bằng body."""
        order1 = self._create_order_with_stock_deduction(
            user_id=self.user_a.id,
            order_code="ORD-ALIAS-01",
            items_spec=[(self.variant_m, 1, Decimal("900000.00"))],
        )
        order2 = self._create_order_with_stock_deduction(
            user_id=self.user_a.id,
            order_code="ORD-ALIAS-02",
            items_spec=[(self.variant_l, 1, Decimal("900000.00"))],
        )

        # Gọi qua /api/orders/ORD-ALIAS-01/cancel
        res1 = self.client.post(
            f"/api/orders/{order1.order_code}/cancel",
            json={"reason": "Hủy qua alias endpoint"},
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["current_status"], OrderStatus.CANCELLED.value)

        # Gọi qua /api/orders/cancel với body
        res2 = self.client.post(
            "/api/orders/cancel",
            json={
                "order_code": order2.order_code,
                "reason": "Hủy qua endpoint body",
            },
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["current_status"], OrderStatus.CANCELLED.value)


if __name__ == "__main__":
    unittest.main()
