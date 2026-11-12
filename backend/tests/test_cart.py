"""Bộ kiểm thử cho SQLAlchemy Model Cart, CartItem và quan hệ Cart/Variant.
Kiểm tra tất cả các tiêu chí chấp nhận:
1. Cart liên kết duy nhất với chủ sở hữu (User 1-1, unique user_id).
2. Cart có trạng thái (status) và timestamp (created_at, updated_at).
3. CartItem liên kết Cart và Variant (ProductVariant).
4. Số lượng CartItem > 0 (kiểm tra cả validation tầng ứng dụng và DB CheckConstraint).
5. Kiểm soát item trùng theo quy tắc gộp giỏ (Cart Merge Rule: tự cộng dồn khi trùng biến thể, UniqueConstraint ở DB).
6. Cascade delete và toàn vẹn dữ liệu quan hệ.
"""
import unittest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from app.db.session import Base
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.models.variant import ProductVariant
from app.models.cart import Cart
from app.models.cart_item import CartItem


class TestCartAndCartItemModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Kiểm tra configure_mappers() không ném lỗi
        configure_mappers()

    def setUp(self):
        # Sử dụng SQLite in-memory để kiểm thử
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        # Tạo sẵn dữ liệu nền tảng: Category -> Product -> Variants -> User
        self.category = Category(name="Áo Đấu T1", slug="ao-dau-t1", status="Active")
        self.session.add(self.category)
        self.session.flush()

        self.product = Product(
            category_id=self.category.id,
            name="Áo T1 CKTG 2026",
            slug="ao-t1-cktg-2026",
            price=Decimal("1200000.00"),
            stock=100,
            status="Published",
        )
        self.session.add(self.product)
        self.session.flush()

        self.variant_m = ProductVariant(
            product_id=self.product.id,
            sku="T1-2026-RED-M",
            color="Red",
            size="M",
            stock=50,
        )
        self.variant_l = ProductVariant(
            product_id=self.product.id,
            sku="T1-2026-RED-L",
            color="Red",
            size="L",
            stock=30,
        )
        self.user = User(
            full_name="Lee Sang-hyeok",
            email="faker@t1.gg",
            password_hash="hashed_pw_faker",
        )
        self.session.add_all([self.variant_m, self.variant_l, self.user])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # -------------------------------------------------------------
    # 1. TIÊU CHÍ: CartItem liên kết Cart và Variant
    # -------------------------------------------------------------
    def test_cart_item_links_cart_and_variant(self):
        """CartItem phải liên kết chính xác tới Cart và ProductVariant."""
        cart = Cart(user=self.user, status="Active")
        self.session.add(cart)
        self.session.commit()

        item = CartItem(cart=cart, variant=self.variant_m, quantity=2)
        self.session.add(item)
        self.session.commit()

        # Kiểm tra truy vấn 2 chiều: CartItem -> Cart và CartItem -> Variant
        queried_item = self.session.scalar(select(CartItem).where(CartItem.id == item.id))
        self.assertIsNotNone(queried_item)
        self.assertEqual(queried_item.cart_id, cart.id)
        self.assertEqual(queried_item.variant_id, self.variant_m.id)
        self.assertEqual(queried_item.variant.sku, "T1-2026-RED-M")
        self.assertEqual(queried_item.variant.size, "M")
        self.assertEqual(queried_item.cart.user.full_name, "Lee Sang-hyeok")

        # Kiểm tra quan hệ ngược từ Variant -> cart_items
        self.assertIn(queried_item, self.variant_m.cart_items)

    # -------------------------------------------------------------
    # 2. TIÊU CHÍ: Số lượng > 0
    # -------------------------------------------------------------
    def test_cart_item_quantity_must_be_positive_python_validation(self):
        """Validation ở mức Model: Không cho phép tạo CartItem với quantity <= 0."""
        cart = Cart(user=self.user)
        self.session.add(cart)
        self.session.commit()

        # Thử gán số lượng = 0
        with self.assertRaises(ValueError) as ctx_zero:
            CartItem(cart=cart, variant_id=self.variant_m.id, quantity=0)
        self.assertIn("lớn hơn 0", str(ctx_zero.exception))

        # Thử gán số lượng âm (< 0)
        with self.assertRaises(ValueError) as ctx_neg:
            CartItem(cart=cart, variant_id=self.variant_m.id, quantity=-5)
        self.assertIn("lớn hơn 0", str(ctx_neg.exception))

        # Thử dùng cart.add_item với quantity <= 0
        with self.assertRaises(ValueError):
            cart.add_item(variant_id=self.variant_m.id, quantity=0)

    def test_cart_item_quantity_must_be_positive_db_constraint(self):
        """DB CheckConstraint: Bắt buộc quantity > 0 khi insert vào Database."""
        cart = Cart(user=self.user)
        self.session.add(cart)
        self.session.commit()

        # Bỏ qua validation Python bằng cách sửa thuộc tính nội bộ để kiểm tra DB CheckConstraint
        item = CartItem(cart_id=cart.id, variant_id=self.variant_m.id)
        item.__dict__["quantity"] = 0
        self.session.add(item)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    # -------------------------------------------------------------
    # 3. TIÊU CHÍ: Kiểm soát item trùng theo quy tắc gộp giỏ
    # -------------------------------------------------------------
    def test_cart_merge_rule_on_add_item(self):
        """Quy tắc gộp giỏ: Khi thêm cùng một variant vào giỏ, số lượng được cộng dồn thay vì tạo dòng mới."""
        cart = Cart(user=self.user)
        self.session.add(cart)
        self.session.commit()

        # Lần 1: Thêm 2 áo size M vào giỏ
        item1 = cart.add_item(variant_id=self.variant_m.id, quantity=2)
        self.session.commit()
        self.assertEqual(len(cart.items), 1)
        self.assertEqual(cart.items[0].quantity, 2)

        # Lần 2: Thêm tiếp 3 áo size M (trùng biến thể) -> Phải tự gộp thành 5 áo, vẫn chỉ có 1 dòng
        item2 = cart.add_item(variant_id=self.variant_m.id, quantity=3)
        self.session.commit()
        self.assertEqual(len(cart.items), 1)
        self.assertEqual(cart.items[0].id, item1.id)
        self.assertEqual(cart.items[0].quantity, 5)

        # Lần 3: Thêm áo size L (khác biến thể) -> Tạo thêm dòng mới trong giỏ
        cart.add_item(variant_id=self.variant_l.id, quantity=1)
        self.session.commit()
        self.assertEqual(len(cart.items), 2)

    def test_cart_merge_multiple_items_from_guest_cart(self):
        """Quy tắc gộp giỏ: Gộp các món từ giỏ hàng khác (ví dụ giỏ hàng vãng lai khi user login)."""
        cart = Cart(user_id=self.user.id)
        self.session.add(cart)
        self.session.flush()
        cart.add_item(variant_id=self.variant_m.id, quantity=1)
        self.session.commit()

        # Giả lập danh sách item từ giỏ hàng khác mang sang
        guest_items = [
            CartItem(cart_id=999, variant_id=self.variant_m.id, quantity=4),
            CartItem(cart_id=999, variant_id=self.variant_l.id, quantity=2),
        ]
        cart.merge_cart(guest_items)
        self.session.commit()

        # Biến thể M: ban đầu có 1, gộp thêm 4 = 5
        item_m = next(i for i in cart.items if i.variant_id == self.variant_m.id)
        self.assertEqual(item_m.quantity, 5)

        # Biến thể L: chưa có, thêm mới = 2
        item_l = next(i for i in cart.items if i.variant_id == self.variant_l.id)
        self.assertEqual(item_l.quantity, 2)

    def test_cart_item_duplicate_prevented_by_unique_constraint(self):
        """Ràng buộc DB (uk_cart_item_cart_variant): Chặn triệt để 2 bản ghi cùng (cart_id, variant_id)."""
        cart = Cart(user=self.user)
        self.session.add(cart)
        self.session.commit()

        item1 = CartItem(cart_id=cart.id, variant_id=self.variant_m.id, quantity=1)
        self.session.add(item1)
        self.session.commit()

        # Cố ý thêm trực tiếp 1 bản ghi trùng variant_id mà không dùng hàm add_item
        item2 = CartItem(cart_id=cart.id, variant_id=self.variant_m.id, quantity=2)
        self.session.add(item2)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    # -------------------------------------------------------------
    # 4. TIÊU CHÍ: Cascade Delete và Ràng buộc chủ sở hữu duy nhất của Cart
    # -------------------------------------------------------------
    def test_cart_cascade_delete_items(self):
        """Khi xoá Cart, toàn bộ CartItem bên trong phải tự động bị xoá theo (cascade all, delete-orphan)."""
        cart = Cart(user_id=self.user.id)
        self.session.add(cart)
        self.session.flush()
        cart.add_item(variant_id=self.variant_m.id, quantity=2)
        cart.add_item(variant_id=self.variant_l.id, quantity=1)
        self.session.commit()

        self.assertEqual(len(self.session.scalars(select(CartItem)).all()), 2)

        # Xoá giỏ hàng
        self.session.delete(cart)
        self.session.commit()

        # Kiểm tra CartItem đã bị dọn dẹp sạch
        remaining_items = self.session.scalars(select(CartItem)).all()
        self.assertEqual(len(remaining_items), 0)

    def test_cart_unique_owner(self):
        """Cart liên kết duy nhất với chủ sở hữu (User 1-1)."""
        cart1 = Cart(user_id=self.user.id, status="Active")
        self.session.add(cart1)
        self.session.commit()

        # Thử tạo thêm cart thứ 2 cho cùng 1 user -> Phải bị chặn
        cart2 = Cart(user_id=self.user.id, status="Active")
        self.session.add(cart2)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()


if __name__ == "__main__":
    unittest.main()
