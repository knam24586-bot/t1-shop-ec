"""Bộ kiểm thử cho Wishlist APIs: Xem (List), Thêm (Add), Xóa (Delete).
Kiểm tra tất cả các tiêu chí chấp nhận:
1. API thêm/xóa/list Wishlist hoạt động chính xác.
2. KHÔNG TẠO ITEM TRÙNG:
   - Thêm cùng 1 sản phẩm nhiều lần -> 400 Bad Request.
   - Ràng buộc DB uk_wishlist_user_product ngăn chặn trùng ở tầng cơ sở dữ liệu.
3. USER CHỈ XEM/SỬA WISHLIST CỦA MÌNH:
   - User A chỉ xem được sản phẩm trong wishlist của User A.
   - User B chỉ xem được sản phẩm trong wishlist của User B.
   - User A không thể xóa sản phẩm trong wishlist của User B (403/404).
   - User A xóa sản phẩm không ảnh hưởng đến wishlist của User B.
4. Kiểm tra sản phẩm không tồn tại -> 404 Not Found.
"""
import unittest
from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.tokens import create_access_token
from app.db.session import Base, get_db
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.models.wishlist import Wishlist, WishlistItem
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.variant import ProductVariant  # noqa: F401
from app.models.order import Order  # noqa: F401
from app.models.order_item import OrderItem  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.voucher import Voucher  # noqa: F401
from app.routers.wishlist import router as wishlist_router


class TestWishlistAPIs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        self._orig_secret = settings.JWT_SECRET_KEY
        settings.JWT_SECRET_KEY = "test-jwt-secret-key-at-least-32-characters-long"
        # Tạo DB SQLite in-memory với StaticPool để chia sẻ session
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        # Tạo 2 User riêng biệt: User A (Faker) và User B (Oner)
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

        # Tạo 3 sản phẩm mẫu
        self.product_1 = Product(
            category_id=self.category.id,
            name="Áo Đấu T1 CKTG 2026",
            slug="ao-dau-t1-cktg-2026",
            price=Decimal("850000.00"),
            stock=20,
            image_url="https://example.com/ao-t1.png",
            status="Published",
        )
        self.product_2 = Product(
            category_id=self.category.id,
            name="Bàn Phím Cơ T1 Faker Edition",
            slug="ban-phim-co-t1-faker-edition",
            price=Decimal("2500000.00"),
            stock=5,
            image_url="https://example.com/keyboard.png",
            status="Published",
        )
        self.product_3 = Product(
            category_id=self.category.id,
            name="Chuột Gaming T1 Wireless",
            slug="chuot-gaming-t1-wireless",
            price=Decimal("1200000.00"),
            stock=15,
            image_url="https://example.com/mouse.png",
            status="Published",
        )
        self.db.add_all([self.product_1, self.product_2, self.product_3])
        self.db.commit()

        # Khởi tạo FastAPI App gắn wishlist router
        self.app = FastAPI()
        self.app.include_router(wishlist_router, prefix="/api")
        self.app.include_router(wishlist_router)  # hỗ trợ cả /wishlist và /api/wishlist

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
    # 1. TIÊU CHÍ: Xem danh sách yêu thích (List Wishlist)
    # -------------------------------------------------------------
    def test_get_empty_wishlist(self):
        """User mới chưa thêm sản phẩm -> Wishlist trống."""
        response = self.client.get("/api/wishlist", headers=self._auth_headers(self.user_a))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 0)

        # Định dạng summary
        resp_sum = self.client.get("/api/wishlist/summary", headers=self._auth_headers(self.user_a))
        self.assertEqual(resp_sum.status_code, 200)
        sum_data = resp_sum.json()
        self.assertEqual(sum_data["total_items"], 0)
        self.assertEqual(len(sum_data["items"]), 0)

    # -------------------------------------------------------------
    # 2. TIÊU CHÍ: Thêm sản phẩm vào Wishlist (Add to Wishlist)
    # -------------------------------------------------------------
    def test_add_to_wishlist_success(self):
        """Thêm sản phẩm hợp lệ vào wishlist thành công."""
        payload = {"product_id": self.product_1.id}
        response = self.client.post("/api/wishlist", json=payload, headers=self._auth_headers(self.user_a))
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["message"], "Thêm sản phẩm vào danh sách yêu thích thành công.")
        item = data["item"]
        self.assertEqual(item["user_id"], self.user_a.id)
        self.assertEqual(item["product_id"], self.product_1.id)
        self.assertEqual(item["product_name"], "Áo Đấu T1 CKTG 2026")
        self.assertEqual(Decimal(str(item["product_price"])), Decimal("850000.00"))

    def test_add_to_wishlist_alias_endpoint(self):
        """Thêm sản phẩm qua endpoint alias /wishlist/items hoạt động tương tự."""
        payload = {"product_id": self.product_2.id}
        response = self.client.post("/api/wishlist/items", json=payload, headers=self._auth_headers(self.user_a))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["item"]["product_id"], self.product_2.id)

    def test_add_nonexistent_product(self):
        """Thêm sản phẩm không tồn tại -> 404 Not Found."""
        payload = {"product_id": 99999}
        response = self.client.post("/api/wishlist", json=payload, headers=self._auth_headers(self.user_a))
        self.assertEqual(response.status_code, 404)
        self.assertIn("không tồn tại", response.json()["detail"])

    # -------------------------------------------------------------
    # 3. TIÊU CHÍ: Không tạo item trùng (Prevent Duplicates)
    # -------------------------------------------------------------
    def test_prevent_duplicate_items_via_api(self):
        """Thêm sản phẩm đã có trong wishlist -> 400 Bad Request."""
        payload = {"product_id": self.product_1.id}
        # Lần 1: Thành công
        res1 = self.client.post("/api/wishlist", json=payload, headers=self._auth_headers(self.user_a))
        self.assertEqual(res1.status_code, 201)

        # Lần 2: Trùng -> Báo lỗi 400
        res2 = self.client.post("/api/wishlist", json=payload, headers=self._auth_headers(self.user_a))
        self.assertEqual(res2.status_code, 400)
        self.assertIn("đã có trong danh sách yêu thích", res2.json()["detail"])

        # Danh sách chỉ có duy nhất 1 mục
        res_list = self.client.get("/api/wishlist", headers=self._auth_headers(self.user_a))
        self.assertEqual(len(res_list.json()), 1)

    def test_db_unique_constraint(self):
        """Ràng buộc DB uk_wishlist_user_product ngăn trùng lặp (IntegrityError)."""
        item1 = Wishlist(user_id=self.user_a.id, product_id=self.product_1.id)
        self.db.add(item1)
        self.db.commit()

        # Cố tình add trực tiếp cùng user_id và product_id vào DB
        item2 = Wishlist(user_id=self.user_a.id, product_id=self.product_1.id)
        self.db.add(item2)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    # -------------------------------------------------------------
    # 4. TIÊU CHÍ: User chỉ xem/sửa Wishlist của mình (Isolation)
    # -------------------------------------------------------------
    def test_user_can_only_view_own_wishlist(self):
        """User A và User B chỉ nhìn thấy sản phẩm trong wishlist của chính mình."""
        # User A thêm Product 1 và Product 2
        self.client.post("/api/wishlist", json={"product_id": self.product_1.id}, headers=self._auth_headers(self.user_a))
        self.client.post("/api/wishlist", json={"product_id": self.product_2.id}, headers=self._auth_headers(self.user_a))

        # User B thêm Product 2 và Product 3
        self.client.post("/api/wishlist", json={"product_id": self.product_2.id}, headers=self._auth_headers(self.user_b))
        self.client.post("/api/wishlist", json={"product_id": self.product_3.id}, headers=self._auth_headers(self.user_b))

        # User A xem wishlist -> chỉ có 2 sản phẩm (1 và 2)
        res_a = self.client.get("/api/wishlist", headers=self._auth_headers(self.user_a))
        self.assertEqual(res_a.status_code, 200)
        items_a = res_a.json()
        self.assertEqual(len(items_a), 2)
        product_ids_a = {it["product_id"] for it in items_a}
        self.assertEqual(product_ids_a, {self.product_1.id, self.product_2.id})
        for it in items_a:
            self.assertEqual(it["user_id"], self.user_a.id)

        # User B xem wishlist -> chỉ có 2 sản phẩm (2 và 3)
        res_b = self.client.get("/api/wishlist", headers=self._auth_headers(self.user_b))
        self.assertEqual(res_b.status_code, 200)
        items_b = res_b.json()
        self.assertEqual(len(items_b), 2)
        product_ids_b = {it["product_id"] for it in items_b}
        self.assertEqual(product_ids_b, {self.product_2.id, self.product_3.id})
        for it in items_b:
            self.assertEqual(it["user_id"], self.user_b.id)

    def test_user_cannot_delete_other_user_wishlist_item(self):
        """User A không thể xóa sản phẩm trong wishlist của User B."""
        # User B thêm Product 3
        res_add_b = self.client.post(
            "/api/wishlist", json={"product_id": self.product_3.id}, headers=self._auth_headers(self.user_b)
        )
        item_b_id = res_add_b.json()["item"]["id"]

        # User A cố tình gửi request xóa Product 3 (hoặc item_b_id) với tư cách User A
        res_del_by_prod = self.client.delete(
            f"/api/wishlist/{self.product_3.id}", headers=self._auth_headers(self.user_a)
        )
        self.assertIn(res_del_by_prod.status_code, [403, 404])

        res_del_by_id = self.client.delete(
            f"/api/wishlist/items/{item_b_id}", headers=self._auth_headers(self.user_a)
        )
        self.assertIn(res_del_by_id.status_code, [403, 404])

        # Kiểm tra wishlist của User B vẫn còn nguyên vẹn Product 3
        res_b = self.client.get("/api/wishlist", headers=self._auth_headers(self.user_b))
        self.assertEqual(len(res_b.json()), 1)
        self.assertEqual(res_b.json()[0]["product_id"], self.product_3.id)

    # -------------------------------------------------------------
    # 5. TIÊU CHÍ: Xóa sản phẩm khỏi Wishlist (Delete Wishlist)
    # -------------------------------------------------------------
    def test_delete_own_wishlist_item_success(self):
        """User A xóa sản phẩm trong wishlist của chính mình thành công."""
        # User A thêm Product 1 và Product 2
        self.client.post("/api/wishlist", json={"product_id": self.product_1.id}, headers=self._auth_headers(self.user_a))
        self.client.post("/api/wishlist", json={"product_id": self.product_2.id}, headers=self._auth_headers(self.user_a))

        # User A xóa Product 1
        res_del = self.client.delete(f"/api/wishlist/{self.product_1.id}", headers=self._auth_headers(self.user_a))
        self.assertEqual(res_del.status_code, 200)

        # Danh sách của User A chỉ còn lại Product 2
        res_list = self.client.get("/api/wishlist", headers=self._auth_headers(self.user_a))
        self.assertEqual(len(res_list.json()), 1)
        self.assertEqual(res_list.json()[0]["product_id"], self.product_2.id)

    def test_delete_by_product_route_and_item_route(self):
        """Kiểm tra các đường dẫn xóa chuyên biệt (/products/{id} và /items/{id})."""
        # User A thêm Product 1 và Product 2
        res1 = self.client.post("/api/wishlist", json={"product_id": self.product_1.id}, headers=self._auth_headers(self.user_a))
        res2 = self.client.post("/api/wishlist", json={"product_id": self.product_2.id}, headers=self._auth_headers(self.user_a))
        item_2_id = res2.json()["item"]["id"]

        # Xóa Product 1 qua /products/{product_id}
        del1 = self.client.delete(f"/api/wishlist/products/{self.product_1.id}", headers=self._auth_headers(self.user_a))
        self.assertEqual(del1.status_code, 200)

        # Xóa Product 2 qua /items/{item_id}
        del2 = self.client.delete(f"/api/wishlist/items/{item_2_id}", headers=self._auth_headers(self.user_a))
        self.assertEqual(del2.status_code, 200)

        # Wishlist giờ trống
        res_empty = self.client.get("/api/wishlist", headers=self._auth_headers(self.user_a))
        self.assertEqual(len(res_empty.json()), 0)

    def test_clear_wishlist(self):
        """Xóa toàn bộ wishlist của user."""
        self.client.post("/api/wishlist", json={"product_id": self.product_1.id}, headers=self._auth_headers(self.user_a))
        self.client.post("/api/wishlist", json={"product_id": self.product_2.id}, headers=self._auth_headers(self.user_a))

        # User B cũng có sản phẩm
        self.client.post("/api/wishlist", json={"product_id": self.product_2.id}, headers=self._auth_headers(self.user_b))

        # User A xóa toàn bộ
        res_clear = self.client.delete("/api/wishlist/clear", headers=self._auth_headers(self.user_a))
        self.assertEqual(res_clear.status_code, 200)
        self.assertEqual(res_clear.json()["deleted_count"], 2)

        # Wishlist của User A trống, của User B vẫn còn
        self.assertEqual(len(self.client.get("/api/wishlist", headers=self._auth_headers(self.user_a)).json()), 0)
        self.assertEqual(len(self.client.get("/api/wishlist", headers=self._auth_headers(self.user_b)).json()), 1)

    # -------------------------------------------------------------
    # 6. TIÊU CHÍ: Xác thực User (Authentication Header)
    # -------------------------------------------------------------
    def test_unauthorized_user(self):
        """Thiếu JWT hoặc token không hợp lệ -> 401 Unauthorized."""
        response = self.client.get("/api/wishlist", headers={"X-User-Id": "99999"})
        self.assertEqual(response.status_code, 401)
        self.assertIn("đăng nhập", response.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()

