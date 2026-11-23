"""API Router cho Hủy đơn hàng và Giải phóng tồn kho.
Cung cấp các endpoint:
- POST /customer/orders/{order_code}/cancel: Khách hàng hủy đơn hàng của mình kèm lý do.
- POST /orders/{order_code}/cancel: Alias endpoint hủy đơn.
- POST /orders/cancel: Hủy đơn qua request body có order_code và reason.
- GET /customer/orders/{order_code}/cancellation: Xem thông tin và lý do hủy đơn.

Tiêu chí chấp nhận:
1. Chỉ hủy đơn ở trạng thái cho phép (PENDING, CONFIRMED).
2. Lưu lý do hủy.
3. Giải phóng/hoàn tồn đúng một lần.
4. Đơn đã giao (DELIVERED) không bị hủy trái quy tắc.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.crud.order_cancellation import (
    get_order_cancellation_info,
    process_order_cancellation,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.order_cancellation import (
    CancelOrderByCodeRequest,
    CancelOrderRequest,
    CancelOrderResponse,
    OrderCancellationInfoResponse,
)

# Router chính theo tiền tố /customer/orders
router = APIRouter(prefix="/customer/orders", tags=["Order Cancellation"])

# Router phụ theo tiền tố /orders
orders_cancellation_router = APIRouter(prefix="/orders", tags=["Order Cancellation"])


@router.post(
    "/{order_code}/cancel",
    response_model=CancelOrderResponse,
    summary="Khách hàng hủy đơn hàng của mình",
    description=(
        "Kiểm tra điều kiện hủy, cập nhật trạng thái đơn sang CANCELLED, "
        "giải phóng tồn kho (hoàn tồn đúng 1 lần) và lưu lý do hủy. "
        "Chỉ cho phép hủy khi đơn ở trạng thái PENDING hoặc CONFIRMED. "
        "Đơn đã giao (DELIVERED) không được phép hủy trái quy tắc."
    ),
)
@router.put("/{order_code}/cancel", response_model=CancelOrderResponse, include_in_schema=False)
def cancel_customer_order(
    order_code: str,
    payload: CancelOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CancelOrderResponse:
    return process_order_cancellation(
        db=db,
        order_code_or_id=order_code,
        user_id=current_user.id,
        reason=payload.reason,
        cancelled_by="CUSTOMER",
    )


@router.get(
    "/{order_code}/cancellation",
    response_model=OrderCancellationInfoResponse,
    summary="Xem lý do và thông tin hủy của một đơn hàng",
)
def get_order_cancellation_detail(
    order_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderCancellationInfoResponse:
    cancellation = get_order_cancellation_info(
        db=db,
        order_code_or_id=order_code,
        user_id=current_user.id,
    )
    return OrderCancellationInfoResponse.model_validate(cancellation)


# Endpoints phụ trên orders_cancellation_router
@orders_cancellation_router.post(
    "/{order_code}/cancel",
    response_model=CancelOrderResponse,
    summary="Hủy đơn hàng (Alias /orders/{order_code}/cancel)",
)
def cancel_order_alias(
    order_code: str,
    payload: CancelOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CancelOrderResponse:
    return process_order_cancellation(
        db=db,
        order_code_or_id=order_code,
        user_id=current_user.id,
        reason=payload.reason,
        cancelled_by="CUSTOMER",
    )


@orders_cancellation_router.post(
    "/cancel",
    response_model=CancelOrderResponse,
    summary="Hủy đơn hàng bằng request body (order_code + reason)",
)
def cancel_order_by_body(
    payload: CancelOrderByCodeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CancelOrderResponse:
    return process_order_cancellation(
        db=db,
        order_code_or_id=payload.order_code,
        user_id=current_user.id,
        reason=payload.reason,
        cancelled_by="CUSTOMER",
    )
