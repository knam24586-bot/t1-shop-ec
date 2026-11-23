"""CRUD và nghiệp vụ truy vấn đơn hàng của khách hàng (Customer Orders).
Đảm bảo:
1. Customer chỉ xem được đơn hàng thuộc về chính mình (Isolation by customer_id).
2. Hỗ trợ xem danh sách (list) có phân trang (pagination) và lọc theo trạng thái.
3. Hỗ trợ xem chi tiết (detail) đơn hàng theo order_code hoặc id.
4. Dữ liệu trả về được chuẩn hóa và loại bỏ hoàn toàn các thông tin nhạy cảm,
   thông tin nội bộ (không chứa password_hash, internal audit logs, webhook payloads,
   ip_address, secret credentials).
"""
from __future__ import annotations

from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.schemas.customer_order import (
    CustomerOrderDetailResponse,
    CustomerOrderItemResponse,
    CustomerOrderPaymentResponse,
    CustomerOrderSummaryResponse,
)


def build_customer_order_item_response(item: OrderItem) -> CustomerOrderItemResponse:
    """Chuyển đổi OrderItem thành CustomerOrderItemResponse an toàn cho khách hàng."""
    product_name: str | None = None
    sku: str | None = None
    color: str | None = None
    size: str | None = None
    image_url: str | None = None

    if item.variant:
        sku = item.variant.sku
        color = item.variant.color
        size = item.variant.size
    if item.product:
        product_name = item.product.name
        image_url = item.product.image_url

    return CustomerOrderItemResponse(
        id=item.id,
        product_id=item.product_id,
        variant_id=item.variant_id,
        product_name=product_name,
        sku=sku,
        color=color,
        size=size,
        image_url=image_url,
        unit_price=Decimal(str(item.unit_price)),
        quantity=item.quantity,
        line_total=Decimal(str(item.line_total)),
    )


def build_customer_payment_response(payment: Payment | None) -> CustomerOrderPaymentResponse | None:
    """Chuyển đổi Payment thành thông tin công khai cho khách hàng.
    Tuyệt đối không kèm webhook logs, ip_address, gateway raw payload hay secrets.
    """
    if payment is None:
        return None

    return CustomerOrderPaymentResponse(
        method=payment.method,
        amount=Decimal(str(payment.amount)),
        status=payment.status,
        transaction_reference=payment.transaction_reference,
    )


def build_customer_order_summary_response(
    order: Order, payment: Payment | None = None
) -> CustomerOrderSummaryResponse:
    """Chuyển đổi Order thành CustomerOrderSummaryResponse phục vụ danh sách phân trang."""
    items_resp = [build_customer_order_item_response(it) for it in order.items]
    total_items = sum(it.quantity for it in order.items)
    payment_resp = build_customer_payment_response(payment)

    return CustomerOrderSummaryResponse(
        id=order.id,
        order_code=order.order_code,
        total_price=Decimal(str(order.total_price)),
        shipping_address=order.shipping_address,
        status=order.status,
        created_at=order.created_at,
        updated_at=order.updated_at,
        total_items=total_items,
        items=items_resp,
        payment=payment_resp,
    )


def build_customer_order_detail_response(
    order: Order, payment: Payment | None = None
) -> CustomerOrderDetailResponse:
    """Chuyển đổi Order thành CustomerOrderDetailResponse phục vụ xem chi tiết đơn hàng."""
    items_resp = [build_customer_order_item_response(it) for it in order.items]
    total_items = sum(it.quantity for it in order.items)
    payment_resp = build_customer_payment_response(payment)

    return CustomerOrderDetailResponse(
        id=order.id,
        order_code=order.order_code,
        total_price=Decimal(str(order.total_price)),
        shipping_address=order.shipping_address,
        status=order.status,
        created_at=order.created_at,
        updated_at=order.updated_at,
        total_items=total_items,
        items=items_resp,
        payment=payment_resp,
    )


def get_customer_orders_paginated(
    db: Session,
    user_id: int,
    page: int = 1,
    limit: int = 10,
    status_filter: str | None = None,
) -> tuple[list[tuple[Order, Payment | None]], int]:
    """Lấy danh sách đơn hàng có phân trang thuộc về user_id hiện tại.
    - Customer chỉ xem đơn thuộc về mình (Order.customer_id == user_id).
    - Hỗ trợ lọc theo trạng thái nếu có.
    - Sắp xếp đơn mới nhất lên đầu (created_at DESC, id DESC).
    - Trả về danh sách (Order, Payment | None) và tổng số lượng đơn hàng thỏa mãn.
    """
    if page < 1:
        page = 1
    if limit < 1:
        limit = 10

    # 1. Đếm tổng số đơn hàng của khách hàng
    count_stmt = select(func.count(Order.id)).where(Order.customer_id == user_id)
    if status_filter and status_filter.strip():
        count_stmt = count_stmt.where(Order.status == status_filter.strip().upper())
    total = db.scalar(count_stmt) or 0

    if total == 0:
        return [], 0

    # 2. Truy vấn danh sách đơn hàng theo phân trang
    offset = (page - 1) * limit
    stmt = (
        select(Order)
        .where(Order.customer_id == user_id)
    )
    if status_filter and status_filter.strip():
        stmt = stmt.where(Order.status == status_filter.strip().upper())

    stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).offset(offset).limit(limit)
    orders = list(db.scalars(stmt))

    # 3. Lấy thông tin thanh toán mới nhất cho từng đơn hàng
    results: list[tuple[Order, Payment | None]] = []
    for ord_obj in orders:
        payment = db.scalar(
            select(Payment)
            .where(Payment.order_id == ord_obj.id)
            .order_by(Payment.attempt_number.desc(), Payment.id.desc())
            .limit(1)
        )
        results.append((ord_obj, payment))

    return results, total


def get_customer_order_detail(
    db: Session,
    user_id: int,
    order_code_or_id: str | int,
) -> tuple[Order, Payment | None]:
    """Lấy chi tiết đơn hàng cho khách hàng theo order_code hoặc id.
    - Tuyệt đối chỉ trả về nếu đơn hàng thuộc về user_id hiện tại.
    - Nếu đơn hàng không tồn tại hoặc thuộc về người khác -> trả về 404 Not Found
      (không để lộ sự tồn tại của đơn hàng người khác).
    """
    identifier_str = str(order_code_or_id).strip()
    if not identifier_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã đơn hàng không hợp lệ.",
        )

    # Điều kiện tìm kiếm: theo order_code hoặc id số
    if identifier_str.isdigit():
        cond = (Order.id == int(identifier_str)) | (Order.order_code == identifier_str)
    else:
        cond = (Order.order_code == identifier_str)

    # Tìm đơn thuộc chính user_id
    stmt = select(Order).where(cond, Order.customer_id == user_id)
    order = db.scalar(stmt)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng '{identifier_str}'.",
        )

    # Lấy thông tin thanh toán mới nhất của đơn hàng
    payment = db.scalar(
        select(Payment)
        .where(Payment.order_id == order.id)
        .order_by(Payment.attempt_number.desc(), Payment.id.desc())
        .limit(1)
    )
    return order, payment
