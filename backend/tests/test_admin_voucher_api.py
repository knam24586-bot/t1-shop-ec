"""Bộ kiểm thử cho API Admin tạo, sửa, khóa và xem Voucher.
Kiểm tra toàn diện tất cả các tiêu chí chấp nhận:
1. ADMIN TẠO/SỬA/KHÓA/MỞ KHÓA VÀ XEM VOUCHER:
   - Admin tạo mới voucher (201 Created).
   - Admin sửa thông tin voucher.
   - Admin khóa voucher (chuyển sang INACTIVE).
   - Admin mở khóa voucher (chuyển sang ACTIVE).
   - Admin xem danh sách và chi tiết voucher.
   - Phân quyền: Người dùng role CUSTOMER hoặc VENDOR bị chặn 403 Forbidden.
2. CODE DUY NHẤT:
   - Chặn tạo trùng code (kể cả chữ thường chữ hoa).
3. NGÀY BẮT ĐẦU < NGÀY KẾT THÚC:
   - Chặn tạo/sửa voucher khi valid_from >= valid_to (400 hoặc 422).
4. KHÔNG ÁP DỤNG MÃ BỊ KHÓA / HẾT HẠN:
   - Mã bị khóa (INACTIVE) không thể áp dụng (400 Bad Request).
   - Mã hết hạn sử dụng không thể áp dụng (400 Bad Request).
   - Mã hợp lệ được áp dụng và tính toán giảm giá chính xác.
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
from app.models.admin_audit_log import AdminOrderAuditLog  # noqa: F401
from app.models.admin_voucher_log import AdminVoucherLog  # noqa: F401
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.category import Category
from app.models.order import Order  # noqa: F401
from app.models.order_cancellation import OrderCancellation  # noqa: F401
from app.models.order_item import OrderItem  # noqa: F401
from app.models.order_status_history import OrderStatusHistory  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.product import Product
from app.models.store import Store  # noqa: F401
from app.models.store_order import StoreOrder  # noqa: F401
from app.models.user import User
from app.models.variant import ProductVariant
from app.models.voucher import DiscountType, Voucher, VoucherStatus
from app.models.wishlist import Wishlist  # noqa: F401
from app.routers.admin_voucher import router as admin_voucher_router
from app.routers.voucher import router as customer_voucher_router


class TestAdminVoucherAPIs(unittest.TestCase):
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

        # 1. Tạo các Users: Admin, Customer, Vendor
        self.admin_user = User(
            full_name="Quản Trị Viên (Admin)",
            email="admin@t1.gg",
            password_hash="hash_pw_admin",
            role="ADMIN",
            status="Active",
        )
        self.customer_user = User(
            full_name="Khách Hàng",
            email="customer@t1.gg",
            password_hash="hash_pw_customer",
            role="CUSTOMER",
            status="Active",
        )
        self.vendor_user = User(
            full_name="Nhà Cung Cấp",
            email="vendor@t1.gg",
            password_hash="hash_pw_vendor",
            role="VENDOR",
            status="Active",
        )
        self.db.add_all([self.admin_user, self.customer_user, self.vendor_user])
        self.db.commit()

        # 2. Khởi tạo FastAPI App gắn routers
        self.app = FastAPI()
        self.app.include_router(admin_voucher_router, prefix="/api")
        self.app.include_router(admin_voucher_router)
        self.app.include_router(customer_voucher_router, prefix="/api")
        self.app.include_router(customer_voucher_router)

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

    # =========================================================================
    # 1. TIÊU CHÍ: ADMIN TẠO/SỬA/KHÓA/MỞ KHÓA VÀ XEM VOUCHER
    # =========================================================================

    def test_admin_create_voucher_success(self):
        """Admin tạo mới voucher thành công (201 Created)."""
        now = datetime.now()
        payload = {
            "code": "T1CHAMPION2026",
            "name": "Mừng T1 Vô Địch 2026",
            "description": "Giảm 15% tối đa 150.000đ cho đơn từ 500k",
            "discount_type": "PERCENTAGE",
            "discount_value": 15.00,
            "max_discount_amount": 150000.00,
            "min_order_amount": 500000.00,
            "valid_from": (now - timedelta(days=1)).isoformat(),
            "valid_to": (now + timedelta(days=30)).isoformat(),
            "usage_limit": 50,
            "status": "ACTIVE",
        }

        res = self.client.post("/api/admin/vouchers", json=payload, headers=self.admin_headers)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIn("thành công", data["message"])
        v = data["voucher"]
        self.assertEqual(v["code"], "T1CHAMPION2026")
        self.assertEqual(v["discount_type"], "PERCENTAGE")
        self.assertEqual(Decimal(str(v["discount_value"])), Decimal("15.00"))
        self.assertEqual(v["status"], "ACTIVE")

        # Kiểm tra Database
        self.db.expire_all()
        voucher_db = self.db.scalar(select(Voucher).where(Voucher.code == "T1CHAMPION2026"))
        self.assertIsNotNone(voucher_db)
        self.assertEqual(voucher_db.usage_limit, 50)

    def test_admin_list_and_get_voucher_detail(self):
        """Admin xem danh sách và chi tiết voucher."""
        now = datetime.now()
        v1 = Voucher(
            code="SALE10",
            name="Giảm 10%",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("10.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=10),
            status=VoucherStatus.ACTIVE.value,
        )
        v2 = Voucher(
            code="SALE20",
            name="Giảm 20%",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("20.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=10),
            status=VoucherStatus.INACTIVE.value,
        )
        self.db.add_all([v1, v2])
        self.db.commit()

        # 1. Danh sách toàn bộ voucher (kể cả ACTIVE và INACTIVE)
        res_list = self.client.get("/api/admin/vouchers", headers=self.admin_headers)
        self.assertEqual(res_list.status_code, 200)
        d_list = res_list.json()
        self.assertEqual(d_list["total"], 2)
        codes = [item["code"] for item in d_list["items"]]
        self.assertIn("SALE10", codes)
        self.assertIn("SALE20", codes)

        # Lọc theo status
        res_filter = self.client.get("/api/admin/vouchers?status=INACTIVE", headers=self.admin_headers)
        self.assertEqual(res_filter.status_code, 200)
        self.assertEqual(res_filter.json()["total"], 1)
        self.assertEqual(res_filter.json()["items"][0]["code"], "SALE20")

        # 2. Xem chi tiết theo code
        res_detail = self.client.get("/api/admin/vouchers/SALE10", headers=self.admin_headers)
        self.assertEqual(res_detail.status_code, 200)
        self.assertEqual(res_detail.json()["code"], "SALE10")

    def test_admin_update_voucher(self):
        """Admin sửa thông tin voucher."""
        now = datetime.now()
        voucher = Voucher(
            code="SPRING2026",
            name="Khuyến Mãi Mùa Xuân",
            discount_type=DiscountType.FIXED_AMOUNT.value,
            discount_value=Decimal("50000.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=10),
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(voucher)
        self.db.commit()

        update_payload = {
            "name": "Khuyến Mãi Mùa Xuân (Đã Cập Nhật)",
            "discount_value": 75000.00,
            "min_order_amount": 300000.00,
        }
        res = self.client.put(
            f"/api/admin/vouchers/{voucher.id}",
            json=update_payload,
            headers=self.admin_headers,
        )
        self.assertEqual(res.status_code, 200)
        d = res.json()["voucher"]
        self.assertEqual(d["name"], "Khuyến Mãi Mùa Xuân (Đã Cập Nhật)")
        self.assertEqual(Decimal(str(d["discount_value"])), Decimal("75000.00"))
        self.assertEqual(Decimal(str(d["min_order_amount"])), Decimal("300000.00"))

    def test_admin_lock_and_unlock_voucher(self):
        """Admin khóa (lock) và mở khóa (unlock) voucher."""
        now = datetime.now()
        voucher = Voucher(
            code="LOCKTEST",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("10.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=10),
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(voucher)
        self.db.commit()

        # 1. Khóa voucher -> chuyển sang INACTIVE
        res_lock = self.client.post(
            f"/api/admin/vouchers/{voucher.code}/lock",
            json={"reason": "Tạm dừng chương trình do sự cố kỹ thuật"},
            headers=self.admin_headers,
        )
        self.assertEqual(res_lock.status_code, 200)
        self.assertEqual(res_lock.json()["voucher"]["status"], "INACTIVE")

        # Kiểm tra Database
        self.db.expire_all()
        v_db = self.db.get(Voucher, voucher.id)
        self.assertEqual(v_db.status, VoucherStatus.INACTIVE.value)

        # 2. Mở khóa voucher -> chuyển sang ACTIVE
        res_unlock = self.client.post(
            f"/api/admin/vouchers/{voucher.code}/unlock",
            headers=self.admin_headers,
        )
        self.assertEqual(res_unlock.status_code, 200)
        self.assertEqual(res_unlock.json()["voucher"]["status"], "ACTIVE")

    def test_non_admin_cannot_access_admin_voucher_apis(self):
        """Người dùng không có quyền Admin bị chặn 403 Forbidden."""
        res_cust = self.client.get(
            "/api/admin/vouchers",
            headers={"X-Role": "CUSTOMER", "X-User-Id": str(self.customer_user.id)},
        )
        self.assertEqual(res_cust.status_code, 403)

        res_vend = self.client.post(
            "/api/admin/vouchers",
            json={"code": "HACK"},
            headers={"X-Role": "VENDOR", "X-User-Id": str(self.vendor_user.id)},
        )
        self.assertEqual(res_vend.status_code, 403)

    # =========================================================================
    # 2. TIÊU CHÍ: CODE DUY NHẤT
    # =========================================================================

    def test_voucher_code_must_be_unique(self):
        """Code duy nhất: Không cho phép tạo voucher trùng code (kể cả case-insensitive)."""
        now = datetime.now()
        v_existing = Voucher(
            code="UNIQUECODE",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("10.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=10),
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(v_existing)
        self.db.commit()

        # Tạo voucher với cùng code (chữ thường)
        payload = {
            "code": "uniquecode",
            "discount_type": "PERCENTAGE",
            "discount_value": 15.00,
            "valid_from": (now - timedelta(days=1)).isoformat(),
            "valid_to": (now + timedelta(days=10)).isoformat(),
        }
        res = self.client.post("/api/admin/vouchers", json=payload, headers=self.admin_headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn("đã tồn tại", res.json()["detail"].lower())

    # =========================================================================
    # 3. TIÊU CHÍ: NGÀY BẮT ĐẦU < NGÀY KẾT THÚC
    # =========================================================================

    def test_valid_from_must_be_before_valid_to(self):
        """Ngày bắt đầu phải nhỏ hơn ngày kết thúc (valid_from < valid_to)."""
        now = datetime.now()

        # 1. valid_from lớn hơn valid_to
        payload_invalid_1 = {
            "code": "DATERANGE1",
            "discount_type": "PERCENTAGE",
            "discount_value": 10.00,
            "valid_from": (now + timedelta(days=10)).isoformat(),
            "valid_to": now.isoformat(),
        }
        res1 = self.client.post("/api/admin/vouchers", json=payload_invalid_1, headers=self.admin_headers)
        self.assertIn(res1.status_code, [400, 422])
        self.assertIn("nhỏ hơn", str(res1.json()).lower())

        # 2. valid_from bằng valid_to (không < valid_to)
        payload_invalid_2 = {
            "code": "DATERANGE2",
            "discount_type": "PERCENTAGE",
            "discount_value": 10.00,
            "valid_from": now.isoformat(),
            "valid_to": now.isoformat(),
        }
        res2 = self.client.post("/api/admin/vouchers", json=payload_invalid_2, headers=self.admin_headers)
        self.assertIn(res2.status_code, [400, 422])
        self.assertIn("nhỏ hơn", str(res2.json()).lower())

    # =========================================================================
    # 4. TIÊU CHÍ: KHÔNG ÁP DỤNG MÃ BỊ KHÓA / HẾT HẠN
    # =========================================================================

    def test_cannot_apply_locked_voucher(self):
        """Mã voucher bị khóa (INACTIVE) tuyệt đối không được áp dụng."""
        now = datetime.now()
        voucher_locked = Voucher(
            code="LOCKEDVOUCHER",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("20.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=10),
            status=VoucherStatus.INACTIVE.value,
        )
        self.db.add(voucher_locked)
        self.db.commit()

        # 1. Thử áp dụng qua Admin test endpoint
        res_test = self.client.post(
            "/api/admin/vouchers/test-apply",
            json={"code": "LOCKEDVOUCHER", "order_amount": 500000.00},
            headers=self.admin_headers,
        )
        self.assertEqual(res_test.status_code, 400)
        self.assertIn("khóa", res_test.json()["detail"].lower())

        # 2. Thử áp dụng qua endpoint khách hàng /api/vouchers/check
        res_client = self.client.post(
            "/api/vouchers/check",
            json={"code": "LOCKEDVOUCHER", "order_amount": 500000.00},
        )
        self.assertEqual(res_client.status_code, 400)
        self.assertIn("inactive", res_client.json()["detail"].lower())

    def test_cannot_apply_expired_voucher(self):
        """Mã voucher đã hết hạn sử dụng (now > valid_to) tuyệt đối không được áp dụng."""
        now = datetime.now()
        voucher_expired = Voucher(
            code="EXPIREDVOUCHER",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("20.00"),
            valid_from=now - timedelta(days=10),
            valid_to=now - timedelta(days=1),  # Đã hết hạn hôm qua
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(voucher_expired)
        self.db.commit()

        # Thử áp dụng qua test endpoint
        res_test = self.client.post(
            "/api/admin/vouchers/test-apply",
            json={"code": "EXPIREDVOUCHER", "order_amount": 500000.00},
            headers=self.admin_headers,
        )
        self.assertEqual(res_test.status_code, 400)
        self.assertIn("hết hạn", res_test.json()["detail"].lower())

    def test_apply_valid_voucher_success(self):
        """Mã voucher hợp lệ (ACTIVE và trong thời hạn) áp dụng thành công và tính mức giảm chính xác."""
        now = datetime.now()
        voucher_valid = Voucher(
            code="VALIDVOUCHER20",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal("20.00"),
            max_discount_amount=Decimal("100000.00"),
            min_order_amount=Decimal("200000.00"),
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=10),
            status=VoucherStatus.ACTIVE.value,
        )
        self.db.add(voucher_valid)
        self.db.commit()

        # Đơn 400.000đ -> Giảm 20% = 80.000đ -> Còn 320.000đ
        res_test = self.client.post(
            "/api/admin/vouchers/test-apply",
            json={"code": "VALIDVOUCHER20", "order_amount": 400000.00},
            headers=self.admin_headers,
        )
        self.assertEqual(res_test.status_code, 200)
        data = res_test.json()
        self.assertTrue(data["valid"])
        self.assertEqual(Decimal(str(data["discount_amount"])), Decimal("80000.00"))
        self.assertEqual(Decimal(str(data["final_amount"])), Decimal("320000.00"))


if __name__ == "__main__":
    unittest.main()
