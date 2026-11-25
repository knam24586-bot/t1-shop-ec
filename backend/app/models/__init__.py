"""Import toàn bộ SQLAlchemy models để Alembic nhìn thấy schema đầy đủ."""

from app.models.item import Item  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.vendor import Vendor  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.store import Store  # noqa: F401
from app.models.product import Product  # noqa: F401
from app.models.variant import ProductVariant  # noqa: F401
from app.models.product_image import ProductImage  # noqa: F401
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.order import Order  # noqa: F401
from app.models.order_item import OrderItem  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.payment_log import PaymentWebhookLog  # noqa: F401
from app.models.order_status_history import OrderStatusHistory  # noqa: F401
from app.models.order_cancellation import OrderCancellation  # noqa: F401
from app.models.store_order import StoreOrder  # noqa: F401
from app.models.inventory_movement import InventoryMovement  # noqa: F401
from app.models.voucher import Voucher  # noqa: F401
from app.models.wishlist import Wishlist  # noqa: F401
