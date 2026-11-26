"""API Router cho Payment Lifecycle: Payment fail, Callback lặp (Idempotent), Hết hạn và Hủy đơn giải phóng hàng.
Cung cấp các API:
- POST /payments/callback-with-release: Xử lý callback webhook kèm tính năng tự động giải phóng tồn kho khi thất bại.
- POST /payments/expire: Xử lý giao dịch thanh toán trực tuyến hết hạn (timeout) và giải phóng hàng đúng 1 lần.
- POST /payments/cancel-order: Hủy đơn hàng tuân thủ quy tắc State Machine và giải phóng tồn kho.
- GET /payments/state-transitions/{order_code}: Xem trạng thái hiện tại và các bước chuyển hợp lệ theo State Machine.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.crud.payment_lifecycle import (
    cancel_order_with_state_machine_guard,
    get_order_state_transitions,
    handle_expired_payment_and_release_stock,
    handle_payment_callback_lifecycle,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.payment_lifecycle import (
    ExpirePaymentRequest,
    ExpirePaymentResponse,
    OrderStateTransitionsResponse,
    PaymentLifecycleCallbackRequest,
    PaymentLifecycleCallbackResponse,
    StateMachineCancelOrderRequest,
    StateMachineCancelOrderResponse,
)

router = APIRouter(prefix="/payments", tags=["Payment Lifecycle & Cancellation"])


@router.post(
    "/callback-with-release",
    response_model=PaymentLifecycleCallbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Xử lý callback thanh toán an toàn, Idempotent và tự động giải phóng hàng khi thất bại",
    description=(
        "Xác thực chữ ký số HMAC, xử lý Idempotent chống trùng lặp. "
        "Nếu thanh toán thất bại (response_code != '00'): tự động chuyển đơn sang CANCELLED "
        "và giải phóng hàng đúng 1 lần duy nhất."
    ),
)
def handle_payment_callback_with_release(
    payload: PaymentLifecycleCallbackRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PaymentLifecycleCallbackResponse:
    client_ip = "127.0.0.1"
    if request.client and request.client.host:
        client_ip = request.client.host

    return handle_payment_callback_lifecycle(
        db=db,
        transaction_reference=payload.transaction_reference,
        method=payload.method,
        response_code=payload.response_code,
        secure_hash=payload.secure_hash,
        extra_params=payload.extra_params,
        ip_address=client_ip,
    )


@router.post(
    "/expire",
    response_model=ExpirePaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Xử lý giao dịch thanh toán hết hạn (Payment Expired / Timeout) và giải phóng hàng đúng 1 lần",
    description=(
        "Khi giao dịch thanh toán online quá hạn mà chưa thanh toán: "
        "chuyển Payment và Order sang CANCELLED, hoàn trả tồn kho đúng một lần duy nhất. "
        "Yêu cầu gọi lặp lại được xử lý Idempotent (không hoàn tồn lần 2)."
    ),
)
def expire_payment(
    payload: ExpirePaymentRequest,
    db: Session = Depends(get_db),
) -> ExpirePaymentResponse:
    return handle_expired_payment_and_release_stock(
        db=db,
        transaction_reference=payload.transaction_reference,
        order_code=payload.order_code,
        reason=payload.reason,
    )


@router.post(
    "/cancel-order",
    response_model=StateMachineCancelOrderResponse,
    status_code=status.HTTP_200_OK,
    summary="Hủy đơn hàng tuân thủ quy tắc State Machine và giải phóng tồn kho",
    description=(
        "Kiểm tra nghiêm ngặt State Machine: Cho phép hủy đơn ở PENDING, CONFIRMED. "
        "Chặn hủy đơn đã giao (DELIVERED), đang giao (SHIPPED) hoặc đã hủy (CANCELLED). "
        "Giải phóng tồn kho đúng 1 lần và ghi nhận lịch sử trạng thái."
    ),
)
def cancel_order_state_machine(
    payload: StateMachineCancelOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StateMachineCancelOrderResponse:
    return cancel_order_with_state_machine_guard(
        db=db,
        order_code=payload.order_code,
        reason=payload.reason,
        user_id=current_user.id,
        cancelled_by=payload.cancelled_by or "CUSTOMER",
    )


@router.get(
    "/state-transitions/{order_code}",
    response_model=OrderStateTransitionsResponse,
    summary="Kiểm tra trạng thái hiện tại và các chuyển đổi hợp lệ theo State Machine",
)
def check_order_state_transitions(
    order_code: str,
    db: Session = Depends(get_db),
) -> OrderStateTransitionsResponse:
    return get_order_state_transitions(db=db, order_code=order_code)
