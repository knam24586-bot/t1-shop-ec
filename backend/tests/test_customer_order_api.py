"""Bộ kiểm thử cho API Khách hàng xem danh sách và chi tiết đơn hàng của mình.
Kiểm tra toàn diện tất cả các tiêu chí chấp nhận:
1. CUSTOMER CHỈ XEM ĐƠN THUỘC MÌNH (User Isolation):
   - User A chỉ xem được danh sách đơn hàng của User A.
   - User B không thấy đơn hàng của User A trong danh sách.
   - User B cố truy cập chi tiết đơn hàng của User A -> 404 Not Found.
   - Không đăng nhập hoặc token/header không hợp lệ -> 401 Unauthorized.
2. HỖ TRỢ XEM LIST/DETAIL VÀ PHÂN TRANG (Pagination):
   - Phân trang chuẩn xác: page, limit, total, total_pages, has_next, has_prev.
   - Hỗ trợ xem nhiều trang, offset, giới hạn tối đa limit <= 100.
   - Chặn page <= 0, limit <= 0 -> 422 Unprocessable Entity.
   - Hỗ trợ lọc danh sách theo trạng thái đơn hàng (PENDING, CONFIRMED, DELIVERED...).
   - Xem chi tiết đơn hàng (detail) theo order_code hoặc id.
3. DỮ LIỆU TRẢ VỀ KHÔNG CHỨA THÔNG TIN NỘI BỘ:
   - Tuyệt đối không chứa password_hash, user internal credentials.
   - Tuyệt đối không chứa raw_payload, ip_address, is_valid_signature của webhook log.
   - Tuyệt đối không chứa các trường admin_note, internal_note hoặc cost price.
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
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.category import Category
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.payment_log import PaymentWebhookLog
from app.models.product import Product
from app.models.user import User
from app.models.variant import ProductVariant
from app.models.wishlist import Wishlist  # noqa: F401
from app.routers.customer_order import order_router, router as customer_order_router


class TestCustomerOrderAPIs(unittest.TestCase):
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

        # 1. Tạo 2 User: User A (Faker) và User B (Oner)
        self.user_a = User(
            full_name="Lee Sang-hyeok (Faker)",
            email="faker@t1.gg",
            password_hash="secret_hash_faker_12345",
            role="CUSTOMER",
            status="Active",
        )
        self.user_b = User(
            full_name="Mun Hyeon-jun (Oner)",
            email="oner@t1.gg",
            password_hash="secret_hash_oner_67890",
            role="CUSTOMER",
            status="Active",
        )
        self.category = Category(name="Đồng phục T1", slug="dong-phuc-t1", status="Active")
        self.db.add_all([self.user_a, self.user_b, self.category])
        self.db.flush()

        # 2. Tạo Product và Variant
        self.product = Product(
            category_id=self.category.id,
            name="Áo Đấu T1 CKTG 2026",
            slug="ao-dau-t1-cktg-2026",
            price=Decimal("850000.00"),
            stock=100,
            image_url="https://t1.gg/images/jersey2026.png",
            status="Published",
        )
        self.db.add(self.product)
        self.db.flush()

        self.variant_m = ProductVariant(
            product_id=self.product.id,
            sku="T1-JERSEY-2026-M",
            color="Black/Red",
            size="M",
            stock=50,
        )
        self.variant_l = ProductVariant(
            product_id=self.product.id,
            sku="T1-JERSEY-2026-L",
            color="Black/Red",
            size="L",
            stock=50,
        )
        self.db.add_all([self.variant_m, self.variant_l])
        self.db.commit()

        # 3. Khởi tạo FastAPI App và gắn router
        self.app = FastAPI()
        self.app.include_router(customer_order_router, prefix="/api")
        self.app.include_router(customer_order_router)
        self.app.include_router(order_router, prefix="/api")
        self.app.include_router(order_router)

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

    def _create_sample_order(
        self,
        user_id: int,
        order_code: str,
        total_price: Decimal,
        status: str = OrderStatus.PENDING.value,
        items_count: int = 1,
        payment_method: str = PaymentMethod.COD.value,
        payment_status: str = PaymentStatus.PENDING.value,
    ) -> Order:
        """Helper tạo đơn hàng mẫu kèm OrderItem và Payment."""
        now = datetime.now()
        order = Order(
            order_code=order_code,
            customer_id=user_id,
            total_price=total_price,
            shipping_address="Số 10 Nguyễn Trãi, Thanh Xuân, Hà Nội",
            status=status,
            created_at=now,
            updated_at=now,
        )
        self.db.add(order)
        self.db.flush()

        # Tạo OrderItem
        unit_p = total_price / items_count if items_count > 0 else total_price
        for i in range(items_count):
            item = OrderItem(
                order_id=order.id,
                variant_id=self.variant_m.id,
                product_id=self.product.id,
                unit_price=unit_p,
                quantity=1,
                line_total=unit_p,
            )
            self.db.add(item)

        # Tạo Payment
        payment = Payment(
            order_id=order.id,
            method=payment_method,
            amount=total_price,
            status=payment_status,
            attempt_number=1,
            transaction_reference=f"REF-{order_code}",
        )
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(order)
        return order

    # =========================================================================
    # 1. TIÊU CHÍ: CUSTOMER CHỈ XEM ĐƠN THUỘC MÌNH (User Isolation)
    # =========================================================================

    def test_customer_can_only_view_own_orders_in_list(self):
        """Khách hàng chỉ thấy các đơn hàng của chính mình trong danh sách."""
        # Tạo 3 đơn cho User A và 2 đơn cho User B
        self._create_sample_order(self.user_a.id, "ORD-A1", Decimal("850000.00"))
        self._create_sample_order(self.user_a.id, "ORD-A2", Decimal("1700000.00"))
        self._create_sample_order(self.user_a.id, "ORD-A3", Decimal("2550000.00"))

        self._create_sample_order(self.user_b.id, "ORD-B1", Decimal("500000.00"))
        self._create_sample_order(self.user_b.id, "ORD-B2", Decimal("600000.00"))

        # User A xem danh sách -> chỉ thấy đúng 3 đơn của A
        res_a = self.client.get(
            "/api/customer/orders",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_a.status_code, 200)
        data_a = res_a.json()
        self.assertEqual(data_a["total"], 3)
        self.assertEqual(len(data_a["items"]), 3)
        order_codes_a = [o["order_code"] for o in data_a["items"]]
        self.assertIn("ORD-A1", order_codes_a)
        self.assertIn("ORD-A2", order_codes_a)
        self.assertIn("ORD-A3", order_codes_a)
        self.assertNotIn("ORD-B1", order_codes_a)
        self.assertNotIn("ORD-B2", order_codes_a)

        # User B xem danh sách -> chỉ thấy đúng 2 đơn của B
        res_b = self.client.get(
            "/api/customer/orders",
            headers={"X-User-Id": str(self.user_b.id)},
        )
        self.assertEqual(res_b.status_code, 200)
        data_b = res_b.json()
        self.assertEqual(data_b["total"], 2)
        self.assertEqual(len(data_b["items"]), 2)
        order_codes_b = [o["order_code"] for o in data_b["items"]]
        self.assertIn("ORD-B1", order_codes_b)
        self.assertIn("ORD-B2", order_codes_b)
        self.assertNotIn("ORD-A1", order_codes_b)

    def test_customer_cannot_view_other_user_order_detail(self):
        """Khách hàng không thể xem chi tiết đơn hàng của người khác (trả về 404)."""
        order_a = self._create_sample_order(self.user_a.id, "ORD-A-SECRET", Decimal("850000.00"))

        # User A xem chi tiết đơn của chính mình -> Thành công 200 OK
        res_a = self.client.get(
            f"/api/customer/orders/{order_a.order_code}",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_a.status_code, 200)
        self.assertEqual(res_a.json()["order_code"], "ORD-A-SECRET")

        # User B cố tình truy cập chi tiết đơn của User A -> 404 Not Found
        res_b = self.client.get(
            f"/api/customer/orders/{order_a.order_code}",
            headers={"X-User-Id": str(self.user_b.id)},
        )
        self.assertEqual(res_b.status_code, 404)
        self.assertIn("không tìm thấy", res_b.json()["detail"].lower())

    def test_unauthenticated_request_rejected(self):
        """Người dùng không hợp lệ hoặc không tồn tại bị từ chối 401."""
        res = self.client.get(
            "/api/customer/orders",
            headers={"X-User-Id": "999999"},
        )
        self.assertEqual(res.status_code, 401)

    # =========================================================================
    # 2. TIÊU CHÍ: HỖ TRỢ XEM LIST/DETAIL VÀ PHÂN TRANG (Pagination)
    # =========================================================================

    def test_pagination_page_limit_and_navigation(self):
        """Kiểm tra phân trang: page, limit, total, total_pages, has_next, has_prev."""
        # Tạo 7 đơn hàng cho User A
        for i in range(1, 8):
            self._create_sample_order(
                self.user_a.id, f"ORD-PAG-{i:02d}", Decimal(f"{i * 100000}.00")
            )

        # 1. Trang 1 (limit=3): mong đợi 3 items, has_next=True, has_prev=False
        res_p1 = self.client.get(
            "/api/customer/orders?page=1&limit=3",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_p1.status_code, 200)
        d1 = res_p1.json()
        self.assertEqual(d1["total"], 7)
        self.assertEqual(d1["page"], 1)
        self.assertEqual(d1["limit"], 3)
        self.assertEqual(d1["total_pages"], 3)
        self.assertEqual(len(d1["items"]), 3)
        self.assertTrue(d1["has_next"])
        self.assertFalse(d1["has_prev"])

        # 2. Trang 2 (limit=3): mong đợi 3 items, has_next=True, has_prev=True
        res_p2 = self.client.get(
            "/api/customer/orders?page=2&limit=3",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_p2.status_code, 200)
        d2 = res_p2.json()
        self.assertEqual(d2["page"], 2)
        self.assertEqual(len(d2["items"]), 3)
        self.assertTrue(d2["has_next"])
        self.assertTrue(d2["has_prev"])

        # Đảm bảo dữ liệu trang 1 và trang 2 không bị trùng lặp
        codes_p1 = {item["order_code"] for item in d1["items"]}
        codes_p2 = {item["order_code"] for item in d2["items"]}
        self.assertTrue(codes_p1.isdisjoint(codes_p2))

        # 3. Trang 3 (limit=3): mong đợi 1 item cuối cùng, has_next=False, has_prev=True
        res_p3 = self.client.get(
            "/api/customer/orders?page=3&limit=3",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_p3.status_code, 200)
        d3 = res_p3.json()
        self.assertEqual(d3["page"], 3)
        self.assertEqual(len(d3["items"]), 1)
        self.assertFalse(d3["has_next"])
        self.assertTrue(d3["has_prev"])

        # 4. Trang 4 (vượt quá total_pages): mong đợi 0 items, has_next=False, has_prev=True
        res_p4 = self.client.get(
            "/api/customer/orders?page=4&limit=3",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_p4.status_code, 200)
        d4 = res_p4.json()
        self.assertEqual(len(d4["items"]), 0)
        self.assertFalse(d4["has_next"])
        self.assertTrue(d4["has_prev"])

    def test_pagination_page_size_alias(self):
        """Hỗ trợ alias page_size tương đương với limit."""
        for i in range(1, 5):
            self._create_sample_order(self.user_a.id, f"ORD-SZ-{i}", Decimal("100000.00"))

        res = self.client.get(
            "/api/customer/orders?page=1&page_size=2",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["limit"], 2)
        self.assertEqual(data["page_size"], 2)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["total_pages"], 2)

    def test_pagination_validation_reject_invalid_inputs(self):
        """Kiểm tra validation: page < 1 hoặc limit < 1 hoặc limit > 100 bị từ chối 422."""
        # page = 0
        r_page0 = self.client.get(
            "/api/customer/orders?page=0&limit=10",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(r_page0.status_code, 422)

        # limit = 0
        r_lim0 = self.client.get(
            "/api/customer/orders?page=1&limit=0",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(r_lim0.status_code, 422)

        # limit = 101 (> 100)
        r_lim101 = self.client.get(
            "/api/customer/orders?page=1&limit=101",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(r_lim101.status_code, 422)

    def test_filter_orders_by_status(self):
        """Lọc danh sách đơn hàng theo trạng thái (status)."""
        self._create_sample_order(self.user_a.id, "ORD-ST-1", Decimal("100000.00"), status=OrderStatus.PENDING.value)
        self._create_sample_order(self.user_a.id, "ORD-ST-2", Decimal("200000.00"), status=OrderStatus.CONFIRMED.value)
        self._create_sample_order(self.user_a.id, "ORD-ST-3", Decimal("300000.00"), status=OrderStatus.DELIVERED.value)

        # Lọc trạng thái PENDING
        res_pending = self.client.get(
            "/api/customer/orders?status=PENDING",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_pending.status_code, 200)
        d_pending = res_pending.json()
        self.assertEqual(d_pending["total"], 1)
        self.assertEqual(d_pending["items"][0]["order_code"], "ORD-ST-1")

        # Lọc trạng thái DELIVERED
        res_del = self.client.get(
            "/api/customer/orders?status=DELIVERED",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_del.status_code, 200)
        d_del = res_del.json()
        self.assertEqual(d_del["total"], 1)
        self.assertEqual(d_del["items"][0]["order_code"], "ORD-ST-3")

    def test_order_detail_view_success(self):
        """Xem chi tiết đơn hàng: trả về đầy đủ sản phẩm, giá, địa chỉ và thông tin thanh toán."""
        order = self._create_sample_order(
            user_id=self.user_a.id,
            order_code="ORD-DETAIL-001",
            total_price=Decimal("1700000.00"),
            status=OrderStatus.CONFIRMED.value,
            items_count=2,
            payment_method=PaymentMethod.VNPAY.value,
            payment_status=PaymentStatus.SUCCESS.value,
        )

        res = self.client.get(
            f"/api/customer/orders/{order.order_code}",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Kiểm tra thông tin đơn
        self.assertEqual(data["order_code"], "ORD-DETAIL-001")
        self.assertEqual(data["status"], OrderStatus.CONFIRMED.value)
        self.assertEqual(Decimal(str(data["total_price"])), Decimal("1700000.00"))
        self.assertEqual(data["shipping_address"], "Số 10 Nguyễn Trãi, Thanh Xuân, Hà Nội")
        self.assertEqual(data["total_items"], 2)
        self.assertEqual(len(data["items"]), 2)

        # Kiểm tra chi tiết mục sản phẩm
        item_0 = data["items"][0]
        self.assertEqual(item_0["product_name"], "Áo Đấu T1 CKTG 2026")
        self.assertEqual(item_0["sku"], "T1-JERSEY-2026-M")
        self.assertEqual(item_0["color"], "Black/Red")
        self.assertEqual(item_0["size"], "M")
        self.assertEqual(Decimal(str(item_0["unit_price"])), Decimal("850000.00"))
        self.assertEqual(item_0["quantity"], 1)
        self.assertEqual(Decimal(str(item_0["line_total"])), Decimal("850000.00"))

        # Kiểm tra chi tiết thanh toán
        self.assertIsNotNone(data["payment"])
        self.assertEqual(data["payment"]["method"], PaymentMethod.VNPAY.value)
        self.assertEqual(data["payment"]["status"], PaymentStatus.SUCCESS.value)
        self.assertEqual(Decimal(str(data["payment"]["amount"])), Decimal("1700000.00"))

    def test_order_detail_lookup_by_numeric_id(self):
        """Hỗ trợ xem chi tiết đơn hàng qua id số."""
        order = self._create_sample_order(self.user_a.id, "ORD-NUM-999", Decimal("500000.00"))

        res = self.client.get(
            f"/api/customer/orders/{order.id}",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["order_code"], "ORD-NUM-999")

    # =========================================================================
    # 3. TIÊU CHÍ: DỮ LIỆU TRẢ VỀ KHÔNG CHỨA THÔNG TIN NỘI BỘ
    # =========================================================================

    def test_response_data_does_not_contain_internal_info(self):
        """Đảm bảo tuyệt đối không trả về thông tin nhạy cảm hoặc nội bộ hệ thống."""
        # Tạo thêm 1 audit log nội bộ của webhook trong DB để kiểm tra rò rỉ
        webhook_log = PaymentWebhookLog(
            transaction_reference="REF-ORD-SEC-01",
            gateway="VNPAY",
            raw_payload='{"vnp_SecretHash": "super_secret_internal_key_abc123"}',
            is_valid_signature=True,
            response_code="00",
            message="Internal callback verified",
            ip_address="192.168.1.100",
        )
        self.db.add(webhook_log)
        self.db.commit()

        order = self._create_sample_order(
            self.user_a.id,
            "ORD-SEC-01",
            Decimal("850000.00"),
            payment_method=PaymentMethod.VNPAY.value,
            payment_status=PaymentStatus.SUCCESS.value,
        )

        # 1. Kiểm tra API danh sách (List endpoint)
        res_list = self.client.get(
            "/api/customer/orders",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_list.status_code, 200)
        raw_list_text = res_list.text

        # 2. Kiểm tra API chi tiết (Detail endpoint)
        res_detail = self.client.get(
            f"/api/customer/orders/{order.order_code}",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_detail.status_code, 200)
        raw_detail_text = res_detail.text

        # Danh sách các từ khóa / thông tin nhạy cảm nội bộ không được phép xuất hiện
        forbidden_keywords = [
            "password_hash",
            "secret_hash_faker_12345",
            "super_secret_internal_key_abc123",
            "raw_payload",
            "192.168.1.100",
            "is_valid_signature",
            "payment_webhook_logs",
            "admin_note",
            "internal_note",
            "cost_price",
        ]

        for kw in forbidden_keywords:
            self.assertNotIn(
                kw,
                raw_list_text,
                f"LỖI BẢO MẬT: Phát hiện thông tin nội bộ '{kw}' trong API danh sách!",
            )
            self.assertNotIn(
                kw,
                raw_detail_text,
                f"LỖI BẢM MẬT: Phát hiện thông tin nội bộ '{kw}' trong API chi tiết đơn hàng!",
            )

    # =========================================================================
    # 4. KIỂM TRA ROUTER PHỤ /orders/my VÀ ALIASES
    # =========================================================================

    def test_order_router_aliases(self):
        """Kiểm tra hoạt động của router phụ /orders/my."""
        self._create_sample_order(self.user_a.id, "ORD-ALIAS-1", Decimal("300000.00"))

        # Gọi qua /api/orders/my
        res_my = self.client.get(
            "/api/orders/my",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_my.status_code, 200)
        self.assertEqual(res_my.json()["total"], 1)

        # Gọi chi tiết qua /api/orders/my/ORD-ALIAS-1
        res_my_detail = self.client.get(
            "/api/orders/my/ORD-ALIAS-1",
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res_my_detail.status_code, 200)
        self.assertEqual(res_my_detail.json()["order_code"], "ORD-ALIAS-1")


if __name__ == "__main__":
    unittest.main()
