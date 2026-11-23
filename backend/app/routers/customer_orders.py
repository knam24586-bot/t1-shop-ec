"""Re-export toàn bộ customer order router."""
from app.routers.customer_order import (
    get_customer_order_detail_endpoint,
    list_customer_orders,
    order_router,
    router,
)

__all__ = [
    "get_customer_order_detail_endpoint",
    "list_customer_orders",
    "order_router",
    "router",
]
