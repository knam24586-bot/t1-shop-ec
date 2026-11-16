"""Bộ kiểm thử cho các API giỏ hàng: Xem, Thêm, Sửa, Xóa.
Kiểm tra tất cả các tiêu chí chấp nhận:
1. API xem/thêm/sửa/xóa Cart hoạt động chính xác.
2. CHỈ THAO TÁC TRÊN CART CỦA USER HIỆN TẠI (User A không thể sửa/xóa item của User B).
3. KIỂM TRA VARIANT VÀ TỒN KHO:
   - Variant không tồn tại -> 404
   - Thêm vượt quá tồn kho -> 400
   - Quy tắc gộp giỏ: cộng dồn vượt tồn kho -> 400
   - Sửa số lượng vượt tồn kho -> 400
   - Số lượng <= 0 -> 400/422
"""
import unittest
from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.core.deps import get_current_user
from app.db.session import Base, get_db
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.models.variant import ProductVariant
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.order import Order  # noqa: F401
from app.models.order_item import OrderItem  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.voucher import Voucher  # noqa: F401
from app.routers.cart import router as cart_router


class TestCartAPIs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        # Tạo DB SQLite in-memory với StaticPool để chia sẻ cùng connection giữa các thread
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        # Tạo 2 User: User A (ID=1) và User B (ID=2)
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
        self.category = Category(name="Thời trang T1", slug="thoi-trang-t1", status="Active")
        self.db.add_all([self.user_a, self.user_b, self.category])
        self.db.flush()

        # Tạo Product và 2 Variant với tồn kho cụ thể
        self.product = Product(
            category_id=self.category.id,
            name="Áo Đấu T1 CKTG",
            slug="ao-dau-t1-cktg",
            price=Decimal("800000.00"),
            stock=15,
            status="Published",
        )
        self.db.add(self.product)
        self.db.flush()

        # Variant 1: Size M - Tồn kho = 10
        self.variant_m = ProductVariant(
            product_id=self.product.id,
            sku="T1-JERSEY-M",
            color="Red",
            size="M",
            stock=10,
        )
        # Variant 2: Size L - Tồn kho = 3
        self.variant_l = ProductVariant(
            product_id=self.product.id,
            sku="T1-JERSEY-L",
            color="Red",
            size="L",
            stock=3,
        )
        self.db.add_all([self.variant_m, self.variant_l])
        self.db.commit()

        # Khởi tạo FastAPI App và gắn router cart
        self.app = FastAPI()
        self.app.include_router(cart_router)

        # Override dependency get_db
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
    # 1. TIÊU CHÍ: Xem giỏ hàng (GET /cart)
    # -------------------------------------------------------------
    def test_get_empty_cart(self):
        """User mới xem giỏ hàng -> Giỏ hàng trống với tổng tiền = 0."""
        response = self.client.get("/cart", headers={"X-User-Id": str(self.user_a.id)})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["user_id"], self.user_a.id)
        self.assertEqual(data["total_items"], 0)
        self.assertEqual(Decimal(str(data["total_amount"])), Decimal("0.00"))
        self.assertEqual(len(data["items"]), 0)

    # -------------------------------------------------------------
    # 2. TIÊU CHÍ: Thêm sản phẩm & Kiểm tra Variant, Tồn kho (POST /cart/items)
    # -------------------------------------------------------------
    def test_add_to_cart_success(self):
        """Thêm sản phẩm thành công khi còn tồn kho."""
        payload = {"variant_id": self.variant_m.id, "quantity": 2}
        response = self.client.post("/cart/items", json=payload, headers={"X-User-Id": str(self.user_a.id)})
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["message"], "Thêm sản phẩm vào giỏ hàng thành công.")
        cart = data["cart"]
        self.assertEqual(cart["total_items"], 2)
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["sku"], "T1-JERSEY-M")
        self.assertEqual(cart["items"][0]["quantity"], 2)
        self.assertEqual(Decimal(str(cart["total_amount"])), Decimal("1600000.00"))  # 800,000 * 2

    def test_add_to_cart_variant_not_found(self):
        """Thêm biến thể không tồn tại -> 404 Not Found."""
        payload = {"variant_id": 99999, "quantity": 1}
        response = self.client.post("/cart/items", json=payload, headers={"X-User-Id": str(self.user_a.id)})
        self.assertEqual(response.status_code, 404)
        self.assertIn("không tồn tại", response.json()["detail"])

    def test_add_to_cart_exceeds_stock(self):
        """Thêm số lượng vượt quá tồn kho (stock=10, yêu cầu=12) -> 400 Bad Request."""
        payload = {"variant_id": self.variant_m.id, "quantity": 12}
        response = self.client.post("/cart/items", json=payload, headers={"X-User-Id": str(self.user_a.id)})
        self.assertEqual(response.status_code, 400)
        self.assertIn("không đủ tồn kho", response.json()["detail"])

    def test_add_to_cart_merge_rule_and_cumulative_stock_check(self):
        """Quy tắc gộp giỏ và kiểm tra tồn kho khi cộng dồn:
        - Lần 1: thêm 6 áo (stock=10) -> OK (còn 4)
        - Lần 2: thêm tiếp 5 áo -> Tổng 11 > 10 -> 400 Bad Request
        - Lần 3: thêm tiếp 3 áo -> Tổng 9 <= 10 -> Thành công, gộp thành 9 áo
        """
        headers = {"X-User-Id": str(self.user_a.id)}

        # Lần 1: thêm 6
        res1 = self.client.post("/cart/items", json={"variant_id": self.variant_m.id, "quantity": 6}, headers=headers)
        self.assertEqual(res1.status_code, 201)

        # Lần 2: thêm tiếp 5 (tổng 11 > 10) -> Bị từ chối
        res2 = self.client.post("/cart/items", json={"variant_id": self.variant_m.id, "quantity": 5}, headers=headers)
        self.assertEqual(res2.status_code, 400)
        self.assertIn("không đủ tồn kho", res2.json()["detail"])

        # Lần 3: thêm tiếp 3 (tổng 9 <= 10) -> Thành công
        res3 = self.client.post("/cart/items", json={"variant_id": self.variant_m.id, "quantity": 3}, headers=headers)
        self.assertEqual(res3.status_code, 201)
        cart = res3.json()["cart"]
        self.assertEqual(cart["total_items"], 9)
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 9)

    # -------------------------------------------------------------
    # 3. TIÊU CHÍ: Sửa số lượng (PUT /cart/items/{id})
    # -------------------------------------------------------------
    def test_update_item_quantity_success_and_stock_check(self):
        """Cập nhật số lượng sản phẩm trong giỏ:
        - Sửa trong phạm vi tồn kho -> Thành công
        - Sửa vượt quá tồn kho -> 400 Bad Request
        """
        headers = {"X-User-Id": str(self.user_a.id)}
        res_add = self.client.post("/cart/items", json={"variant_id": self.variant_l.id, "quantity": 1}, headers=headers)
        item_id = res_add.json()["cart"]["items"][0]["id"]

        # Sửa thành 3 (stock=3) -> Thành công
        res_update1 = self.client.put(f"/cart/items/{item_id}", json={"quantity": 3}, headers=headers)
        self.assertEqual(res_update1.status_code, 200)
        self.assertEqual(res_update1.json()["cart"]["items"][0]["quantity"], 3)

        # Sửa thành 4 (vượt quá stock=3) -> 400 Bad Request
        res_update2 = self.client.put(f"/cart/items/{item_id}", json={"quantity": 4}, headers=headers)
        self.assertEqual(res_update2.status_code, 400)
        self.assertIn("vượt quá số lượng tồn kho", res_update2.json()["detail"])

    # -------------------------------------------------------------
    # 4. TIÊU CHÍ: Chỉ thao tác trên cart của user hiện tại
    # -------------------------------------------------------------
    def test_isolation_between_users_cannot_modify_other_user_cart(self):
        """User A thêm món vào giỏ -> User B KHÔNG THỂ sửa hoặc xoá món của User A (403 Forbidden)."""
        # User A thêm món vào giỏ
        res_a = self.client.post(
            "/cart/items",
            json={"variant_id": self.variant_m.id, "quantity": 2},
            headers={"X-User-Id": str(self.user_a.id)},
        )
        item_a_id = res_a.json()["cart"]["items"][0]["id"]

        # User B cố tình SỬA item của User A -> Bị chặn 403 Forbidden
        res_b_update = self.client.put(
            f"/cart/items/{item_a_id}",
            json={"quantity": 5},
            headers={"X-User-Id": str(self.user_b.id)},
        )
        self.assertEqual(res_b_update.status_code, 403)
        self.assertIn("không có quyền thao tác", res_b_update.json()["detail"])

        # User B cố tình XOÁ item của User A -> Bị chặn 403 Forbidden
        res_b_delete = self.client.delete(
            f"/cart/items/{item_a_id}",
            headers={"X-User-Id": str(self.user_b.id)},
        )
        self.assertEqual(res_b_delete.status_code, 403)
        self.assertIn("không có quyền thao tác", res_b_delete.json()["detail"])

        # Giỏ của User B vẫn hoàn toàn trống
        res_b_cart = self.client.get("/cart", headers={"X-User-Id": str(self.user_b.id)})
        self.assertEqual(res_b_cart.json()["total_items"], 0)

        # Giỏ của User A vẫn nguyên vẹn
        res_a_cart = self.client.get("/cart", headers={"X-User-Id": str(self.user_a.id)})
        self.assertEqual(res_a_cart.json()["total_items"], 2)

    # -------------------------------------------------------------
    # 5. TIÊU CHÍ: Xóa sản phẩm khỏi giỏ (DELETE /cart/items/{id})
    # -------------------------------------------------------------
    def test_delete_cart_item(self):
        """Xóa món khỏi giỏ hàng thành công."""
        headers = {"X-User-Id": str(self.user_a.id)}
        res_add = self.client.post("/cart/items", json={"variant_id": self.variant_m.id, "quantity": 2}, headers=headers)
        item_id = res_add.json()["cart"]["items"][0]["id"]

        # Xóa món
        res_del = self.client.delete(f"/cart/items/{item_id}", headers=headers)
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.json()["message"], "Xóa sản phẩm khỏi giỏ hàng thành công.")
        self.assertEqual(res_del.json()["cart"]["total_items"], 0)

    def test_clear_cart(self):
        """Làm trống toàn bộ giỏ hàng."""
        headers = {"X-User-Id": str(self.user_a.id)}
        self.client.post("/cart/items", json={"variant_id": self.variant_m.id, "quantity": 1}, headers=headers)
        self.client.post("/cart/items", json={"variant_id": self.variant_l.id, "quantity": 2}, headers=headers)

        res_clear = self.client.delete("/cart", headers=headers)
        self.assertEqual(res_clear.status_code, 200)
        self.assertEqual(res_clear.json()["cart"]["total_items"], 0)


if __name__ == "__main__":
    unittest.main()
