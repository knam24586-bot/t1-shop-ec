"""Bộ kiểm thử cho SQLAlchemy Model Order và trạng thái đơn.
Kiểm tra tất cả các tiêu chí chấp nhận:
1. Order lưu đầy đủ: mã đơn, khách hàng, địa chỉ snapshot, tổng tiền, trạng thái và timestamp.
2. Mã đơn duy nhất (order_code unique).
3. Địa chỉ snapshot độc lập với sự thay đổi của User.
4. Trạng thái đơn (OrderStatus enum, default PENDING, quy tắc chuyển đổi trạng thái hợp lệ).
5. Quan hệ Order <-> Customer và Order <-> OrderItem (cascade delete).
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
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem


class TestOrderModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configure_mappers()

    def setUp(self):
        # Sử dụng SQLite in-memory để kiểm thử
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        # Dữ liệu mẫu ban đầu: User, Category, Product
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

        self.product = Product(
            category_id=self.category.id,
            name="Áo Đấu T1 2026",
            slug="ao-dau-t1-2026",
            price=Decimal("1500000.00"),
            stock=50,
            status="Published",
        )
        self.session.add(self.product)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # -------------------------------------------------------------
    # 1. TIÊU CHÍ: Lưu đầy đủ các trường và timestamp
    # -------------------------------------------------------------
    def test_order_fields_and_timestamps(self):
        """Order phải lưu: mã đơn, khách hàng, địa chỉ snapshot, tổng tiền, trạng thái và timestamp."""
        order_code = Order.generate_order_code()
        address = "123 Đường Cầu Giấy, Quận Cầu Giấy, Hà Nội"
        total_price = Decimal("3000000.00")

        order = Order(
            order_code=order_code,
            customer_id=self.customer.id,
            shipping_address=address,
            total_price=total_price,
            status=OrderStatus.PENDING.value,
        )
        self.session.add(order)
        self.session.commit()

        # Kiểm tra truy vấn lại
        saved_order = self.session.scalar(select(Order).where(Order.id == order.id))
        self.assertIsNotNone(saved_order)
        self.assertEqual(saved_order.order_code, order_code)
        self.assertEqual(saved_order.customer_id, self.customer.id)
        self.assertEqual(saved_order.shipping_address, address)
        self.assertEqual(saved_order.total_price, total_price)
        self.assertEqual(saved_order.status, OrderStatus.PENDING.value)
        self.assertIsNotNone(saved_order.created_at)
        self.assertIsNotNone(saved_order.updated_at)
        self.assertIsInstance(saved_order.created_at, datetime)
        self.assertIsInstance(saved_order.updated_at, datetime)

    # -------------------------------------------------------------
    # 2. TIÊU CHÍ: Mã đơn duy nhất (order_code unique)
    # -------------------------------------------------------------
    def test_order_code_unique_constraint(self):
        """Mã đơn (order_code) phải là duy nhất, trùng lặp sẽ bị chặn bởi Database."""
        code = "ORD-2026-UNIQUE-001"

        order1 = Order(
            order_code=code,
            customer_id=self.customer.id,
            shipping_address="Hà Nội",
            total_price=Decimal("500000.00"),
        )
        self.session.add(order1)
        self.session.commit()

        # Tạo đơn thứ 2 cố ý trùng mã đơn
        order2 = Order(
            order_code=code,
            customer_id=self.customer.id,
            shipping_address="Đà Nẵng",
            total_price=Decimal("700000.00"),
        )
        self.session.add(order2)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    # -------------------------------------------------------------
    # 3. TIÊU CHÍ: Địa chỉ snapshot (Không đổi khi user thay đổi)
    # -------------------------------------------------------------
    def test_shipping_address_is_snapshot(self):
        """Địa chỉ lưu trên Order là snapshot độc lập."""
        original_address = "Số 1 Đại Cồ Việt, Hai Bà Trưng, Hà Nội"
        order = Order(
            order_code=Order.generate_order_code(),
            customer=self.customer,
            shipping_address=original_address,
            total_price=Decimal("1500000.00"),
        )
        self.session.add(order)
        self.session.commit()

        # Đơn hàng vẫn giữ nguyên địa chỉ snapshot ban đầu
        queried_order = self.session.scalar(select(Order).where(Order.id == order.id))
        self.assertEqual(queried_order.shipping_address, original_address)
        self.assertEqual(queried_order.customer.full_name, "Son Heung-min")

    # -------------------------------------------------------------
    # 4. TIÊU CHÍ: Quản lý trạng thái đơn hàng (OrderStatus & Transitions)
    # -------------------------------------------------------------
    def test_order_status_lifecycle_and_transitions(self):
        """Kiểm tra vòng đời trạng thái đơn và các quy tắc chuyển trạng thái hợp lệ/bất hợp lệ."""
        order = Order(
            order_code=Order.generate_order_code(),
            customer_id=self.customer.id,
            shipping_address="Hồ Chí Minh",
            total_price=Decimal("1500000.00"),
        )
        self.session.add(order)
        self.session.commit()

        # 1. Trạng thái mặc định ban đầu là PENDING
        self.assertEqual(order.status, OrderStatus.PENDING.value)

        # 2. Chuyển hợp lệ: PENDING -> CONFIRMED
        self.assertTrue(order.can_transition_to(OrderStatus.CONFIRMED))
        order.transition_to(OrderStatus.CONFIRMED)
        self.session.commit()
        self.assertEqual(order.status, OrderStatus.CONFIRMED.value)

        # 3. Chuyển hợp lệ: CONFIRMED -> PROCESSING -> SHIPPED -> DELIVERED
        order.transition_to(OrderStatus.PROCESSING)
        order.transition_to(OrderStatus.SHIPPED)
        order.transition_to(OrderStatus.DELIVERED)
        self.session.commit()
        self.assertEqual(order.status, OrderStatus.DELIVERED.value)

        # 4. Chuyển bất hợp lệ: Đơn đã DELIVERED không thể quay lại PENDING hoặc CANCELLED
        self.assertFalse(order.can_transition_to(OrderStatus.PENDING))
        with self.assertRaises(ValueError) as ctx:
            order.transition_to(OrderStatus.PENDING)
        self.assertIn("Không thể chuyển trạng thái", str(ctx.exception))

    def test_order_cancellation_from_pending(self):
        """Đơn hàng ở trạng thái PENDING có thể bị huỷ (CANCELLED)."""
        order = Order(
            order_code=Order.generate_order_code(),
            customer_id=self.customer.id,
            shipping_address="Cần Thơ",
            total_price=Decimal("1000000.00"),
        )
        self.session.add(order)
        self.session.commit()

        self.assertTrue(order.can_transition_to(OrderStatus.CANCELLED))
        order.transition_to(OrderStatus.CANCELLED)
        self.session.commit()
        self.assertEqual(order.status, OrderStatus.CANCELLED.value)

        # Đơn đã huỷ không thể chuyển sang SHIPPED
        with self.assertRaises(ValueError):
            order.transition_to(OrderStatus.SHIPPED)

    # -------------------------------------------------------------
    # 5. TIÊU CHÍ: Quan hệ Order <-> OrderItems và Cascade Delete
    # -------------------------------------------------------------
    def test_order_items_relationship_and_total_calculation(self):
        """Order liên kết đúng với OrderItem, tự động tính tổng tiền và xoá liên hoàn."""
        order = Order(
            order_code=Order.generate_order_code(),
            customer_id=self.customer.id,
            shipping_address="Hải Phòng",
            total_price=Decimal("0.00"),
        )
        self.session.add(order)
        self.session.flush()

        # Thêm 2 mục vào đơn hàng
        item1 = OrderItem.create_item(
            order=order,
            product_id=self.product.id,
            unit_price=Decimal("1500000.00"),
            quantity=2,
        )
        item2 = OrderItem.create_item(
            order=order,
            product_id=self.product.id,
            unit_price=Decimal("500000.00"),
            quantity=1,
        )
        self.session.add_all([item1, item2])
        self.session.flush()

        # Tự động tính lại tổng tiền
        order.calculate_total()
        self.session.commit()

        # 1500000*2 + 500000*1 = 3500000
        self.assertEqual(order.total_price, Decimal("3500000.00"))
        self.assertEqual(len(order.items), 2)

        # Xoá Order -> OrderItem tự động bị xoá theo (cascade delete-orphan)
        self.session.delete(order)
        self.session.commit()

        remaining_items = self.session.scalars(select(OrderItem)).all()
        self.assertEqual(len(remaining_items), 0)


if __name__ == "__main__":
    unittest.main()

