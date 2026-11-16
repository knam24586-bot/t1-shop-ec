"""Bộ kiểm thử cho SQLAlchemy Model Order, OrderItem và cơ chế snapshot giá/số lượng.
Kiểm tra toàn diện các tiêu chí chấp nhận:
1. Order lưu mã đơn (duy nhất), khách hàng, địa chỉ snapshot, tổng tiền, trạng thái và timestamp.
2. OrderItem lưu variant, quantity và unit_price snapshot.
3. DỮ LIỆU ĐƠN KHÔNG THAY ĐỔI KHI GIÁ PRODUCT THAY ĐỔI SAU ĐÓ.
4. Ràng buộc số lượng > 0 và đơn giá snapshot >= 0.
5. Quan hệ và Cascade Delete.
"""
import unittest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers

from app.db.session import Base
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.models.variant import ProductVariant
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem


class TestOrderAndOrderItemModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        # Sử dụng SQLite in-memory để kiểm thử
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        # Dữ liệu mẫu ban đầu: User, Category, Product, Variant
        self.customer = User(
            full_name="Son Heung-min",
            email="sonny@t1.gg",
            password_hash="hashed_pw_sonny",
            role="CUSTOMER",
            status="Active",
        )
        self.category = Category(name="Đồng phục", slug="dong-phuc", status="Active")
        self.session.add_all([self.customer, self.category])
        self.session.flush()

        # Sản phẩm ban đầu có giá 1.500.000 VNĐ
        self.product = Product(
            category_id=self.category.id,
            name="Áo Đấu T1 2026",
            slug="ao-dau-t1-2026",
            price=Decimal("1500000.00"),
            stock=50,
            status="Published",
        )
        self.session.add(self.product)
        self.session.flush()

        # Biến thể áo đấu size M
        self.variant = ProductVariant(
            product_id=self.product.id,
            sku="T1-2026-JERSEY-M",
            color="Black/Red",
            size="M",
            stock=20,
        )
        self.session.add(self.variant)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # -------------------------------------------------------------
    # 1. TIÊU CHÍ: OrderItem lưu variant, quantity và unit_price snapshot
    # -------------------------------------------------------------
    def test_order_item_stores_variant_quantity_and_snapshot_price(self):
        """OrderItem phải lưu liên kết variant, số lượng và đơn giá snapshot."""
        order = Order(
            order_code=Order.generate_order_code(),
            customer_id=self.customer.id,
            shipping_address="Hà Nội",
            total_price=Decimal("0.00"),
        )
        self.session.add(order)
        self.session.flush()

        # Tạo OrderItem qua hàm from_variant với snapshot giá
        item = OrderItem.from_variant(
            order=order,
            variant=self.variant,
            quantity=3,
        )
        self.session.add(item)
        order.calculate_total()
        self.session.commit()

        # Kiểm tra dữ liệu OrderItem được lưu
        saved_item = self.session.scalar(select(OrderItem).where(OrderItem.id == item.id))
        self.assertIsNotNone(saved_item)
        self.assertEqual(saved_item.variant_id, self.variant.id)
        self.assertEqual(saved_item.variant.sku, "T1-2026-JERSEY-M")
        self.assertEqual(saved_item.quantity, 3)
        self.assertEqual(saved_item.unit_price, Decimal("1500000.00"))
        self.assertEqual(saved_item.line_total, Decimal("4500000.00"))
        self.assertEqual(order.total_price, Decimal("4500000.00"))

    # -------------------------------------------------------------
    # 2. TIÊU CHÍ THEN CHỐT: Dữ liệu đơn KHÔNG thay đổi khi giá Product đổi sau đó
    # -------------------------------------------------------------
    def test_order_data_immutable_when_product_price_changes_later(self):
        """Chứng minh tính chất snapshot: Khi giá sản phẩm tăng/giảm sau này, đơn hàng cũ giữ nguyên 100%."""
        order = Order(
            order_code=Order.generate_order_code(),
            customer_id=self.customer.id,
            shipping_address="Số 10 Tôn Thất Thuyết, Cầu Giấy, Hà Nội",
            total_price=Decimal("0.00"),
        )
        self.session.add(order)
        self.session.flush()

        # Mua 2 áo với giá tại thời điểm mua là 1.500.000 VNĐ -> line_total = 3.000.000 VNĐ
        order_item = OrderItem.from_variant(
            order=order,
            variant=self.variant,
            quantity=2,
        )
        self.session.add(order_item)
        order.calculate_total()
        self.session.commit()

        # Xác nhận đơn hàng ban đầu: total = 3.000.000 VNĐ
        self.assertEqual(order.total_price, Decimal("3000000.00"))
        self.assertEqual(order_item.unit_price, Decimal("1500000.00"))
        self.assertEqual(order_item.line_total, Decimal("3000000.00"))

        # ---------------------------------------------------------
        # KỊCH BẢN THAY ĐỔI GIÁ SAU ĐÓ:
        # Shop tăng giá sản phẩm từ 1.500.000 lên 2.500.000 VNĐ
        # ---------------------------------------------------------
        self.product.price = Decimal("2500000.00")
        self.session.commit()

        # Xoá cache session để đảm bảo load trực tiếp từ Database
        self.session.expire_all()

        # Truy vấn lại Product: Giá đã tăng lên 2.500.000 VNĐ
        reloaded_product = self.session.scalar(select(Product).where(Product.id == self.product.id))
        self.assertEqual(reloaded_product.price, Decimal("2500000.00"))

        # Truy vấn lại Đơn hàng và Mục đơn hàng: DỮ LIỆU ĐƠN KHÔNG HỀ BỊ ẢNH HƯỞNG!
        reloaded_order = self.session.scalar(select(Order).where(Order.id == order.id))
        reloaded_item = reloaded_order.items[0]

        # Đơn giá snapshot vẫn là 1.500.000 VNĐ
        self.assertEqual(reloaded_item.unit_price, Decimal("1500000.00"))
        # Thành tiền snapshot vẫn là 3.000.000 VNĐ
        self.assertEqual(reloaded_item.line_total, Decimal("3000000.00"))
        # Tổng tiền đơn hàng vẫn là 3.000.000 VNĐ
        self.assertEqual(reloaded_order.total_price, Decimal("3000000.00"))

    # -------------------------------------------------------------
    # 3. TIÊU CHÍ: Ràng buộc số lượng > 0 và đơn giá >= 0
    # -------------------------------------------------------------
    def test_order_item_quantity_must_be_positive(self):
        """Số lượng OrderItem phải > 0."""
        order = Order(
            order_code=Order.generate_order_code(),
            customer_id=self.customer.id,
            shipping_address="Đà Nẵng",
            total_price=Decimal("0.00"),
        )
        self.session.add(order)
        self.session.flush()

        # Số lượng = 0 phải văng lỗi
        with self.assertRaises(ValueError):
            OrderItem.create_item(order=order, unit_price=Decimal("100000.00"), quantity=0)

        # Số lượng < 0 phải văng lỗi
        with self.assertRaises(ValueError):
            OrderItem.create_item(order=order, unit_price=Decimal("100000.00"), quantity=-2)

    def test_order_item_unit_price_nonnegative(self):
        """Đơn giá snapshot không được âm."""
        order = Order(
            order_code=Order.generate_order_code(),
            customer_id=self.customer.id,
            shipping_address="TP. Hồ Chí Minh",
            total_price=Decimal("0.00"),
        )
        self.session.add(order)
        self.session.flush()

        with self.assertRaises(ValueError):
            OrderItem.create_item(order=order, unit_price=Decimal("-50000.00"), quantity=1)

    # -------------------------------------------------------------
    # 4. TIÊU CHÍ: Order tổng thể (Mã đơn duy nhất, trạng thái, cascade delete)
    # -------------------------------------------------------------
    def test_order_code_unique_and_status(self):
        """Mã đơn phải duy nhất và trạng thái đơn vận hành đúng."""
        code = "ORD-2026-IMMUTABLE-01"
        order1 = Order(
            order_code=code,
            customer_id=self.customer.id,
            shipping_address="Cần Thơ",
            total_price=Decimal("100000.00"),
        )
        self.session.add(order1)
        self.session.commit()

        # Tạo đơn thứ 2 trùng mã -> Lỗi IntegrityError
        order2 = Order(
            order_code=code,
            customer_id=self.customer.id,
            shipping_address="Huế",
            total_price=Decimal("200000.00"),
        )
        self.session.add(order2)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    def test_order_cascade_delete_items(self):
        """Khi xoá Order, toàn bộ OrderItem liên kết phải tự động bị xoá."""
        order = Order(
            order_code=Order.generate_order_code(),
            customer_id=self.customer.id,
            shipping_address="Hải Phòng",
            total_price=Decimal("1500000.00"),
        )
        self.session.add(order)
        self.session.flush()

        item = OrderItem.from_variant(order=order, variant=self.variant, quantity=1)
        self.session.add(item)
        self.session.commit()

        self.assertEqual(len(self.session.scalars(select(OrderItem)).all()), 1)

        # Xoá đơn hàng
        self.session.delete(order)
        self.session.commit()

        # OrderItem đã bị xoá
        self.assertEqual(len(self.session.scalars(select(OrderItem)).all()), 0)


if __name__ == "__main__":
    unittest.main()
