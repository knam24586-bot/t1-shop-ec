from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.errors import register_middleware_and_handlers
from app.routers import (
    cart,
    categories,
    customer_order,
    order,
    order_cancellation,
    payment,
    vendor_order,
    voucher,
    wishlist,
)
from app.routers.auth import router as auth_router
from app.routers.inventory import router as inventory_router
from app.routers.products import router as products_router
from app.routers.stores import router as stores_router

app = FastAPI(title=settings.APP_NAME)

register_middleware_and_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(products_router)
app.include_router(stores_router)
app.include_router(vendor_order.store_orders_router, prefix="/api")
app.include_router(inventory_router)
app.include_router(cart.router, prefix="/api")
app.include_router(wishlist.router, prefix="/api")
app.include_router(customer_order.order_router, prefix="/api")
app.include_router(order_cancellation.orders_cancellation_router, prefix="/api")
app.include_router(order.router, prefix="/api")
app.include_router(customer_order.router, prefix="/api")
app.include_router(order_cancellation.router, prefix="/api")
app.include_router(payment.router, prefix="/api")
app.include_router(voucher.router, prefix="/api")
app.include_router(vendor_order.router, prefix="/api")

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
