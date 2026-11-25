"""Bộ kiểm thử cho API Admin theo dõi, lọc và cập nhật đơn theo quyền.
Kiểm tra toàn diện tất cả các tiêu chí chấp nhận:
1. ADMIN LỌC/XEM ĐƠN TOÀN HỆ THỐNG:
   - Admin xem được tất cả các đơn hàng thuộc nhiều khách hàng và store khác nhau.
   - Hỗ trợ lọc theo trạng thái (status), khách hàng (customer_id), store (store_id), khoảng giá (price), khoảng thời gian, tìm kiếm mã đơn.
   - Hỗ trợ xem chi tiết toàn diện của đơn hàng.
   - Kiểm tra phân quyền: User có role CUSTOMER hoặc VENDOR bị chặn 403 Forbidden.
2. CẬP NHẬT TRẠNG THÁI THEO QUYỀN VÀ QUY TẮC:
   - Admin cập nhật trạng thái hợp lệ theo State Machine (PENDING -> CONFIRMED -> PROCESSING -> SHIPPED -> DELIVERED).
   - Chặn các bước chuyển trạng thái vi phạm State Machine (PENDING -> SHIPPED, DELIVERED -> CANCELLED...).
   - Hủy đơn cần lý do bắt buộc và giải phóng tồn kho.
3. THAO TÁC QUAN TRỌNG ĐƯỢC GHI LOG:
   - Mọi thao tác cập nhật trạng thái, hủy đơn của Admin đều được ghi vào admin_order_audit_logs.
   - Cung cấp endpoint xem audit log và dòng thời gian lịch sử trạng thái của đơn hàng.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.models.admin_audit_log import AdminOrderAuditLog
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
from app.routers.admin_order import router as admin_order_router


class TestAdminOrderAPIs(unittest.TestCase):
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

        # 1. Tạo các Users: Admin, Customer A, Customer B, Vendor
        self.admin_user = User(
            full_name="Quản Trị Viên (Admin)",
            email="admin@t1.gg",
            password_hash="pw_hash_admin",
            role="ADMIN",
            status="Active",
        )
        self.customer_a = User(
            full_name="Khách Hàng Faker",
            email="faker@t1.gg",
            password_hash="pw_hash_faker",
            role="CUSTOMER",
            status="Active",
        )
        self.customer_b = User(
            full_name="Khách Hàng Oner",
            email="oner@t1.gg",
            password_hash="pw_hash_oner",
            role="CUSTOMER",
            status="Active",
        )
        self.vendor_user = User(
            full_name="Chủ Cửa Hàng Vendor",
            email="vendor@t1.gg",
            password_hash="pw_hash_vendor",
            role="VENDOR",
            status="Active",
        )
        self.category = Category(name="Áo Đấu T1", slug="ao-dau-t1", status="Active")
        self.db.add_all([self.admin_user, self.customer_a, self.customer_b, self.vendor_user, self.category])
        self.db.flush()

        # 2. Tạo 2 Store
        self.store_1 = Store(name="Store Hà Nội", vendor_id=self.vendor_user.id, status="Active")
        self.store_2 = Store(name="Store TP.HCM", vendor_id=self.vendor_user.id, status="Active")
        self.db.add_all([self.store_1, self.store_2])
        self.db.flush()

        # 3. Tạo Product và Variant
        self.product = Product(
            category_id=self.category.id,
            name="Áo Đấu T1 2026",
            slug="ao-dau-t1-2026",
            price=Decimal("1000000.00"),
            stock=100,
            status="Published",
        )
        self.db.add(self.product)
        self.db.flush()

        self.variant = ProductVariant(
            product_id=self.product.id,
            sku="T1-JERSEY-M",
            color="Red",
            size="M",
            stock=50,
        )
        self.db.add(self.variant)
        self.db.commit()

        # 4. Khởi tạo FastAPI App gắn admin order router
        self.app = FastAPI()
        self.app.include_router(admin_order_router, prefix="/api")
        self.app.include_router(admin_order_router)

        def override_get_db():
            session = Session(self.engine)
            try:
                yield session
            finally:
                session.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

        self.admin_headers = {
            "X-Role": "ADMIN",
            "X-User-Id": str(self.admin_user.id),
        }

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _create_sample_order(
        self,
        customer_id: int,
        order_code: str,
        total_price: Decimal,
        status: str = OrderStatus.PENDING.value,
        store_id: int | None = None,
        created_at: datetime | None = None,
        quantity: int = 1,
    ) -> Order:
        """Helper tạo đơn hàng mẫu cho kiểm thử."""
        now = created_at or datetime.now()
        order = Order(
            order_code=order_code,
            customer_id=customer_id,
            shipping_address="Hà Nội, Việt Nam",
            total_price=total_price,
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
            unit_price=total_price / quantity,
            quantity=quantity,
            line_total=total_price,
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

        # Trừ kho
        self.variant.stock -= quantity
        self.product.stock -= quantity

        if store_id is not None:
            so = StoreOrder(order_id=order.id, store_id=store_id)
            self.db.add(so)

        self.db.commit()
        self.db.refresh(order)
        return order

    # =========================================================================
    # 1. TIÊU CHÍ: ADMIN LỌC/XEM ĐƠN TOÀN HỆ THỐNG
    # =========================================================================

    def test_admin_can_view_all_orders_across_system(self):
        """Admin xem được toàn bộ đơn hàng trong hệ thống (không bị giới hạn theo user hay store)."""
        # Tạo đơn của Customer A (Store 1) và Customer B (Store 2)
        self._create_sample_order(self.customer_a.id, "ORD-SYS-01", Decimal("500000.00"), store_id=self.store_1.id)
        self._create_sample_order(self.customer_b.id, "ORD-SYS-02", Decimal("800000.00"), store_id=self.store_2.id)

        res = self.client.get("/api/admin/orders", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 2)
        codes = [o["order_code"] for o in data["items"]]
        self.assertIn("ORD-SYS-01", codes)
        self.assertIn("ORD-SYS-02", codes)

    def test_admin_filter_orders_by_status_and_customer(self):
        """Admin lọc đơn hàng theo trạng thái (status) và khách hàng (customer_id)."""
        self._create_sample_order(self.customer_a.id, "ORD-PEND-A", Decimal("500000.00"), status=OrderStatus.PENDING.value)
        self._create_sample_order(self.customer_a.id, "ORD-CONF-A", Decimal("600000.00"), status=OrderStatus.CONFIRMED.value)
        self._create_sample_order(self.customer_b.id, "ORD-PEND-B", Decimal("700000.00"), status=OrderStatus.PENDING.value)

        # 1. Lọc theo trạng thái CONFIRMED -> chỉ có 1 đơn
        res_conf = self.client.get("/api/admin/orders?status=CONFIRMED", headers=self.admin_headers)
        self.assertEqual(res_conf.status_code, 200)
        d_conf = res_conf.json()
        self.assertEqual(d_conf["total"], 1)
        self.assertEqual(d_conf["items"][0]["order_code"], "ORD-CONF-A")

        # 2. Lọc theo Customer B -> chỉ có 1 đơn
        res_cust = self.client.get(f"/api/admin/orders?customer_id={self.customer_b.id}", headers=self.admin_headers)
        self.assertEqual(res_cust.status_code, 200)
        d_cust = res_cust.json()
        self.assertEqual(d_cust["total"], 1)
        self.assertEqual(d_cust["items"][0]["order_code"], "ORD-PEND-B")

    def test_admin_filter_orders_by_store_and_search_order_code(self):
        """Admin lọc theo Store và tìm kiếm mã đơn hàng."""
        self._create_sample_order(self.customer_a.id, "ORD-SEARCH-MATCH", Decimal("500000.00"), store_id=self.store_1.id)
        self._create_sample_order(self.customer_a.id, "ORD-OTHER-01", Decimal("500000.00"), store_id=self.store_2.id)

        # Lọc theo store_id = 1
        res_st1 = self.client.get(f"/api/admin/orders?store_id={self.store_1.id}", headers=self.admin_headers)
        self.assertEqual(res_st1.status_code, 200)
        self.assertEqual(res_st1.json()["total"], 1)
        self.assertEqual(res_st1.json()["items"][0]["order_code"], "ORD-SEARCH-MATCH")

        # Tìm kiếm theo order_code
        res_search = self.client.get("/api/admin/orders?order_code=MATCH", headers=self.admin_headers)
        self.assertEqual(res_search.status_code, 200)
        self.assertEqual(res_search.json()["total"], 1)
        self.assertEqual(res_search.json()["items"][0]["order_code"], "ORD-SEARCH-MATCH")

    def test_admin_filter_by_price_range_and_pagination(self):
        """Admin lọc theo khoảng giá trị đơn hàng và phân trang."""
        self._create_sample_order(self.customer_a.id, "ORD-P1", Decimal("300000.00"))
        self._create_sample_order(self.customer_a.id, "ORD-P2", Decimal("600000.00"))
        self._create_sample_order(self.customer_a.id, "ORD-P3", Decimal("900000.00"))

        # Lọc min_price=500000 -> P2, P3
        res = self.client.get("/api/admin/orders?min_price=500000&max_price=800000", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["order_code"], "ORD-P2")

    def test_admin_view_order_detail_comprehensive(self):
        """Xem chi tiết đơn hàng: đầy đủ khách hàng, sản phẩm, thanh toán và lịch sử."""
        order = self._create_sample_order(
            self.customer_a.id, "ORD-DETAIL-FULL", Decimal("1000000.00"), store_id=self.store_1.id
        )

        res = self.client.get(f"/api/admin/orders/{order.order_code}", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["order_code"], "ORD-DETAIL-FULL")
        self.assertEqual(data["customer"]["full_name"], "Khách Hàng Faker")
        self.assertEqual(data["customer"]["email"], "faker@t1.gg")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["product_name"], "Áo Đấu T1 2026")
        self.assertIsNotNone(data["payment"])
        self.assertEqual(data["payment"]["method"], "COD")

    def test_non_admin_cannot_access_admin_api(self):
        """Người dùng không có quyền Admin (CUSTOMER, VENDOR) bị từ chối 403 Forbidden."""
        # 1. Customer cố tình gọi API admin
        res_cust = self.client.get(
            "/api/admin/orders",
            headers={"X-Role": "CUSTOMER", "X-User-Id": str(self.customer_a.id)},
        )
        self.assertEqual(res_cust.status_code, 403)
        self.assertIn("chỉ dành riêng cho administrator", res_cust.json()["detail"].lower())

        # 2. Vendor cố tình gọi API admin
        res_vend = self.client.get(
            "/api/admin/orders",
            headers={"X-Role": "VENDOR", "X-User-Id": str(self.vendor_user.id)},
        )
        self.assertEqual(res_vend.status_code, 403)

    # =========================================================================
    # 2. TIÊU CHÍ: CẬP NHẬT TRẠNG THÁI THEO QUYỀN VÀ QUY TẮC
    # =========================================================================

    def test_admin_update_status_following_state_machine(self):
        """Admin cập nhật trạng thái hợp lệ theo State Machine (PENDING -> CONFIRMED)."""
        order = self._create_sample_order(self.customer_a.id, "ORD-ADM-UPDATE-01", Decimal("500000.00"))

        payload = {
            "status": "CONFIRMED",
            "reason": "Admin xác nhận đơn qua điện thoại",
            "admin_note": "Khách hàng xác nhận nhận hàng vào sáng thứ 2",
        }
        res = self.client.patch(
            f"/api/admin/orders/{order.order_code}/status",
            json=payload,
            headers=self.admin_headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["previous_status"], OrderStatus.PENDING.value)
        self.assertEqual(data["current_status"], OrderStatus.CONFIRMED.value)
        self.assertGreater(data["audit_log_id"], 0)

        # Kiểm tra Database
        self.db.expire_all()
        order_db = self.db.get(Order, order.id)
        self.assertEqual(order_db.status, OrderStatus.CONFIRMED.value)

    def test_admin_cannot_break_state_machine_rules(self):
        """Admin không thể chuyển trạng thái vi phạm quy tắc State Machine (nhảy cóc PENDING -> DELIVERED)."""
        order = self._create_sample_order(self.customer_a.id, "ORD-ILLEGAL-TRANS", Decimal("500000.00"))

        res = self.client.patch(
            f"/api/admin/orders/{order.order_code}/status",
            json={"status": "DELIVERED"},
            headers=self.admin_headers,
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("state machine", res.json()["detail"].lower())

    def test_admin_cannot_change_delivered_order_status(self):
        """Đơn đã giao (DELIVERED) không được phép thay đổi trạng thái trái quy tắc."""
        order = self._create_sample_order(
            self.customer_a.id, "ORD-DELIVERED-LOCK", Decimal("500000.00"), status=OrderStatus.DELIVERED.value
        )

        res = self.client.patch(
            f"/api/admin/orders/{order.order_code}/status",
            json={"status": "CANCELLED", "reason": "Hủy đơn đã giao"},
            headers=self.admin_headers,
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("delivered", res.json()["detail"].lower())

    def test_admin_cancel_order_with_mandatory_reason_and_restock(self):
        """Admin hủy đơn hàng: bắt buộc có lý do, hoàn tồn kho và ghi audit log."""
        order = self._create_sample_order(
            self.customer_a.id, "ORD-ADM-CANCEL", Decimal("1000000.00"), status=OrderStatus.PENDING.value, quantity=3
        )
        stock_after_create = self.db.get(ProductVariant, self.variant.id).stock

        # 1. Hủy không có lý do -> Bị từ chối
        res_no_reason = self.client.post(
            f"/api/admin/orders/{order.order_code}/cancel",
            json={"reason": "  "},
            headers=self.admin_headers,
        )
        self.assertIn(res_no_reason.status_code, [400, 422])

        # 2. Hủy có lý do hợp lệ -> Thành công
        cancel_reason = "Đơn hàng có dấu hiệu gian lận thanh toán, hủy theo quy định an toàn"
        res_cancel = self.client.post(
            f"/api/admin/orders/{order.order_code}/cancel",
            json={"reason": cancel_reason, "admin_note": "Case #8892"},
            headers=self.admin_headers,
        )
        self.assertEqual(res_cancel.status_code, 200)
        self.assertEqual(res_cancel.json()["current_status"], OrderStatus.CANCELLED.value)

        # Kiểm tra tồn kho đã được hoàn (+3)
        self.db.expire_all()
        self.assertEqual(self.db.get(ProductVariant, self.variant.id).stock, stock_after_create + 3)

        # Kiểm tra bản ghi OrderCancellation
        cancellation = self.db.scalar(
            select(OrderCancellation).where(OrderCancellation.order_id == order.id)
        )
        self.assertIsNotNone(cancellation)
        self.assertEqual(cancellation.cancelled_by, "ADMIN")
        self.assertEqual(cancellation.reason, cancel_reason)

    # =========================================================================
    # 3. TIÊU CHÍ: THAO TÁC QUAN TRỌNG ĐƯỢC GHI LOG (AUDIT LOGS)
    # =========================================================================

    def test_important_admin_actions_recorded_in_audit_log(self):
        """Mọi thao tác quan trọng của Admin (cập nhật trạng thái, hủy đơn) đều được ghi audit log."""
        order = self._create_sample_order(self.customer_a.id, "ORD-AUDIT-TEST", Decimal("500000.00"))

        # Admin cập nhật trạng thái PENDING -> CONFIRMED
        self.client.patch(
            f"/api/admin/orders/{order.order_code}/status",
            json={"status": "CONFIRMED", "reason": "Xác nhận sau kiểm toán"},
            headers=self.admin_headers,
        )

        # Tra cứu audit logs qua endpoint /audit-logs
        res_logs = self.client.get(
            f"/api/admin/orders/{order.order_code}/audit-logs",
            headers=self.admin_headers,
        )
        self.assertEqual(res_logs.status_code, 200)
        logs = res_logs.json()
        self.assertGreaterEqual(len(logs), 1)

        first_log = logs[0]
        self.assertEqual(first_log["order_code"], "ORD-AUDIT-TEST")
        self.assertEqual(first_log["action"], "UPDATE_STATUS")
        self.assertEqual(first_log["previous_status"], OrderStatus.PENDING.value)
        self.assertEqual(first_log["new_status"], OrderStatus.CONFIRMED.value)
        self.assertEqual(first_log["reason"], "Xác nhận sau kiểm toán")
        self.assertEqual(first_log["admin_id"], self.admin_user.id)
        self.assertIsNotNone(first_log["created_at"])

    def test_audit_logs_included_in_order_detail(self):
        """Thông tin audit log được tích hợp trực tiếp trong response chi tiết đơn hàng của Admin."""
        order = self._create_sample_order(self.customer_a.id, "ORD-EMBED-LOGS", Decimal("500000.00"))

        # Thực hiện cập nhật
        self.client.patch(
            f"/api/admin/orders/{order.order_code}/status",
            json={"status": "CONFIRMED", "reason": "Thao tác cập nhật bởi Admin"},
            headers=self.admin_headers,
        )

        # Xem chi tiết đơn
        res = self.client.get(f"/api/admin/orders/{order.order_code}", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("audit_logs", data)
        self.assertEqual(len(data["audit_logs"]), 1)
        self.assertEqual(data["audit_logs"][0]["action"], "UPDATE_STATUS")


if __name__ == "__main__":
    unittest.main()
