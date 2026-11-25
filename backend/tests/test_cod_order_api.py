"""Bộ kiểm thử cho API Tạo đơn hàng COD, kiểm tra tồn kho và lưu trong Transaction.
Kiểm tra toàn diện tất cả các tiêu chí chấp nhận:
1. COD tạo đơn khi cart hợp lệ (giỏ hàng có sản phẩm, địa chỉ giao hàng hợp lệ).
2. GIÁ VÀ TỒN KHO ĐƯỢC KIỂM TRA LẠI Ở SERVER:
   - Server tự fetch giá mới nhất từ Product trong DB, không tin giá cũ hay giá client.
   - Server kiểm tra tồn kho: Nếu số lượng đặt > tồn kho hiện tại -> từ chối 400.
3. TRANSACTION NGUYÊN TỬ (Tất cả nằm trong 1 Transaction):
   - Tạo Order, OrderItems, trừ tồn kho variant, tạo Payment COD (PENDING) và xoá giỏ hàng.
   - Nếu có bất kỳ lỗi nào xảy ra: Rollback toàn bộ, tồn kho không bị trừ, giỏ hàng giữ nguyên, không tạo đơn rác.
4. User chỉ xem được đơn hàng của chính mình (User Isolation).
"""
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.tokens import create_access_token
from app.db.session import Base, get_db
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.models.variant import ProductVariant
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.voucher import DiscountType, Voucher, VoucherStatus
from app.models.wishlist import Wishlist  # noqa: F401
from app.routers.order import router as order_router


class TestCODOrderAPIs(unittest.TestCase):
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

        # 1. Tạo 2 User: Faker (User A) và Oner (User B)
        self.user_a = User(
            full_name="Faker (User A)",
            email="faker@t1.gg",
            password_hash="pw_a",
            role="CUSTOMER",
            status="Active",
        )
        self.user_b = User(
            full_name="Oner (User B)",
            email="oner@t1.gg",
            password_hash="pw_b",
            role="CUSTOMER",
            status="Active",
        )
        self.category = Category(name="Áo Đấu T1", slug="ao-dau-t1", status="Active")
        self.db.add_all([self.user_a, self.user_b, self.category])
        self.db.flush()

        # 2. Tạo Product và 2 Variant với số lượng tồn kho cụ thể
        self.product = Product(
            category_id=self.category.id,
            name="Áo Đấu T1 CKTG 2026",
            slug="ao-dau-t1-cktg-2026",
            price=Decimal("800000.00"),
            stock=20,
            status="Published",
        )
        self.db.add(self.product)
        self.db.flush()

        # Variant M: Tồn kho = 10
        self.variant_m = ProductVariant(
            product_id=self.product.id,
            sku="T1-JERSEY-M",
            color="Red",
            size="M",
            stock=10,
        )
        # Variant L: Tồn kho = 3
        self.variant_l = ProductVariant(
            product_id=self.product.id,
            sku="T1-JERSEY-L",
            color="Red",
            size="L",
            stock=3,
        )
        self.db.add_all([self.variant_m, self.variant_l])

        # 3. Tạo Cart cho User A và User B
        self.cart_a = Cart(user_id=self.user_a.id, status="Active")
        self.cart_b = Cart(user_id=self.user_b.id, status="Active")
        self.db.add_all([self.cart_a, self.cart_b])

        # 4. Tạo Voucher giảm 10%
        now = datetime.now()
        self.voucher = Voucher(
            code="SALE10",
            name="Giảm 10%",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("10.00"),
            min_order_amount=Decimal("500000.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=10),
            usage_limit=10,
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(self.voucher)
        self.db.commit()

        # Khởi tạo FastAPI App gắn order router
        self.app = FastAPI()
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

    def _auth_headers(self, user: User) -> dict[str, str]:
        token, _ = create_access_token(user)
        return {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.JWT_SECRET_KEY = self._orig_secret

    # -------------------------------------------------------------
    # 1. TIÊU CHÍ: COD tạo đơn khi cart hợp lệ
    # -------------------------------------------------------------
    def test_create_cod_order_success(self):
        """Tạo đơn hàng COD thành công khi giỏ hàng có sản phẩm và địa chỉ hợp lệ."""
        # Thêm 2 áo Size M (800k x 2 = 1.6tr) vào giỏ hàng của User A
        item = CartItem(cart_id=self.cart_a.id, variant_id=self.variant_m.id, quantity=2)
        self.db.add(item)
        self.db.commit()

        initial_stock = self.variant_m.stock  # 10

        payload = {
            "shipping_address": "Số 1 Đại Cồ Việt, Hai Bà Trưng, Hà Nội",
            "note": "Giao giờ hành chính",
        }
        response = self.client.post(
            "/api/orders/cod",
            json=payload,
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["message"], "Tạo đơn hàng COD thành công.")
        order_info = data["order"]

        # Kiểm tra Order
        self.assertTrue(order_info["order_code"].startswith("COD-"))
        self.assertEqual(order_info["customer_id"], self.user_a.id)
        self.assertEqual(Decimal(str(order_info["total_price"])), Decimal("1600000.00"))
        self.assertEqual(order_info["shipping_address"], payload["shipping_address"])
        self.assertEqual(order_info["status"], OrderStatus.PENDING.value)

        # Kiểm tra OrderItems (Snapshot giá & số lượng)
        self.assertEqual(len(order_info["items"]), 1)
        item_resp = order_info["items"][0]
        self.assertEqual(item_resp["variant_id"], self.variant_m.id)
        self.assertEqual(item_resp["sku"], "T1-JERSEY-M")
        self.assertEqual(item_resp["quantity"], 2)
        self.assertEqual(Decimal(str(item_resp["unit_price"])), Decimal("800000.00"))
        self.assertEqual(Decimal(str(item_resp["line_total"])), Decimal("1600000.00"))

        # Kiểm tra Payment COD được tạo kèm
        payment_info = order_info["payment"]
        self.assertIsNotNone(payment_info)
        self.assertEqual(payment_info["method"], PaymentMethod.COD.value)
        self.assertEqual(Decimal(str(payment_info["amount"])), Decimal("1600000.00"))
        self.assertEqual(payment_info["status"], PaymentStatus.PENDING.value)

        # KIỂM TRA DATABASE: Tồn kho đã bị trừ (10 - 2 = 8)
        self.db.expire_all()
        variant_db = self.db.get(ProductVariant, self.variant_m.id)
        self.assertEqual(variant_db.stock, initial_stock - 2)

        # KIỂM TRA DATABASE: Giỏ hàng của User A đã được dọn sạch
        cart_db = self.db.get(Cart, self.cart_a.id)
        self.assertEqual(len(cart_db.items), 0)

    def test_reject_empty_cart(self):
        """Giỏ hàng trống -> từ chối tạo đơn (400 Bad Request)."""
        payload = {"shipping_address": "Số 1 Đại Cồ Việt, Hà Nội"}
        response = self.client.post(
            "/api/orders/cod",
            json=payload,
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("giỏ hàng trống", response.json()["detail"].lower())

    def test_reject_empty_shipping_address(self):
        """Địa chỉ giao hàng trống hoặc quá ngắn -> từ chối (400/422)."""
        # Thêm sản phẩm vào giỏ
        item = CartItem(cart_id=self.cart_a.id, variant_id=self.variant_m.id, quantity=1)
        self.db.add(item)
        self.db.commit()

        # Địa chỉ trống
        res_empty = self.client.post(
            "/api/orders/cod",
            json={"shipping_address": "   "},
            headers=self._auth_headers(self.user_a),
        )
        self.assertIn(res_empty.status_code, [400, 422])

        # Địa chỉ quá ngắn (< 5 ký tự)
        res_short = self.client.post(
            "/api/orders/cod",
            json={"shipping_address": "HN"},
            headers=self._auth_headers(self.user_a),
        )
        self.assertIn(res_short.status_code, [400, 422])

    # -------------------------------------------------------------
    # 2. TIÊU CHÍ: Giá và tồn kho được kiểm tra lại ở server
    # -------------------------------------------------------------
    def test_server_rechecks_stock_insufficient(self):
        """Tồn kho không đủ (kho còn 3, giỏ hàng đòi mua 5) -> từ chối 400 và không trừ kho."""
        # Variant L chỉ có tồn kho = 3
        item = CartItem(cart_id=self.cart_a.id, variant_id=self.variant_l.id, quantity=5)
        self.db.add(item)
        self.db.commit()

        initial_stock = self.variant_l.stock  # 3

        payload = {"shipping_address": "Số 10 Nguyễn Trãi, Thanh Xuân, Hà Nội"}
        response = self.client.post(
            "/api/orders/cod",
            json=payload,
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("không đủ số lượng tồn kho", response.json()["detail"].lower())

        # TRANSACTION ROLLBACK: Tồn kho không bị trừ, giỏ hàng giữ nguyên
        self.db.expire_all()
        variant_db = self.db.get(ProductVariant, self.variant_l.id)
        self.assertEqual(variant_db.stock, initial_stock)

        cart_db = self.db.get(Cart, self.cart_a.id)
        self.assertEqual(len(cart_db.items), 1)

        # Không có order nào được tạo
        orders_db = self.db.scalars(select(Order)).all()
        self.assertEqual(len(orders_db), 0)

    def test_server_rechecks_price_fresh_from_db(self):
        """Server lấy giá gốc mới nhất từ DB tại thời điểm đặt đơn, không dùng giá cũ."""
        # User A có áo Size M trong giỏ hàng
        item = CartItem(cart_id=self.cart_a.id, variant_id=self.variant_m.id, quantity=1)
        self.db.add(item)
        self.db.commit()

        # Admin tăng giá sản phẩm từ 800.000 lên 950.000 trong DB
        self.product.price = Decimal("950000.00")
        self.db.commit()

        payload = {"shipping_address": "Số 10 Nguyễn Trãi, Thanh Xuân, Hà Nội"}
        response = self.client.post(
            "/api/orders/cod",
            json=payload,
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()["order"]

        # Giá snapshot trong đơn phải là giá mới 950.000đ do server tự nạp từ DB
        self.assertEqual(Decimal(str(data["total_price"])), Decimal("950000.00"))
        self.assertEqual(Decimal(str(data["items"][0]["unit_price"])), Decimal("950000.00"))

    # -------------------------------------------------------------
    # 3. TIÊU CHÍ: Order/OrderItems và giữ/trừ kho nằm trong transaction
    # -------------------------------------------------------------
    def test_transaction_atomicity_with_multiple_items(self):
        """Nhiều sản phẩm trong giỏ: Nếu 1 sản phẩm bị thiếu kho -> Toàn bộ transaction bị rollback."""
        # Item 1: Size M (còn 10, mua 2) -> hợp lệ
        # Item 2: Size L (còn 3, mua 10) -> thiếu kho!
        item1 = CartItem(cart_id=self.cart_a.id, variant_id=self.variant_m.id, quantity=2)
        item2 = CartItem(cart_id=self.cart_a.id, variant_id=self.variant_l.id, quantity=10)
        self.db.add_all([item1, item2])
        self.db.commit()

        stock_m_before = self.variant_m.stock  # 10
        stock_l_before = self.variant_l.stock  # 3

        payload = {"shipping_address": "Số 10 Nguyễn Trãi, Thanh Xuân, Hà Nội"}
        response = self.client.post(
            "/api/orders/cod",
            json=payload,
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(response.status_code, 400)

        # Kiểm tra tính nguyên tử của Transaction: Tồn kho Item 1 cũng KHÔNG bị trừ
        self.db.expire_all()
        self.assertEqual(self.db.get(ProductVariant, self.variant_m.id).stock, stock_m_before)
        self.assertEqual(self.db.get(ProductVariant, self.variant_l.id).stock, stock_l_before)

        # Giỏ hàng giữ nguyên 2 items
        self.assertEqual(len(self.db.get(Cart, self.cart_a.id).items), 2)
        # Không có order và payment nào được tạo
        self.assertEqual(len(self.db.scalars(select(Order)).all()), 0)
        self.assertEqual(len(self.db.scalars(select(Payment)).all()), 0)

    # -------------------------------------------------------------
    # 4. TIÊU CHÍ: Áp dụng Voucher khi tạo đơn COD
    # -------------------------------------------------------------
    def test_create_cod_order_with_valid_voucher(self):
        """Tạo đơn COD có áp dụng mã voucher SALE10 (giảm 10%)."""
        # Mua 1 áo Size M (800k)
        item = CartItem(cart_id=self.cart_a.id, variant_id=self.variant_m.id, quantity=1)
        self.db.add(item)
        self.db.commit()

        payload = {
            "shipping_address": "Số 10 Nguyễn Trãi, Thanh Xuân, Hà Nội",
            "voucher_code": "SALE10",
        }
        response = self.client.post(
            "/api/orders/cod",
            json=payload,
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()["order"]

        # Tổng tiền: 800.000 - 10% (80.000) = 720.000đ
        self.assertEqual(Decimal(str(data["total_price"])), Decimal("720000.00"))
        self.assertEqual(Decimal(str(data["payment"]["amount"])), Decimal("720000.00"))

        # Kiểm tra số lượt dùng voucher tăng thêm 1
        self.db.expire_all()
        voucher_db = self.db.get(Voucher, self.voucher.id)
        self.assertEqual(voucher_db.used_count, 1)

    # -------------------------------------------------------------
    # 5. TIÊU CHÍ: Quyền riêng tư người dùng (User Isolation)
    # -------------------------------------------------------------
    def test_user_can_only_view_own_orders(self):
        """User B không thể xem danh sách đơn hàng của User A."""
        # User A tạo 1 đơn hàng
        item = CartItem(cart_id=self.cart_a.id, variant_id=self.variant_m.id, quantity=1)
        self.db.add(item)
        self.db.commit()

        res_create = self.client.post(
            "/api/orders/cod",
            json={"shipping_address": "Địa chỉ User A tại Hà Nội"},
            headers=self._auth_headers(self.user_a),
        )
        self.assertEqual(res_create.status_code, 201)
        order_code = res_create.json()["order"]["order_code"]

        # User A xem danh sách -> có 1 đơn
        res_list_a = self.client.get("/api/orders", headers=self._auth_headers(self.user_a))
        self.assertEqual(len(res_list_a.json()), 1)

        # User B xem danh sách -> trống (0 đơn)
        res_list_b = self.client.get("/api/orders", headers=self._auth_headers(self.user_b))
        self.assertEqual(len(res_list_b.json()), 0)

        # User B cố tình truy cập chi tiết đơn của User A -> 404 Not Found
        res_detail_b = self.client.get(
            f"/api/orders/{order_code}",
            headers=self._auth_headers(self.user_b),
        )
        self.assertEqual(res_detail_b.status_code, 404)


if __name__ == "__main__":
    unittest.main()

