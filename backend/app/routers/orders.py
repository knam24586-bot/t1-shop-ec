"""Checkout and customer-owned order endpoints."""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.product import Product
from app.models.user import User
from app.models.variant import ProductVariant
from app.schemas.order import (
    CheckoutRequest,
    OrderItemResponse,
    OrderResponse,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _response(order: Order, payment: Payment) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        order_code=order.order_code,
        status=order.status,
        total_price=order.total_price,
        shipping_address=order.shipping_address,
        payment_method=payment.method,
        payment_status=payment.status,
        created_at=order.created_at,
        items=[
            OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                variant_id=item.variant_id,
                product_name=item.product.name if item.product else None,
                sku=item.variant.sku if item.variant else None,
                unit_price=item.unit_price,
                quantity=item.quantity,
                line_total=item.line_total,
            )
            for item in order.items
        ],
    )


@router.post("/checkout", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderResponse:
    cart = db.scalar(
        select(Cart).where(Cart.user_id == current_user.id).with_for_update()
    )
    if cart is None:
        raise HTTPException(status_code=400, detail="Giỏ hàng đang trống.")

    cart_items = list(
        db.scalars(
            select(CartItem)
            .where(CartItem.cart_id == cart.id)
            .order_by(CartItem.variant_id)
            .with_for_update()
        )
    )
    if not cart_items:
        raise HTTPException(status_code=400, detail="Giỏ hàng đang trống.")

    quantities_by_product: dict[int, int] = defaultdict(int)
    variants: dict[int, ProductVariant] = {}
    for cart_item in cart_items:
        variant = db.scalar(
            select(ProductVariant)
            .where(ProductVariant.id == cart_item.variant_id)
            .with_for_update()
        )
        if variant is None:
            raise HTTPException(status_code=409, detail="Một sản phẩm trong giỏ không còn tồn tại.")
        variants[variant.id] = variant
        quantities_by_product[variant.product_id] += cart_item.quantity

    products: dict[int, Product] = {}
    for product_id in sorted(quantities_by_product):
        product = db.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        if product is None or product.status != "Published":
            raise HTTPException(
                status_code=409,
                detail="Một sản phẩm trong giỏ hiện không được bán.",
            )
        if product.stock < quantities_by_product[product_id]:
            raise HTTPException(
                status_code=409,
                detail=f"Sản phẩm '{product.name}' không đủ tồn kho.",
            )
        products[product_id] = product

    for variant in variants.values():
        matching_item = next(item for item in cart_items if item.variant_id == variant.id)
        if variant.stock < matching_item.quantity:
            raise HTTPException(
                status_code=409,
                detail=f"Biến thể '{variant.sku}' không đủ tồn kho.",
            )

    order = Order(
        order_code=Order.generate_order_code(),
        customer_id=current_user.id,
        shipping_address=payload.shipping_address,
        status="PENDING",
    )
    for cart_item in cart_items:
        variant = variants[cart_item.variant_id]
        product = products[variant.product_id]
        OrderItem.from_variant(
            order,
            variant,
            quantity=cart_item.quantity,
            unit_price=product.price,
        )
        variant.stock -= cart_item.quantity
    for product_id, quantity in quantities_by_product.items():
        products[product_id].stock -= quantity

    order.calculate_total()
    if order.total_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tổng tiền đơn hàng phải lớn hơn 0 để tạo thanh toán COD.",
        )
    db.add(order)
    db.flush()
    payment = Payment(
        order_id=order.id,
        method=PaymentMethod.COD.value,
        amount=order.total_price,
        status=PaymentStatus.PENDING.value,
        transaction_reference=Payment.generate_transaction_ref(
            PaymentMethod.COD, order.id
        ),
    )
    db.add(payment)
    for cart_item in cart_items:
        db.delete(cart_item)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(order)
    db.refresh(payment)
    return _response(order, payment)


@router.get("/{order_id}", response_model=OrderResponse)
def read_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderResponse:
    order = db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.customer_id == current_user.id,
        )
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng.")
    payment = db.scalar(
        select(Payment)
        .where(Payment.order_id == order.id)
        .order_by(Payment.attempt_number.desc())
    )
    if payment is None:
        raise HTTPException(status_code=500, detail="Đơn hàng thiếu thông tin thanh toán.")
    return _response(order, payment)
