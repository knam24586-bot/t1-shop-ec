"""API Router cho Khách hàng xem danh sách và chi tiết đơn hàng của mình.
Cung cấp các endpoint:
- GET /customer/orders: Xem danh sách đơn hàng có phân trang (pagination) và lọc theo status.
- GET /customer/orders/{order_code}: Xem chi tiết một đơn hàng cụ thể của khách hàng.

Tiêu chí chấp nhận:
1. Customer chỉ xem đơn thuộc về chính mình (User Isolation qua current_user).
2. Hỗ trợ xem list, chi tiết detail và pagination đầy đủ.
3. Dữ liệu trả về không chứa thông tin nội bộ (không lộ password_hash, payment logs, raw webhook data, secrets).
"""
from __future__ import annotations

import math
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.crud.customer_order import (
    build_customer_order_detail_response,
    build_customer_order_summary_response,
    get_customer_order_detail,
    get_customer_orders_paginated,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.customer_order import (
    CustomerOrderDetailResponse,
    CustomerOrderPaginationResponse,
)

# Router chính với prefix tiêu chuẩn /customer/orders
router = APIRouter(prefix="/customer/orders", tags=["Customer Orders"])

# Router phụ với prefix /orders để thuận tiện tích hợp nếu môi trường mount theo /orders
order_router = APIRouter(prefix="/orders", tags=["Customer Orders"])


def _handle_list_orders(
    page: int,
    limit: int,
    page_size: int | None,
    status_filter: str | None,
    current_user: User,
    db: Session,
) -> CustomerOrderPaginationResponse:
    """Xử lý nghiệp vụ phân trang danh sách đơn hàng của khách hàng."""
    actual_limit = page_size if page_size is not None else limit
    order_tuples, total = get_customer_orders_paginated(
        db=db,
        user_id=current_user.id,
        page=page,
        limit=actual_limit,
        status_filter=status_filter,
    )

    items = [build_customer_order_summary_response(order, payment) for order, payment in order_tuples]
    total_pages = math.ceil(total / actual_limit) if actual_limit > 0 else 0
    has_next = page < total_pages
    has_prev = page > 1 and total > 0

    return CustomerOrderPaginationResponse(
        items=items,
        orders=items,
        total=total,
        total_orders=total,
        page=page,
        limit=actual_limit,
        page_size=actual_limit,
        total_pages=total_pages,
        has_next=has_next,
        has_prev=has_prev,
    )


def _handle_get_order_detail(
    order_code: str,
    current_user: User,
    db: Session,
) -> CustomerOrderDetailResponse:
    """Xử lý nghiệp vụ xem chi tiết đơn hàng của khách hàng."""
    order, payment = get_customer_order_detail(
        db=db,
        user_id=current_user.id,
        order_code_or_id=order_code,
    )
    return build_customer_order_detail_response(order, payment)


@router.get(
    "",
    response_model=CustomerOrderPaginationResponse,
    summary="Xem danh sách đơn hàng của khách hàng hiện tại (có phân trang)",
    description=(
        "Chỉ hiển thị các đơn hàng thuộc về chính khách hàng đang đăng nhập (X-User-Id). "
        "Hỗ trợ phân trang bằng `page` và `limit` (hoặc `page_size`), lọc theo trạng thái `status`. "
        "Dữ liệu trả về không chứa thông tin nội bộ hệ thống."
    ),
)
@router.get("/my-orders", response_model=CustomerOrderPaginationResponse, include_in_schema=False)
def list_customer_orders(
    page: int = Query(default=1, ge=1, description="Số thứ tự trang (bắt đầu từ 1)"),
    limit: int = Query(default=10, ge=1, le=100, description="Số đơn hàng tối đa trên mỗi trang"),
    page_size: int | None = Query(default=None, ge=1, le=100, description="Alias tương đương cho limit"),
    status: str | None = Query(default=None, description="Lọc theo trạng thái đơn hàng (PENDING, CONFIRMED, ...)", alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerOrderPaginationResponse:
    return _handle_list_orders(page, limit, page_size, status, current_user, db)


@router.get(
    "/{order_code}",
    response_model=CustomerOrderDetailResponse,
    summary="Xem chi tiết một đơn hàng của khách hàng theo mã đơn hoặc id",
    description=(
        "Chỉ người sở hữu đơn hàng mới có quyền xem thông tin. "
        "Nếu đơn không tồn tại hoặc thuộc người khác, trả về 404 Not Found. "
        "Dữ liệu trả về không chứa thông tin nội bộ hệ thống."
    ),
)
@router.get("/detail/{order_code}", response_model=CustomerOrderDetailResponse, include_in_schema=False)
def get_customer_order_detail_endpoint(
    order_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerOrderDetailResponse:
    return _handle_get_order_detail(order_code, current_user, db)


# Đăng ký các endpoint tương đương cho order_router
@order_router.get(
    "/my",
    response_model=CustomerOrderPaginationResponse,
    summary="Xem danh sách đơn hàng của khách hàng (mount dưới /orders/my)",
)
def list_orders_my(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    page_size: int | None = Query(default=None, ge=1, le=100),
    status: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerOrderPaginationResponse:
    return _handle_list_orders(page, limit, page_size, status, current_user, db)


@order_router.get(
    "/customer",
    response_model=CustomerOrderPaginationResponse,
    summary="Xem danh sách đơn hàng của khách hàng (mount dưới /orders/customer)",
)
def list_orders_customer(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    page_size: int | None = Query(default=None, ge=1, le=100),
    status: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerOrderPaginationResponse:
    return _handle_list_orders(page, limit, page_size, status, current_user, db)


@order_router.get(
    "/my/{order_code}",
    response_model=CustomerOrderDetailResponse,
    summary="Xem chi tiết đơn hàng của khách hàng (mount dưới /orders/my/{order_code})",
)
def get_order_my_detail(
    order_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerOrderDetailResponse:
    return _handle_get_order_detail(order_code, current_user, db)
