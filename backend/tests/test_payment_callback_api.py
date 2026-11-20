"""Bộ kiểm thử cho Webhook / Callback thanh toán an toàn.
Tiêu chí chấp nhận:
1. Webhook xác thực chữ ký/nguồn theo gateway:
   - VNPAY: xác thực HMAC-SHA512 đúng chuẩn tham số vnp_*.
   - MoMo: xác thực HMAC-SHA256 chuẩn partnerCode, orderId, amount, resultCode...
   - ZaloPay: xác thực HMAC-SHA256 (app_id|app_trans_id|amount).
   - Sai chữ ký / giả mạo chữ ký -> từ chối với HTTP 400 Bad Request.
   - Cổng thanh toán (nguồn) không khớp với phương thức đã đăng ký -> từ chối HTTP 400.
2. Xử lý Idempotent (chống lặp):
   - Callback lặp nhiều lần với cùng transaction_reference không tạo thanh toán/đơn hàng trùng lặp.
   - Lần gọi đầu cập nhật SUCCESS / CONFIRMED; các lần sau trả về is_idempotent=True an toàn.
3. Lưu log kết quả:
   - Mọi lần gọi callback (thành công, thất bại, sai chữ ký, lặp lại) đều được lưu vào PaymentWebhookLog.
   - Cung cấp API truy vấn log đối soát theo transaction_reference.
"""
from __future__ import annotations

import unittest
from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
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
from app.models.payment_log import PaymentWebhookLog
from app.models.voucher import Voucher  # noqa: F401
from app.models.wishlist import Wishlist  # noqa: F401
from app.routers.payment import router as payment_router
from app.services.payment_gateway import (
    GatewayConfig,
    build_momo_signature,
    build_vnpay_signature,
    build_zalopay_signature,
)


class TestPaymentCallbackAPIs(unittest.TestCase):
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

        # 1. Tạo User
        self.user = User(
            full_name="Lee Faker",
            email="faker@t1.gg",
            password_hash="hashed_secret",
            role="CUSTOMER",
            status="Active",
        )
        self.db.add(self.user)
        self.db.flush()

        # 2. Tạo Order mẫu
        self.order = Order(
            order_code="ORD-TEST-CB-001",
            customer_id=self.user.id,
            total_price=Decimal("1500000.00"),
            shipping_address="T1 Basecamp, Seoul",
            status=OrderStatus.PENDING.value,
        )
        self.db.add(self.order)
        self.db.flush()

        # 3. Tạo Payment mẫu (VNPAY)
        self.txn_ref_vnpay = "TXN-VNPAY-20261120-001"
        self.payment_vnpay = Payment(
            order_id=self.order.id,
            method=PaymentMethod.VNPAY.value,
            amount=Decimal("1500000.00"),
            status=PaymentStatus.PENDING.value,
            attempt_number=1,
            transaction_reference=self.txn_ref_vnpay,
        )
        self.db.add(self.payment_vnpay)
        self.db.commit()

        # Cấu hình FastAPI App
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

    # =========================================================================
    # 1. TIÊU CHÍ: Xác thực chữ ký và nguồn theo từng cổng (Gateway Signature Verification)
    # =========================================================================
    def test_vnpay_valid_signature_updates_payment_and_order(self):
        """VNPAY: Chữ ký HMAC-SHA512 chuẩn xác nhận giao dịch thành công và chuyển trạng thái đơn."""
        vnp_params = {
            "vnp_Amount": "150000000",
            "vnp_BankCode": "NCB",
            "vnp_Command": "pay",
            "vnp_OrderInfo": f"Thanh toan don hang {self.order.order_code}",
            "vnp_ResponseCode": "00",
            "vnp_TmnCode": GatewayConfig.VNPAY_TMN_CODE,
            "vnp_TxnRef": self.txn_ref_vnpay,
        }
        secure_hash = build_vnpay_signature(vnp_params)

        payload = {
            "transaction_reference": self.txn_ref_vnpay,
            "method": "VNPAY",
            "response_code": "00",
            "secure_hash": secure_hash,
            "extra_params": vnp_params,
        }

        response = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["is_idempotent"])
        self.assertEqual(data["payment_status"], PaymentStatus.SUCCESS.value)
        self.assertEqual(data["order_status"], OrderStatus.CONFIRMED.value)

        # Kiểm tra DB
        self.db.expire_all()
        payment_db = self.db.scalar(select(Payment).where(Payment.transaction_reference == self.txn_ref_vnpay))
        order_db = self.db.scalar(select(Order).where(Order.id == self.order.id))
        self.assertEqual(payment_db.status, PaymentStatus.SUCCESS.value)
        self.assertEqual(order_db.status, OrderStatus.CONFIRMED.value)

    def test_vnpay_get_callback_return_url(self):
        """VNPAY: Xác thực callback qua GET query params (Return URL từ trình duyệt)."""
        vnp_params = {
            "vnp_Amount": "150000000",
            "vnp_BankCode": "NCB",
            "vnp_Command": "pay",
            "vnp_OrderInfo": f"Thanh toan {self.order.order_code}",
            "vnp_ResponseCode": "00",
            "vnp_TmnCode": GatewayConfig.VNPAY_TMN_CODE,
            "vnp_TxnRef": self.txn_ref_vnpay,
        }
        secure_hash = build_vnpay_signature(vnp_params)

        query_str = (
            f"/api/payments/callback?transaction_reference={self.txn_ref_vnpay}"
            f"&method=VNPAY&response_code=00&vnp_SecureHash={secure_hash}"
            f"&vnp_Amount=150000000&vnp_BankCode=NCB&vnp_Command=pay"
            f"&vnp_OrderInfo=Thanh+toan+{self.order.order_code}&vnp_ResponseCode=00"
            f"&vnp_TmnCode={GatewayConfig.VNPAY_TMN_CODE}&vnp_TxnRef={self.txn_ref_vnpay}"
        )

        response = self.client.get(query_str)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["payment_status"], PaymentStatus.SUCCESS.value)

    def test_momo_valid_signature_updates_payment_and_order(self):
        """MOMO: Chữ ký HMAC-SHA256 chuẩn được xác thực thành công."""
        order_momo = Order(
            order_code="ORD-TEST-MOMO-002",
            customer_id=self.user.id,
            total_price=Decimal("1500000.00"),
            shipping_address="T1 Basecamp, Seoul",
            status=OrderStatus.PENDING.value,
        )
        self.db.add(order_momo)
        self.db.flush()

        txn_ref_momo = "TXN-MOMO-20261120-002"
        payment_momo = Payment(
            order_id=order_momo.id,
            method=PaymentMethod.MOMO.value,
            amount=Decimal("1500000.00"),
            status=PaymentStatus.PENDING.value,
            attempt_number=1,
            transaction_reference=txn_ref_momo,
        )
        self.db.add(payment_momo)
        self.db.commit()

        momo_params = {
            "partnerCode": GatewayConfig.MOMO_PARTNER_CODE,
            "orderId": txn_ref_momo,
            "amount": "1500000",
            "orderInfo": "Thanh toan don hang MoMo",
            "resultCode": "00",
        }
        signature = build_momo_signature(momo_params)

        payload = {
            "transaction_reference": txn_ref_momo,
            "method": "MOMO",
            "response_code": "00",
            "secure_hash": signature,
            "extra_params": momo_params,
        }

        response = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["payment_status"], PaymentStatus.SUCCESS.value)

    def test_zalopay_valid_signature_updates_payment_and_order(self):
        """ZALOPAY: Chữ ký HMAC-SHA256 chuẩn được xác thực thành công."""
        order_zalo = Order(
            order_code="ORD-TEST-ZALO-003",
            customer_id=self.user.id,
            total_price=Decimal("1500000.00"),
            shipping_address="T1 Basecamp, Seoul",
            status=OrderStatus.PENDING.value,
        )
        self.db.add(order_zalo)
        self.db.flush()

        txn_ref_zalo = "TXN-ZALO-20261120-003"
        payment_zalo = Payment(
            order_id=order_zalo.id,
            method=PaymentMethod.ZALOPAY.value,
            amount=Decimal("1500000.00"),
            status=PaymentStatus.PENDING.value,
            attempt_number=1,
            transaction_reference=txn_ref_zalo,
        )
        self.db.add(payment_zalo)
        self.db.commit()

        zalo_params = {
            "app_id": GatewayConfig.ZALOPAY_APP_ID,
            "app_trans_id": txn_ref_zalo,
            "amount": "1500000",
        }
        mac = build_zalopay_signature(zalo_params)

        payload = {
            "transaction_reference": txn_ref_zalo,
            "method": "ZALOPAY",
            "response_code": "00",
            "secure_hash": mac,
            "extra_params": zalo_params,
        }

        response = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["payment_status"], PaymentStatus.SUCCESS.value)

    def test_reject_tampered_or_invalid_signature(self):
        """Bị từ chối HTTP 400 khi chữ ký bị sửa đổi hoặc không hợp lệ; Payment và Order giữ nguyên PENDING."""
        payload = {
            "transaction_reference": self.txn_ref_vnpay,
            "method": "VNPAY",
            "response_code": "00",
            "secure_hash": "HACKER_FAKE_SIGNATURE_1234567890",
            "extra_params": {
                "vnp_Amount": "150000000",
                "vnp_TxnRef": self.txn_ref_vnpay,
            },
        }

        response = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Chữ ký không hợp lệ", response.json()["detail"])

        # Trạng thái trong DB không bị thay đổi
        self.db.expire_all()
        payment_db = self.db.scalar(select(Payment).where(Payment.transaction_reference == self.txn_ref_vnpay))
        order_db = self.db.scalar(select(Order).where(Order.id == self.order.id))
        self.assertEqual(payment_db.status, PaymentStatus.PENDING.value)
        self.assertEqual(order_db.status, OrderStatus.PENDING.value)

        # Đã ghi log chữ ký không hợp lệ
        log = self.db.scalar(
            select(PaymentWebhookLog)
            .where(PaymentWebhookLog.transaction_reference == self.txn_ref_vnpay)
            .order_by(PaymentWebhookLog.id.desc())
        )
        self.assertIsNotNone(log)
        self.assertFalse(log.is_valid_signature)

    def test_reject_missing_signature(self):
        """Từ chối HTTP 400 khi thiếu hoàn toàn chữ ký số."""
        payload = {
            "transaction_reference": self.txn_ref_vnpay,
            "method": "VNPAY",
            "response_code": "00",
            "secure_hash": None,
        }
        response = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(response.status_code, 400)

    def test_reject_gateway_source_mismatch(self):
        """Từ chối HTTP 400 khi cổng gửi callback không khớp với gateway đã tạo giao dịch."""
        # Giao dịch được tạo bằng VNPAY, nhưng callback gửi là MOMO
        payload = {
            "transaction_reference": self.txn_ref_vnpay,
            "method": "MOMO",
            "response_code": "00",
            "secure_hash": "some_sig",
        }
        response = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("không khớp với phương thức", response.json()["detail"])

    # =========================================================================
    # 2. TIÊU CHÍ: Xử lý Idempotent (Chống callback lặp)
    # =========================================================================
    def test_idempotent_duplicate_callback_does_not_create_duplicates(self):
        """Callback lặp nhiều lần (Idempotency):
        - Lần 1: cập nhật SUCCESS, CONFIRMED (is_idempotent=False).
        - Lần 2 & 3: trả về 200 OK (is_idempotent=True), không tạo đơn hay thanh toán trùng.
        - Số lượng Order và Payment trong DB không hề tăng.
        """
        vnp_params = {
            "vnp_Amount": "150000000",
            "vnp_BankCode": "NCB",
            "vnp_Command": "pay",
            "vnp_ResponseCode": "00",
            "vnp_TmnCode": GatewayConfig.VNPAY_TMN_CODE,
            "vnp_TxnRef": self.txn_ref_vnpay,
        }
        secure_hash = build_vnpay_signature(vnp_params)

        payload = {
            "transaction_reference": self.txn_ref_vnpay,
            "method": "VNPAY",
            "response_code": "00",
            "secure_hash": secure_hash,
            "extra_params": vnp_params,
        }

        # Gọi lần 1
        res1 = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertTrue(data1["success"])
        self.assertFalse(data1["is_idempotent"])

        # Gọi lần 2 (Lặp lại callback từ cổng)
        res2 = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(data2["success"])
        self.assertTrue(data2["is_idempotent"])
        self.assertIn("Idempotent", data2["message"])

        # Gọi lần 3 (Lặp lại callback tiếp)
        res3 = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(res3.status_code, 200)
        data3 = res3.json()
        self.assertTrue(data3["success"])
        self.assertTrue(data3["is_idempotent"])

        # ĐẢM BẢO KHÔNG TẠO THANH TOÁN HAY ĐƠN HÀNG TRÙNG
        total_payments = self.db.scalar(select(func.count(Payment.id)))
        total_orders = self.db.scalar(select(func.count(Order.id)))
        self.assertEqual(total_payments, 1)
        self.assertEqual(total_orders, 1)

    def test_failed_callback_response_code_marks_payment_failed(self):
        """Cổng thanh toán báo lỗi (response_code != '00') -> Payment=FAILED, Order giữ nguyên PENDING."""
        vnp_params = {
            "vnp_Amount": "150000000",
            "vnp_Command": "pay",
            "vnp_ResponseCode": "24",  # Mã lỗi: Người dùng hủy giao dịch
            "vnp_TmnCode": GatewayConfig.VNPAY_TMN_CODE,
            "vnp_TxnRef": self.txn_ref_vnpay,
        }
        secure_hash = build_vnpay_signature(vnp_params)

        payload = {
            "transaction_reference": self.txn_ref_vnpay,
            "method": "VNPAY",
            "response_code": "24",
            "secure_hash": secure_hash,
            "extra_params": vnp_params,
        }

        response = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["payment_status"], PaymentStatus.FAILED.value)

        # Kiểm tra DB
        self.db.expire_all()
        payment_db = self.db.scalar(select(Payment).where(Payment.transaction_reference == self.txn_ref_vnpay))
        order_db = self.db.scalar(select(Order).where(Order.id == self.order.id))
        self.assertEqual(payment_db.status, PaymentStatus.FAILED.value)
        self.assertEqual(order_db.status, OrderStatus.PENDING.value)

        # Lặp lại callback thất bại -> Xử lý Idempotent
        res_repeat = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(res_repeat.status_code, 200)
        self.assertTrue(res_repeat.json()["is_idempotent"])

    # =========================================================================
    # 3. TIÊU CHÍ: Lưu log kết quả và API đối soát log (Audit Logging)
    # =========================================================================
    def test_webhook_audit_logging_and_inquiry_api(self):
        """Mọi callback đều sinh bản ghi audit log đầy đủ và có thể tra cứu qua GET /payments/logs/{ref}."""
        vnp_params = {
            "vnp_Amount": "150000000",
            "vnp_Command": "pay",
            "vnp_ResponseCode": "00",
            "vnp_TmnCode": GatewayConfig.VNPAY_TMN_CODE,
            "vnp_TxnRef": self.txn_ref_vnpay,
        }
        secure_hash = build_vnpay_signature(vnp_params)

        payload = {
            "transaction_reference": self.txn_ref_vnpay,
            "method": "VNPAY",
            "response_code": "00",
            "secure_hash": secure_hash,
            "extra_params": vnp_params,
        }

        # Thực hiện 2 cuộc gọi (lần 1 thành công, lần 2 idempotent)
        self.client.post("/api/payments/callback", json=payload)
        self.client.post("/api/payments/callback", json=payload)

        # Gọi API tra cứu logs
        res_logs = self.client.get(f"/api/payments/logs/{self.txn_ref_vnpay}")
        self.assertEqual(res_logs.status_code, 200)
        logs = res_logs.json()
        self.assertEqual(len(logs), 2)

        # Kiểm tra chi tiết trường log
        for item in logs:
            self.assertEqual(item["transaction_reference"], self.txn_ref_vnpay)
            self.assertEqual(item["gateway"], "VNPAY")
            self.assertTrue(item["is_valid_signature"])
            self.assertEqual(item["response_code"], "00")
            self.assertIn("created_at", item)

    def test_callback_nonexistent_transaction_returns_404(self):
        """Callback với transaction_reference không tồn tại trả về 404 và vẫn lưu log audit."""
        payload = {
            "transaction_reference": "TXN-NOT-EXIST-9999",
            "method": "VNPAY",
            "response_code": "00",
            "secure_hash": "sig",
        }
        response = self.client.post("/api/payments/callback", json=payload)
        self.assertEqual(response.status_code, 404)

        # Kiểm tra DB xem log có được lưu không
        log = self.db.scalar(
            select(PaymentWebhookLog).where(
                PaymentWebhookLog.transaction_reference == "TXN-NOT-EXIST-9999"
            )
        )
        self.assertIsNotNone(log)
        self.assertFalse(log.is_valid_signature)


if __name__ == "__main__":
    unittest.main()
