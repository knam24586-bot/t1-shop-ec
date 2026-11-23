"""Bộ kiểm thử cho API Vendor xem, xác nhận/từ chối và cập nhật đơn hàng của Store.
Kiểm tra toàn diện tất cả các tiêu chí chấp nhận:
1. VENDOR CHỈ XEM/THAO TÁC ĐƠN THUỘC STORE CỦA MÌNH:
   - Vendor Store 1 chỉ thấy đơn của Store 1.
   - Vendor Store 2 chỉ thấy đơn của Store 2.
   - Vendor Store 1 cố truy cập đơn của Store 2 -> 403 Forbidden.
   - Thiếu Header X-Store-Id hoặc X-Role không hợp lệ -> 401/403.
2. XÁC NHẬN ĐƠN HÀNG (CONFIRM):
   - Đơn PENDING -> Xác nhận -> CONFIRMED.
   - Lưu lịch sử trạng thái kèm lý do.
   - Đơn không phải PENDING thì không được xác nhận -> 400 Bad Request.
3. TỪ CHỐI / HỦY ĐƠN HÀNG (REJECT) CẦN LÝ DO VÀ LƯU LỊCH SỬ:
   - Bắt buộc có lý do (tối thiểu 3 ký tự).
   - Chuyển trạng thái sang CANCELLED và lưu lịch sử.
   - Giải phóng tồn kho cho sản phẩm trong đơn.
4. CHUYỂN TRẠNG THÁI THEO STATE MACHINE:
   - Chuyển tuần tự: CONFIRMED -> PROCESSING -> SHIPPED -> DELIVERED.
   - Chuyển nhảy cóc (VD: PENDING -> SHIPPED) -> 400 Bad Request.
   - Đơn DELIVERED hoặc CANCELLED không thể đổi trạng thái tiếp -> 400 Bad Request.
5. TRA CỨU LỊCH SỬ CHUYỂN ĐỔI TRẠNG THÁI (History Timeline).
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

from app.db.session import Base, get_db
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.category import Category
from app.models.order import Order, OrderStatus
from app.models.order_cancellation import OrderCancellation
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.product import Product
from app.models.store import Store
from app.models.store_order import StoreOrder
from app.models.user import User
from app.models.variant import ProductVariant
from app.models.wishlist import Wishlist  # noqa: F401
from app.routers.vendor_order import router as vendor_order_router, store_orders_router


class TestVendorOrderAPIs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        # Database SQLite in-memory dùng StaticPool
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        # 1. Tạo Users: Customer, Vendor 1, Vendor 2
        self.customer = User(
            full_name="Khách Hàng A",
            email="customer@t1.gg",
            password_hash="hash_pw_customer",
            role="CUSTOMER",
            status="Active",
        )
        self.vendor_user_1 = User(
            full_name="Chủ Shop T1 Store",
            email="vendor1@t1.gg",
            password_hash="hash_pw_vendor1",
            role="VENDOR",
            status="Active",
        )
        self.vendor_user_2 = User(
            full_name="Chủ Shop GenG Store",
            email="vendor2@t1.gg",
            password_hash="hash_pw_vendor2",
            role="VENDOR",
            status="Active",
        )
        self.category = Category(name="Áo Đấu", slug="ao-dau", status="Active")
        self.db.add_all([self.customer, self.vendor_user_1, self.vendor_user_2, self.category])
        self.db.flush()

        # 2. Tạo 2 Store: Store 1 (T1 Official) và Store 2 (GenG Official)
        self.store_1 = Store(
            name="T1 Official Shop",
            vendor_id=self.vendor_user_1.id,
            email="t1shop@t1.gg",
            status="Active",
        )
        self.store_2 = Store(
            name="GenG Official Shop",
            vendor_id=self.vendor_user_2.id,
            email="gengshop@geng.gg",
            status="Active",
        )
        self.db.add_all([self.store_1, self.store_2])
        self.db.flush()

        # 3. Tạo Product và Variant cho Store 1
        self.product = Product(
            category_id=self.category.id,
            name="Áo T1 2026",
            slug="ao-t1-2026",
            price=Decimal("800000.00"),
            stock=100,
            status="Published",
        )
        self.db.add(self.product)
        self.db.flush()

        self.variant = ProductVariant(
            product_id=self.product.id,
            sku="T1-JERSEY-RED-M",
            color="Red",
            size="M",
            stock=50,
        )
        self.db.add(self.variant)
        self.db.commit()

        # 4. Khởi tạo FastAPI App gắn vendor router
        self.app = FastAPI()
        self.app.include_router(vendor_order_router, prefix="/api")
        self.app.include_router(vendor_order_router)
        self.app.include_router(store_orders_router, prefix="/api")
        self.app.include_router(store_orders_router)

        def override_get_db():
            session = Session(self.engine)
            try:
                yield session
            finally:
                session.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _create_sample_store_order(
        self,
        store_id: int,
        order_code: str,
        status: str = OrderStatus.PENDING.value,
        quantity: int = 1,
    ) -> Order:
        """Helper tạo đơn hàng và gán vào Store."""
        total = Decimal("800000.00") * quantity
        now = datetime.now()
        order = Order(
            order_code=order_code,
            customer_id=self.customer.id,
            shipping_address="Hà Nội, Việt Nam",
            total_price=total,
            status=status,
            created_at=now,
            updated_at=now,
        )
        self.db.add(order)
        self.db.flush()

        item = OrderItem(
            order_id=order.id,
            variant_id=self.variant.id,
            product_id=self.product.id,
            unit_price=Decimal("800000.00"),
            quantity=quantity,
            line_total=total,
        )
        self.db.add(item)

        # Trừ kho theo đơn
        self.variant.stock -= quantity
        self.product.stock -= quantity

        # Gán đơn cho Store
        store_order = StoreOrder(order_id=order.id, store_id=store_id)
        self.db.add(store_order)

        self.db.commit()
        self.db.refresh(order)
        return order

    # =========================================================================
    # 1. TIÊU CHÍ: VENDOR CHỈ XEM ĐƠN THUỘC STORE CỦA MÌNH
    # =========================================================================

    def test_vendor_can_only_view_own_store_orders_in_list(self):
        """Vendor chỉ xem được danh sách đơn hàng thuộc Store của mình."""
        # Store 1 có 2 đơn hàng, Store 2 có 1 đơn hàng
        self._create_sample_store_order(self.store_1.id, "ORD-STORE1-01")
        self._create_sample_store_order(self.store_1.id, "ORD-STORE1-02")
        self._create_sample_store_order(self.store_2.id, "ORD-STORE2-01")

        # Vendor 1 (X-Store-Id = 1) xem danh sách -> chỉ thấy 2 đơn của Store 1
        res1 = self.client.get(
            "/api/vendor/orders",
            headers={
                "X-Role": "VENDOR",
                "X-Store-Id": str(self.store_1.id),
                "X-User-Id": str(self.vendor_user_1.id),
            },
        )
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertEqual(data1["total"], 2)
        codes1 = [o["order_code"] for o in data1["items"]]
        self.assertIn("ORD-STORE1-01", codes1)
        self.assertIn("ORD-STORE1-02", codes1)
        self.assertNotIn("ORD-STORE2-01", codes1)

        # Vendor 2 (X-Store-Id = 2) xem danh sách -> chỉ thấy 1 đơn của Store 2
        res2 = self.client.get(
            "/api/vendor/orders",
            headers={
                "X-Role": "VENDOR",
                "X-Store-Id": str(self.store_2.id),
                "X-User-Id": str(self.vendor_user_2.id),
            },
        )
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2["total"], 1)
        self.assertEqual(data2["items"][0]["order_code"], "ORD-STORE2-01")

    def test_vendor_cannot_view_or_access_other_store_order_detail(self):
        """Vendor không thể xem chi tiết đơn hàng của Store khác (403 Forbidden)."""
        order_s1 = self._create_sample_store_order(self.store_1.id, "ORD-SECRET-S1")

        # Vendor 2 cố tình xem đơn của Store 1 -> 403 Forbidden
        res = self.client.get(
            f"/api/vendor/orders/{order_s1.order_code}",
            headers={
                "X-Role": "VENDOR",
                "X-Store-Id": str(self.store_2.id),
                "X-User-Id": str(self.vendor_user_2.id),
            },
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("không thuộc store", res.json()["detail"].lower())

    def test_missing_store_id_or_unauthorized_role_rejected(self):
        """Yêu cầu thiếu X-Store-Id hoặc role không hợp lệ bị từ chối 401/403."""
        # Thiếu X-Store-Id khi Role là VENDOR
        res1 = self.client.get(
            "/api/vendor/orders",
            headers={"X-Role": "VENDOR"},
        )
        self.assertEqual(res1.status_code, 403)

        # Role không phải VENDOR hoặc ADMIN (VD: CUSTOMER)
        res2 = self.client.get(
            "/api/vendor/orders",
            headers={"X-Role": "CUSTOMER", "X-Store-Id": "1"},
        )
        self.assertEqual(res2.status_code, 401)

    # =========================================================================
    # 2. TIÊU CHÍ: XÁC NHẬN ĐƠN HÀNG (CONFIRM: PENDING -> CONFIRMED)
    # =========================================================================

    def test_confirm_order_success(self):
        """Vendor xác nhận đơn hàng PENDING -> chuyển thành CONFIRMED và lưu lịch sử."""
        order = self._create_sample_store_order(self.store_1.id, "ORD-CONFIRM-01", status=OrderStatus.PENDING.value)

        res = self.client.post(
            f"/api/vendor/orders/{order.order_code}/confirm",
            headers={
                "X-Role": "VENDOR",
                "X-Store-Id": str(self.store_1.id),
                "X-User-Id": str(self.vendor_user_1.id),
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["order_code"], "ORD-CONFIRM-01")
        self.assertEqual(data["previous_status"], OrderStatus.PENDING.value)
        self.assertEqual(data["current_status"], OrderStatus.CONFIRMED.value)

        # Kiểm tra Database
        self.db.expire_all()
        order_db = self.db.get(Order, order.id)
        self.assertEqual(order_db.status, OrderStatus.CONFIRMED.value)

        # Kiểm tra lịch sử OrderStatusHistory đã được tạo
        history = self.db.scalar(
            select(OrderStatusHistory)
            .where(OrderStatusHistory.order_id == order.id)
            .order_by(OrderStatusHistory.id.desc())
        )
        self.assertIsNotNone(history)
        self.assertEqual(history.previous_status, OrderStatus.PENDING.value)
        self.assertEqual(history.new_status, OrderStatus.CONFIRMED.value)
        self.assertEqual(history.changed_by_role, "VENDOR")

    def test_cannot_confirm_non_pending_order(self):
        """Chỉ đơn PENDING mới được xác nhận, đơn đã CONFIRMED không thể xác nhận tiếp."""
        order = self._create_sample_store_order(self.store_1.id, "ORD-ALREADY-CONFIRMED", status=OrderStatus.CONFIRMED.value)

        res = self.client.post(
            f"/api/vendor/orders/{order.order_code}/confirm",
            headers={
                "X-Role": "VENDOR",
                "X-Store-Id": str(self.store_1.id),
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("chỉ cho phép xác nhận khi đơn ở trạng thái pending", res.json()["detail"].lower())

    # =========================================================================
    # 3. TIÊU CHÍ: TỪ CHỐI / HỦY CẦN LÝ DO VÀ LƯU LỊCH SỬ (REJECT)
    # =========================================================================

    def test_reject_order_with_reason_and_history(self):
        """Vendor từ chối đơn PENDING kèm lý do -> CANCELLED, lưu lịch sử và hoàn tồn."""
        initial_variant_stock = self.variant.stock  # sau khi tạo đơn đã bị trừ 2
        order = self._create_sample_store_order(
            self.store_1.id, "ORD-REJECT-01", status=OrderStatus.PENDING.value, quantity=2
        )
        stock_after_order = self.db.get(ProductVariant, self.variant.id).stock

        payload = {"reason": "Sản phẩm tạm thời hết size M, cửa hàng xin lỗi quý khách"}
        res = self.client.post(
            f"/api/vendor/orders/{order.order_code}/reject",
            json=payload,
            headers={
                "X-Role": "VENDOR",
                "X-Store-Id": str(self.store_1.id),
                "X-User-Id": str(self.vendor_user_1.id),
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["current_status"], OrderStatus.CANCELLED.value)
        self.assertEqual(data["reason"], payload["reason"])

        # Kiểm tra Database
        self.db.expire_all()
        order_db = self.db.get(Order, order.id)
        self.assertEqual(order_db.status, OrderStatus.CANCELLED.value)

        # Kiểm tra lịch sử chuyển trạng thái
        history = self.db.scalar(
            select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id)
        )
        self.assertIsNotNone(history)
        self.assertEqual(history.previous_status, OrderStatus.PENDING.value)
        self.assertEqual(history.new_status, OrderStatus.CANCELLED.value)
        self.assertEqual(history.reason, payload["reason"])

        # Tồn kho được hoàn lại (+2)
        variant_db = self.db.get(ProductVariant, self.variant.id)
        self.assertEqual(variant_db.stock, stock_after_order + 2)

    def test_reject_order_requires_valid_reason(self):
        """Từ chối đơn hàng mà không có lý do hoặc lý do quá ngắn -> Bị từ chối 400/422."""
        order = self._create_sample_store_order(self.store_1.id, "ORD-NO-REASON", status=OrderStatus.PENDING.value)

        # Không có lý do
        res_empty = self.client.post(
            f"/api/vendor/orders/{order.order_code}/reject",
            json={"reason": "   "},
            headers={"X-Role": "VENDOR", "X-Store-Id": str(self.store_1.id)},
        )
        self.assertIn(res_empty.status_code, [400, 422])

        # Lý do chỉ 2 ký tự
        res_short = self.client.post(
            f"/api/vendor/orders/{order.order_code}/reject",
            json={"reason": "Ko"},
            headers={"X-Role": "VENDOR", "X-Store-Id": str(self.store_1.id)},
        )
        self.assertIn(res_short.status_code, [400, 422])

        # Trạng thái đơn không đổi
        self.db.expire_all()
        self.assertEqual(self.db.get(Order, order.id).status, OrderStatus.PENDING.value)

    # =========================================================================
    # 4. TIÊU CHÍ: CHUYỂN TRẠNG THÁI THEO STATE MACHINE
    # =========================================================================

    def test_valid_state_machine_transitions_step_by_step(self):
        """Chuyển đổi trạng thái tuần tự hợp lệ: PENDING -> CONFIRMED -> PROCESSING -> SHIPPED -> DELIVERED."""
        order = self._create_sample_store_order(self.store_1.id, "ORD-LIFECYCLE-01", status=OrderStatus.PENDING.value)
        headers = {"X-Role": "VENDOR", "X-Store-Id": str(self.store_1.id)}

        # 1. PENDING -> CONFIRMED
        res1 = self.client.patch(
            f"/api/vendor/orders/{order.order_code}/status",
            json={"status": "CONFIRMED"},
            headers=headers,
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["current_status"], OrderStatus.CONFIRMED.value)

        # 2. CONFIRMED -> PROCESSING
        res2 = self.client.patch(
            f"/api/vendor/orders/{order.order_code}/status",
            json={"status": "PROCESSING", "reason": "Bắt đầu đóng gói sản phẩm"},
            headers=headers,
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["current_status"], OrderStatus.PROCESSING.value)

        # 3. PROCESSING -> SHIPPED
        res3 = self.client.patch(
            f"/api/vendor/orders/{order.order_code}/status",
            json={"status": "SHIPPED", "reason": "Bàn giao cho đơn vị vận chuyển ViettelPost"},
            headers=headers,
        )
        self.assertEqual(res3.status_code, 200)
        self.assertEqual(res3.json()["current_status"], OrderStatus.SHIPPED.value)

        # 4. SHIPPED -> DELIVERED
        res4 = self.client.patch(
            f"/api/vendor/orders/{order.order_code}/status",
            json={"status": "DELIVERED", "reason": "Khách hàng đã nhận được hàng thành công"},
            headers=headers,
        )
        self.assertEqual(res4.status_code, 200)
        self.assertEqual(res4.json()["current_status"], OrderStatus.DELIVERED.value)

    def test_invalid_state_machine_transition_jump_rejected(self):
        """Chuyển trạng thái nhảy cóc (PENDING -> SHIPPED) bị từ chối 400 Bad Request."""
        order = self._create_sample_store_order(self.store_1.id, "ORD-JUMP-01", status=OrderStatus.PENDING.value)

        res = self.client.patch(
            f"/api/vendor/orders/{order.order_code}/status",
            json={"status": "SHIPPED"},
            headers={"X-Role": "VENDOR", "X-Store-Id": str(self.store_1.id)},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("state machine", res.json()["detail"].lower())

    def test_terminated_state_cannot_be_changed(self):
        """Trạng thái DELIVERED và CANCELLED là trạng thái kết thúc, không thể đổi sang trạng thái khác."""
        # Đơn DELIVERED
        order_delivered = self._create_sample_store_order(
            self.store_1.id, "ORD-DELIVERED-IMMUTABLE", status=OrderStatus.DELIVERED.value
        )
        res_del = self.client.patch(
            f"/api/vendor/orders/{order_delivered.order_code}/status",
            json={"status": "CONFIRMED"},
            headers={"X-Role": "VENDOR", "X-Store-Id": str(self.store_1.id)},
        )
        self.assertEqual(res_del.status_code, 400)

        # Đơn CANCELLED
        order_cancelled = self._create_sample_store_order(
            self.store_1.id, "ORD-CANCELLED-IMMUTABLE", status=OrderStatus.CANCELLED.value
        )
        res_can = self.client.patch(
            f"/api/vendor/orders/{order_cancelled.order_code}/status",
            json={"status": "PENDING"},
            headers={"X-Role": "VENDOR", "X-Store-Id": str(self.store_1.id)},
        )
        self.assertEqual(res_can.status_code, 400)

    def test_update_status_to_cancelled_requires_reason(self):
        """Khi cập nhật trạng thái sang CANCELLED, bắt buộc phải có lý do (reason)."""
        order = self._create_sample_store_order(self.store_1.id, "ORD-CANCEL-REQ-REASON", status=OrderStatus.CONFIRMED.value)

        res = self.client.patch(
            f"/api/vendor/orders/{order.order_code}/status",
            json={"status": "CANCELLED"},
            headers={"X-Role": "VENDOR", "X-Store-Id": str(self.store_1.id)},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("bắt buộc phải có lý do", res.json()["detail"].lower())

    # =========================================================================
    # 5. TIÊU CHÍ: LỊCH SỬ CHUYỂN TRẠNG THÁI (HISTORY) VÀ ALIASES
    # =========================================================================

    def test_get_order_status_history_timeline(self):
        """Xem toàn bộ dòng thời gian chuyển trạng thái của một đơn hàng."""
        order = self._create_sample_store_order(self.store_1.id, "ORD-TIMELINE-01", status=OrderStatus.PENDING.value)
        headers = {"X-Role": "VENDOR", "X-Store-Id": str(self.store_1.id)}

        # Confirm
        self.client.post(f"/api/vendor/orders/{order.order_code}/confirm", headers=headers)
        # Update sang PROCESSING
        self.client.patch(
            f"/api/vendor/orders/{order.order_code}/status",
            json={"status": "PROCESSING", "reason": "Đang đóng gói"},
            headers=headers,
        )

        # Lấy lịch sử qua /history
        res = self.client.get(
            f"/api/vendor/orders/{order.order_code}/history",
            headers=headers,
        )
        self.assertEqual(res.status_code, 200)
        history_list = res.json()
        self.assertEqual(len(history_list), 2)
        self.assertEqual(history_list[0]["previous_status"], OrderStatus.PENDING.value)
        self.assertEqual(history_list[0]["new_status"], OrderStatus.CONFIRMED.value)
        self.assertEqual(history_list[1]["previous_status"], OrderStatus.CONFIRMED.value)
        self.assertEqual(history_list[1]["new_status"], OrderStatus.PROCESSING.value)
        self.assertEqual(history_list[1]["reason"], "Đang đóng gói")

    def test_store_orders_alias_router(self):
        """Kiểm tra hoạt động của router alias /stores/{store_id}/orders."""
        self._create_sample_store_order(self.store_1.id, "ORD-ALIAS-01")

        res = self.client.get(
            f"/api/stores/{self.store_1.id}/orders",
            headers={"X-Role": "VENDOR", "X-Store-Id": str(self.store_1.id)},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total"], 1)
        self.assertEqual(res.json()["items"][0]["order_code"], "ORD-ALIAS-01")


if __name__ == "__main__":
    unittest.main()
