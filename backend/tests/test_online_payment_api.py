"""Bộ kiểm thử cho API Tạo yêu cầu thanh toán online và xử lý kết quả khởi tạo.
Kiểm tra tất cả các tiêu chí chấp nhận:
1. Online checkout tạo giao dịch và URL/token theo gateway cấu hình (VNPAY, MOMO, ZALOPAY...).
2. KHÔNG ĐÁNH DẤU PAID TRƯỚC CALLBACK HỢP LỆ:
   - Khi vừa khởi tạo: payment.status và order.status luôn là PENDING.
   - Chỉ khi callback hợp lệ (code='00') mới chuyển sang SUCCESS/CONFIRMED.
3. XỬ LÝ ĐẦY ĐỦ CÁC LỖI KHỞI TẠO:
   - Đơn hàng không tồn tại -> 404 Not Found.
   - User không phải chủ sở hữu đơn hàng -> 403 Forbidden.
   - Đơn hàng đã thanh toán thành công -> 400 Bad Request.
   - Đơn hàng đã bị huỷ -> 400 Bad Request.
   - Cổng thanh toán không hỗ trợ / không hợp lệ -> 400 Bad Request.
4. Hỗ trợ retry tăng attempt_number khi thanh toán lại.
"""
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.models.category import Category  # noqa: F401
from app.models.product import Product  # noqa: F401
from app.models.user import User
from app.models.variant import ProductVariant  # noqa: F401
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem  # noqa: F401
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.voucher import Voucher  # noqa: F401
from app.models.wishlist import Wishlist  # noqa: F401
from app.routers.payment import router as payment_router
from app.services.payment_gateway import build_vnpay_signature


class TestOnlinePaymentAPIs(unittest.TestCase):
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

        # 1. Tạo 2 User
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
        self.db.add_all([self.user_a, self.user_b])
        self.db.flush()

        # 2. Tạo đơn hàng mẫu cho User A
        self.order_a = Order(
            order_code="ORD-20261120-FAKER01",
            customer_id=self.user_a.id,
            total_price=Decimal("1500000.00"),
            shipping_address="T1 HQ, Gangnam, Seoul",
            status=OrderStatus.PENDING.value,
        )
        self.db.add(self.order_a)
        self.db.commit()

        # Khởi tạo FastAPI App gắn payment router
        self.app = FastAPI()
        self.app.include_router(payment_router, prefix="/api")
        self.app.include_router(payment_router)

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
    # 1. TIÊU CHÍ: Online checkout tạo giao dịch và URL/token theo gateway cấu hình
    # -------------------------------------------------------------
    def test_online_checkout_vnpay_success(self):
        """Khởi tạo thanh toán VNPAY thành công: tạo giao dịch, URL và token chuẩn."""
        payload = {
            "order_code": self.order_a.order_code,
            "method": "VNPAY",
            "return_url": "https://t1shop.vn/payment-return",
        }
        response = self.client.post(
            "/api/payments/checkout",
            json=payload,
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()

        # Kiểm tra thông tin trả về
        self.assertEqual(data["order_code"], self.order_a.order_code)
        self.assertEqual(data["method"], "VNPAY")
        self.assertEqual(Decimal(str(data["amount"])), Decimal("1500000.00"))
        self.assertEqual(data["gateway_name"], "VNPAY")
        self.assertTrue(data["transaction_reference"].startswith("VNPAY-ORD"))

        # Kiểm tra URL thanh toán VNPAY
        self.assertIn("sandbox.vnpayment.vn", data["payment_url"])
        self.assertIn("vnp_Amount=150000000", data["payment_url"])  # 1.5tr * 100
        self.assertIn("vnp_SecureHash=", data["payment_url"])
        self.assertIn("vnp_TxnRef=", data["payment_url"])

        # Kiểm tra Token
        self.assertTrue(data["payment_token"].startswith("VNPAY-TOKEN-"))
        self.assertIsNotNone(data["expires_at"])

        # TIÊU CHÍ QUAN TRỌNG: Trạng thái khi vừa tạo PHẢI LÀ PENDING
        self.assertEqual(data["status"], PaymentStatus.PENDING.value)

        # KIỂM TRA DATABASE: Bản ghi Payment được lưu với trạng thái PENDING
        payment_db = self.db.get(Payment, data["payment_id"])
        self.assertIsNotNone(payment_db)
        self.assertEqual(payment_db.status, PaymentStatus.PENDING.value)
        self.assertEqual(payment_db.method, "VNPAY")

        # Đơn hàng vẫn giữ trạng thái PENDING (chưa bị đánh dấu paid)
        order_db = self.db.get(Order, self.order_a.id)
        self.assertEqual(order_db.status, OrderStatus.PENDING.value)

    def test_online_checkout_momo_success(self):
        """Khởi tạo thanh toán MoMo thành công: sinh URL và token của MoMo."""
        payload = {
            "order_code": self.order_a.order_code,
            "method": "MOMO",
        }
        response = self.client.post(
            "/api/payments/checkout",
            json=payload,
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()

        self.assertEqual(data["method"], "MOMO")
        self.assertIn("test-payment.momo.vn", data["payment_url"])
        self.assertIn("signature=", data["payment_url"])
        self.assertTrue(data["payment_token"].startswith("MOMO-TOKEN-"))
        self.assertEqual(data["status"], PaymentStatus.PENDING.value)

    def test_online_checkout_zalopay_success(self):
        """Khởi tạo thanh toán ZaloPay thành công: sinh URL và token của ZaloPay."""
        payload = {
            "order_code": self.order_a.order_code,
            "method": "ZALOPAY",
        }
        response = self.client.post(
            "/api/payments/checkout",
            json=payload,
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()

        self.assertEqual(data["method"], "ZALOPAY")
        self.assertIn("sb-openapi.zalopay.vn", data["payment_url"])
        self.assertIn("mac=", data["payment_url"])
        self.assertTrue(data["payment_token"].startswith("ZALO-TOKEN-"))
        self.assertEqual(data["status"], PaymentStatus.PENDING.value)

    # -------------------------------------------------------------
    # 2. TIÊU CHÍ: Không đánh dấu paid trước callback hợp lệ
    # -------------------------------------------------------------
    def test_not_marked_paid_before_valid_callback(self):
        """Khởi tạo xong: Payment và Order KHÔNG ĐƯỢC đánh dấu PAID."""
        payload = {
            "order_code": self.order_a.order_code,
            "method": "VNPAY",
        }
        res_init = self.client.post(
            "/api/payments/checkout",
            json=payload,
            headers={"X-User-Id": str(self.user_a.id)},
        )
        txn_ref = res_init.json()["transaction_reference"]

        # Kiểm tra trạng thái giao dịch vẫn là PENDING
        res_status = self.client.get(f"/api/payments/transaction/{txn_ref}")
        self.assertEqual(res_status.json()["status"], PaymentStatus.PENDING.value)

        # Kiểm tra đơn hàng trong DB vẫn là PENDING
        self.db.expire_all()
        order_db = self.db.get(Order, self.order_a.id)
        self.assertEqual(order_db.status, OrderStatus.PENDING.value)

    def test_callback_valid_marks_paid_and_confirms_order(self):
        """Chỉ khi nhận callback hợp lệ từ gateway (code='00') mới cập nhật SUCCESS và CONFIRMED."""
        # 1. Khởi tạo
        res_init = self.client.post(
            "/api/payments/checkout",
            json={"order_code": self.order_a.order_code, "method": "VNPAY"},
            headers={"X-User-Id": str(self.user_a.id)},
        )
        txn_ref = res_init.json()["transaction_reference"]

        # 2. Gửi callback thành công (response_code="00")
        vnp_params = {"vnp_Amount": "150000000", "vnp_ResponseCode": "00", "vnp_TxnRef": txn_ref}
        sig = build_vnpay_signature(vnp_params)
        callback_payload = {
            "transaction_reference": txn_ref,
            "method": "VNPAY",
            "response_code": "00",
            "secure_hash": sig,
            "extra_params": vnp_params,
        }
        res_cb = self.client.post("/api/payments/callback", json=callback_payload)
        self.assertEqual(res_cb.status_code, 200)
        self.assertTrue(res_cb.json()["success"])
        self.assertEqual(res_cb.json()["payment_status"], PaymentStatus.SUCCESS.value)
        self.assertEqual(res_cb.json()["order_status"], OrderStatus.CONFIRMED.value)

        # 3. Kiểm tra DB: Payment đã thành SUCCESS và Order đã thành CONFIRMED
        self.db.expire_all()
        payment_db = self.db.scalar(select(Payment).where(Payment.transaction_reference == txn_ref))
        self.assertEqual(payment_db.status, PaymentStatus.SUCCESS.value)
        self.assertEqual(payment_db.order.status, OrderStatus.CONFIRMED.value)

    def test_callback_failed_does_not_mark_paid(self):
        """Gateway callback báo thất bại (code!='00') -> Payment là FAILED, Order không chuyển CONFIRMED."""
        res_init = self.client.post(
            "/api/payments/checkout",
            json={"order_code": self.order_a.order_code, "method": "VNPAY"},
            headers={"X-User-Id": str(self.user_a.id)},
        )
        txn_ref = res_init.json()["transaction_reference"]

        # Gửi callback thất bại (mã lỗi '24': khách huỷ giao dịch)
        vnp_params = {"vnp_Amount": "150000000", "vnp_ResponseCode": "24", "vnp_TxnRef": txn_ref}
        sig = build_vnpay_signature(vnp_params)
        callback_payload = {
            "transaction_reference": txn_ref,
            "method": "VNPAY",
            "response_code": "24",
            "secure_hash": sig,
            "extra_params": vnp_params,
        }
        res_cb = self.client.post("/api/payments/callback", json=callback_payload)
        self.assertEqual(res_cb.status_code, 200)
        self.assertFalse(res_cb.json()["success"])
        self.assertEqual(res_cb.json()["payment_status"], PaymentStatus.FAILED.value)

        # Kiểm tra DB
        self.db.expire_all()
        payment_db = self.db.scalar(select(Payment).where(Payment.transaction_reference == txn_ref))
        self.assertEqual(payment_db.status, PaymentStatus.FAILED.value)
        self.assertEqual(payment_db.order.status, OrderStatus.PENDING.value)

    # -------------------------------------------------------------
    # 3. TIÊU CHÍ: Xử lý triệt để các lỗi khởi tạo
    # -------------------------------------------------------------
    def test_error_order_not_found(self):
        """Mã đơn hàng không tồn tại -> 404 Not Found."""
        payload = {"order_code": "ORD-NOT-EXIST-9999", "method": "VNPAY"}
        response = self.client.post(
            "/api/payments/checkout",
            json=payload,
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("không tìm thấy đơn hàng", response.json()["detail"].lower())

    def test_error_unauthorized_user(self):
        """User B cố tình thanh toán đơn hàng của User A -> 403 Forbidden."""
        payload = {"order_code": self.order_a.order_code, "method": "VNPAY"}
        response = self.client.post(
            "/api/payments/checkout",
            json=payload,
            headers={"X-User-Id": str(self.user_b.id)},  # User B
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("không có quyền", response.json()["detail"].lower())

    def test_error_order_already_paid(self):
        """Đơn hàng đã được thanh toán thành công -> từ chối 400."""
        # Đánh dấu đơn hàng đã thanh toán thành công
        self.order_a.status = OrderStatus.CONFIRMED.value
        self.db.commit()

        payload = {"order_code": self.order_a.order_code, "method": "VNPAY"}
        response = self.client.post(
            "/api/payments/checkout",
            json=payload,
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("đã được thanh toán", response.json()["detail"].lower())

    def test_error_order_cancelled(self):
        """Đơn hàng đã bị huỷ -> từ chối 400."""
        self.order_a.status = OrderStatus.CANCELLED.value
        self.db.commit()

        payload = {"order_code": self.order_a.order_code, "method": "VNPAY"}
        response = self.client.post(
            "/api/payments/checkout",
            json=payload,
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("đã bị huỷ", response.json()["detail"].lower())

    def test_error_unsupported_gateway_method(self):
        """Cổng thanh toán không hỗ trợ (ví dụ BITCOIN hoặc COD) -> từ chối 400."""
        payload = {"order_code": self.order_a.order_code, "method": "BITCOIN"}
        response = self.client.post(
            "/api/payments/checkout",
            json=payload,
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("không được hỗ trợ", response.json()["detail"].lower())

    # -------------------------------------------------------------
    # 4. TIÊU CHÍ: Hỗ trợ lần thử tiếp theo (Retry Attempt)
    # -------------------------------------------------------------
    def test_retry_checkout_increments_attempt_number(self):
        """Thanh toán lại cho cùng 1 đơn hàng -> attempt_number tự động tăng."""
        # Lần 1: Khởi tạo với VNPAY
        res1 = self.client.post(
            "/api/payments/checkout",
            json={"order_code": self.order_a.order_code, "method": "VNPAY"},
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res1.status_code, 201)
        self.assertEqual(res1.json()["attempt_number"], 1)

        # Lần 2: Thử lại với MOMO
        res2 = self.client.post(
            "/api/payments/checkout",
            json={"order_code": self.order_a.order_code, "method": "MOMO"},
            headers={"X-User-Id": str(self.user_a.id)},
        )
        self.assertEqual(res2.status_code, 201)
        self.assertEqual(res2.json()["attempt_number"], 2)
        self.assertNotEqual(res1.json()["transaction_reference"], res2.json()["transaction_reference"])


if __name__ == "__main__":
    unittest.main()

