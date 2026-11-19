"""API Router cho Đơn hàng (Orders) và Tạo đơn COD.
Cung cấp các endpoint:
- POST /orders/cod: Tạo đơn hàng COD, kiểm tra tồn kho và lưu trong transaction.
- POST /orders: Alias tạo đơn hàng từ giỏ.
- GET /orders: Xem danh sách đơn hàng của người dùng hiện tại.
- GET /orders/{order_code}: Xem chi tiết một đơn hàng.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.crud.order import (
    build_order_response,
    create_cod_order,
    get_order_by_code,
    get_user_orders,
)
from app.db.session import get_db
from app.models.payment import Payment
from app.models.user import User
from app.schemas.order import (
    CreateCODOrderRequest,
    CreateOrderActionMessage,
    OrderResponse,
)

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post(
    "/cod",
    response_model=CreateOrderActionMessage,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo đơn hàng COD từ giỏ hàng hiện tại",
    description="Kiểm tra tính hợp lệ của giỏ hàng, kiểm tra lại tồn kho và giá ở server. Thực hiện tạo Order, OrderItems, trừ kho và tạo Payment COD trong 1 database transaction duy nhất.",
)
def create_cod_order_endpoint(
    payload: CreateCODOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreateOrderActionMessage:
    order, payment = create_cod_order(
        db=db,
        user_id=current_user.id,
        shipping_address=payload.shipping_address,
        voucher_code=payload.voucher_code,
    )
    return CreateOrderActionMessage(
        message="Tạo đơn hàng COD thành công.",
        order=build_order_response(order, payment),
    )


@router.post(
    "",
    response_model=CreateOrderActionMessage,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo đơn hàng từ giỏ (Mặc định phương thức COD)",
)
def create_order_alias_endpoint(
    payload: CreateCODOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreateOrderActionMessage:
    return create_cod_order_endpoint(
        payload=payload,
        current_user=current_user,
        db=db,
    )


@router.get(
    "",
    response_model=list[OrderResponse],
    summary="Danh sách đơn hàng của người dùng hiện tại",
    description="Chỉ hiển thị các đơn hàng thuộc về chính người dùng đang đăng nhập.",
)
def list_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OrderResponse]:
    orders = get_user_orders(db=db, user_id=current_user.id)
    result: list[OrderResponse] = []
    for ord_obj in orders:
        # Lấy payment gần nhất của đơn
        payment = None
        if ord_obj.id:
            from sqlalchemy import select
            payment = db.scalar(
                select(Payment)
                .where(Payment.order_id == ord_obj.id)
                .order_by(Payment.attempt_number.desc())
            )
        result.append(build_order_response(ord_obj, payment))
    return result


@router.get(
    "/{order_code}",
    response_model=OrderResponse,
    summary="Xem chi tiết một đơn hàng theo order_code",
)
def get_order_detail(
    order_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderResponse:
    order, payment = get_order_by_code(
        db=db,
        order_code=order_code,
        user_id=current_user.id,
    )
    return build_order_response(order, payment)

