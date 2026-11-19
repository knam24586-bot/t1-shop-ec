"""Bộ kiểm thử cho Voucher API: Kiểm tra mã, thời hạn, điều kiện và mức giảm.
Kiểm tra tất cả các tiêu chí chấp nhận:
1. Voucher hợp lệ trả mức giảm và tổng sau giảm chính xác (cả FIXED_AMOUNT và PERCENTAGE).
2. Mã hết hạn / sai điều kiện bị từ chối (400 Bad Request / 404 Not Found):
   - Mã không tồn tại -> 404.
   - Mã đã hết hạn (valid_to < now) -> 400.
   - Mã chưa có hiệu lực (valid_from > now) -> 400.
   - Mã bị tạm ngưng (status = INACTIVE) -> 400.
   - Mã hết lượt dùng (used_count >= usage_limit hoặc DEPLETED) -> 400.
   - Đơn hàng chưa đạt giá trị tối thiểu (order_amount < min_order_amount) -> 400.
3. KHÔNG TIN SỐ TIỀN GIẢM TỪ CLIENT:
   - Client cố tình gửi số tiền giảm giả mạo (client_discount / discount_amount) -> Server hoàn toàn tự tính lại từ DB.
4. Hỗ trợ các endpoint alias (/check, /validate, /apply).
"""
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.models.category import Category  # noqa: F401
from app.models.product import Product  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.variant import ProductVariant  # noqa: F401
from app.models.order import Order  # noqa: F401
from app.models.order_item import OrderItem  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.wishlist import Wishlist  # noqa: F401
from app.models.voucher import DiscountType, Voucher, VoucherStatus
from app.routers.voucher import router as voucher_router


class TestVoucherAPIs(unittest.TestCase):
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

        self.now = datetime.now()

        # 1. Voucher giảm phần trăm hợp lệ (15%, đơn tối thiểu 200k, không max cap)
        self.voucher_percent = Voucher(
            code="PERCENT15",
            name="Giảm 15% mùa hè",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("15.00"),
            min_order_amount=Decimal("200000.00"),
            valid_from=self.now - timedelta(days=2),
            valid_to=self.now + timedelta(days=10),
            usage_limit=100,
            status=VoucherStatus.ACTIVE.value,
        )

        # 2. Voucher giảm phần trăm có chặn trần (20% tối đa 100k, đơn tối thiểu 300k)
        self.voucher_capped = Voucher(
            code="CAPPED20",
            name="Giảm 20% tối đa 100k",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("20.00"),
            max_discount_amount=Decimal("100000.00"),
            min_order_amount=Decimal("300000.00"),
            valid_from=self.now - timedelta(days=2),
            valid_to=self.now + timedelta(days=10),
            usage_limit=50,
            status=VoucherStatus.ACTIVE.value,
        )

        # 3. Voucher giảm số tiền cố định (Giảm 50k, đơn tối thiểu 150k)
        self.voucher_fixed = Voucher(
            code="FIXED50K",
            name="Giảm 50.000đ",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("50000.00"),
            min_order_amount=Decimal("150000.00"),
            valid_from=self.now - timedelta(days=2),
            valid_to=self.now + timedelta(days=10),
            usage_limit=200,
            status=VoucherStatus.ACTIVE.value,
        )

        # 4. Voucher đã hết hạn sử dụng
        self.voucher_expired = Voucher(
            code="EXPIREDVOUCHER",
            name="Voucher đã hết hạn",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("30000.00"),
            min_order_amount=Decimal("100000.00"),
            valid_from=self.now - timedelta(days=30),
            valid_to=self.now - timedelta(days=1),
            status=VoucherStatus.ACTIVE.value,
        )

        # 5. Voucher chưa đến ngày hiệu lực
        self.voucher_future = Voucher(
            code="FUTUREVOUCHER",
            name="Voucher tương lai",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("50000.00"),
            min_order_amount=Decimal("100000.00"),
            valid_from=self.now + timedelta(days=5),
            valid_to=self.now + timedelta(days=15),
            status=VoucherStatus.ACTIVE.value,
        )

        # 6. Voucher bị vô hiệu hoá bởi admin
        self.voucher_inactive = Voucher(
            code="INACTIVEVOUCHER",
            name="Voucher tạm ngưng",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("20000.00"),
            min_order_amount=Decimal("0.00"),
            valid_from=self.now - timedelta(days=1),
            valid_to=self.now + timedelta(days=10),
            status=VoucherStatus.INACTIVE.value,
        )

        # 7. Voucher đã dùng hết số lượt (status=ACTIVE nhưng used_count >= usage_limit)
        self.voucher_depleted = Voucher(
            code="DEPLETEDVOUCHER",
            name="Voucher hết lượt",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("40000.00"),
            min_order_amount=Decimal("0.00"),
            valid_from=self.now - timedelta(days=1),
            valid_to=self.now + timedelta(days=10),
            usage_limit=10,
            used_count=10,
            status=VoucherStatus.ACTIVE.value,
        )

        self.db.add_all([
            self.voucher_percent,
            self.voucher_capped,
            self.voucher_fixed,
            self.voucher_expired,
            self.voucher_future,
            self.voucher_inactive,
            self.voucher_depleted,
        ])
        self.db.commit()

        # Tạo FastAPI app gắn voucher router
        self.app = FastAPI()
        self.app.include_router(voucher_router, prefix="/api")
        self.app.include_router(voucher_router)

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

    # -------------------------------------------------------------
    # 1. TIÊU CHÍ: Voucher hợp lệ trả mức giảm và tổng sau giảm
    # -------------------------------------------------------------
    def test_valid_voucher_fixed_amount(self):
        """Voucher FIXED_AMOUNT: Giảm 50.000đ cho đơn 500.000đ -> giảm 50.000đ, còn 450.000đ."""
        payload = {"code": "FIXED50K", "order_amount": 500000}
        response = self.client.post("/api/vouchers/check", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["code"], "FIXED50K")
        self.assertEqual(data["discount_type"], "FIXED_AMOUNT")
        self.assertEqual(Decimal(str(data["original_amount"])), Decimal("500000.00"))
        self.assertEqual(Decimal(str(data["discount_amount"])), Decimal("500000.00") - Decimal("450000.00"))
        self.assertEqual(Decimal(str(data["final_amount"])), Decimal("450000.00"))

    def test_valid_voucher_percentage(self):
        """Voucher PERCENTAGE: Giảm 15% cho đơn 1.000.000đ -> giảm 150.000đ, còn 850.000đ."""
        payload = {"code": "PERCENT15", "order_amount": 1000000}
        response = self.client.post("/api/vouchers/check", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["valid"])
        self.assertEqual(Decimal(str(data["discount_amount"])), Decimal("150000.00"))
        self.assertEqual(Decimal(str(data["final_amount"])), Decimal("850000.00"))

    def test_valid_voucher_percentage_with_max_cap(self):
        """Voucher PERCENTAGE có chặn trần: 20% của 1.000.000đ = 200k, nhưng trần là 100k -> giảm 100.000đ, còn 900.000đ."""
        payload = {"code": "CAPPED20", "order_amount": 1000000}
        response = self.client.post("/api/vouchers/check", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(Decimal(str(data["discount_amount"])), Decimal("100000.00"))
        self.assertEqual(Decimal(str(data["final_amount"])), Decimal("900000.00"))

    def test_case_insensitive_code(self):
        """Code gửi chữ thường (fixed50k) vẫn tìm thấy và áp dụng bình thường."""
        payload = {"code": "fixed50k", "order_amount": 300000}
        response = self.client.post("/api/vouchers/check", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], "FIXED50K")

    # -------------------------------------------------------------
    # 2. TIÊU CHÍ: Không tin số tiền giảm từ client
    # -------------------------------------------------------------
    def test_do_not_trust_client_discount(self):
        """Client cố tình gửi số tiền giảm giả mạo (client_discount=999999đ)
        -> Server PHẢI TỰ TÍNH LẠI (chỉ giảm đúng 15% = 30.000đ trên đơn 200.000đ).
        """
        payload = {
            "code": "PERCENT15",
            "order_amount": 200000,
            "client_discount": 999999,  # Cố tình gian lận số tiền giảm
        }
        response = self.client.post("/api/vouchers/check", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Mức giảm phải là 15% của 200.000 = 30.000đ, tuyệt đối không lấy 999.999đ của client
        self.assertEqual(Decimal(str(data["discount_amount"])), Decimal("30000.00"))
        self.assertEqual(Decimal(str(data["final_amount"])), Decimal("170000.00"))

    # -------------------------------------------------------------
    # 3. TIÊU CHÍ: Mã hết hạn / sai điều kiện bị từ chối
    # -------------------------------------------------------------
    def test_reject_expired_voucher(self):
        """Voucher đã hết hạn -> 400 Bad Request kèm thông báo chi tiết."""
        payload = {"code": "EXPIREDVOUCHER", "order_amount": 500000}
        response = self.client.post("/api/vouchers/check", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("hết hạn", response.json()["detail"].lower())

    def test_reject_future_voucher(self):
        """Voucher chưa tới ngày bắt đầu -> 400 Bad Request."""
        payload = {"code": "FUTUREVOUCHER", "order_amount": 500000}
        response = self.client.post("/api/vouchers/check", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("chưa có hiệu lực", response.json()["detail"].lower())

    def test_reject_inactive_voucher(self):
        """Voucher bị INACTIVE -> 400 Bad Request."""
        payload = {"code": "INACTIVEVOUCHER", "order_amount": 500000}
        response = self.client.post("/api/vouchers/check", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("INACTIVE", response.json()["detail"])

    def test_reject_depleted_voucher(self):
        """Voucher đã hết số lượt dùng -> 400 Bad Request."""
        payload = {"code": "DEPLETEDVOUCHER", "order_amount": 500000}
        response = self.client.post("/api/vouchers/check", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("hết lượt sử dụng", response.json()["detail"].lower())

    def test_reject_below_min_order_amount(self):
        """Đơn hàng 100.000đ chưa đạt min_order_amount (200.000đ) -> 400 Bad Request."""
        payload = {"code": "PERCENT15", "order_amount": 100000}
        response = self.client.post("/api/vouchers/check", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("chưa đạt giá trị tối thiểu", response.json()["detail"].lower())

    def test_reject_nonexistent_voucher(self):
        """Mã voucher không tồn tại trong hệ thống -> 404 Not Found."""
        payload = {"code": "DOESNOTEXIST999", "order_amount": 500000}
        response = self.client.post("/api/vouchers/check", json=payload)
        self.assertEqual(response.status_code, 404)
        self.assertIn("không tồn tại", response.json()["detail"].lower())

    # -------------------------------------------------------------
    # 4. TIÊU CHÍ: Các endpoint alias và GET
    # -------------------------------------------------------------
    def test_alias_endpoints(self):
        """Endpoint /validate và /apply hoạt động như /check."""
        payload = {"code": "FIXED50K", "order_amount": 200000}
        res_val = self.client.post("/api/vouchers/validate", json=payload)
        self.assertEqual(res_val.status_code, 200)
        self.assertEqual(Decimal(str(res_val.json()["final_amount"])), Decimal("150000.00"))

        res_app = self.client.post("/api/vouchers/apply", json=payload)
        self.assertEqual(res_app.status_code, 200)
        self.assertEqual(Decimal(str(res_app.json()["final_amount"])), Decimal("150000.00"))

    def test_get_check_endpoint(self):
        """GET /vouchers/check qua query params."""
        response = self.client.get("/api/vouchers/check?code=FIXED50K&order_amount=200000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(str(response.json()["final_amount"])), Decimal("150000.00"))

    def test_list_active_vouchers(self):
        """GET /vouchers chỉ liệt kê các mã đang ACTIVE, chưa hết hạn, còn lượt dùng."""
        response = self.client.get("/api/vouchers")
        self.assertEqual(response.status_code, 200)
        codes = [v["code"] for v in response.json()]
        self.assertIn("PERCENT15", codes)
        self.assertIn("CAPPED20", codes)
        self.assertIn("FIXED50K", codes)
        self.assertNotIn("EXPIREDVOUCHER", codes)
        self.assertNotIn("FUTUREVOUCHER", codes)
        self.assertNotIn("INACTIVEVOUCHER", codes)
        self.assertNotIn("DEPLETEDVOUCHER", codes)


if __name__ == "__main__":
    unittest.main()
