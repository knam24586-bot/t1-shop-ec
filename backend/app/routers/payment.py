"""API Router cho Thanh toán Online (Online Payment & Checkout) và Webhook.
Cung cấp các API:
- POST /payments/checkout hoặc /payments/online-checkout: Khởi tạo yêu cầu thanh toán online.
- POST /payments/callback hoặc GET /payments/callback: Xử lý và xác thực callback / IPN từ cổng thanh toán.
- GET /payments/transaction/{transaction_ref}: Xem trạng thái giao dịch.
- GET /payments/logs/{transaction_ref}: Xem lịch sử audit log của webhook.
- GET /payments/gateways: Danh sách các cổng thanh toán online được hỗ trợ.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.crud.payment import (
    get_payment_by_transaction_ref,
    get_webhook_logs,
    initiate_online_checkout,
    process_payment_callback,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.payment import (
    OnlineCheckoutRequest,
    OnlineCheckoutResponse,
    PaymentCallbackRequest,
    PaymentCallbackResponse,
    PaymentWebhookLogResponse,
)
from app.services.payment_gateway import SUPPORTED_ONLINE_GATEWAYS

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "/checkout",
    response_model=OnlineCheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Khởi tạo yêu cầu thanh toán trực tuyến (Online Checkout)",
    description=(
        "Tạo bản ghi giao dịch với trạng thái PENDING và sinh URL/token thanh toán "
        "dựa trên cấu hình của cổng thanh toán được chọn (VNPAY, MOMO, ZALOPAY...). "
        "Tuyệt đối không đánh dấu PAID trước khi nhận được callback hợp lệ. "
        "Xử lý đầy đủ các lỗi khởi tạo."
    ),
)
def create_online_checkout(
    payload: OnlineCheckoutRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnlineCheckoutResponse:
    client_ip = "127.0.0.1"
    if request.client and request.client.host:
        client_ip = request.client.host

    return initiate_online_checkout(
        db=db,
        user_id=current_user.id,
        order_code=payload.order_code,
        method=payload.method,
        return_url=payload.return_url,
        ip_address=client_ip,
    )


@router.post(
    "/online-checkout",
    response_model=OnlineCheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Khởi tạo thanh toán trực tuyến (Alias /online-checkout)",
)
def create_online_checkout_alias(
    payload: OnlineCheckoutRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnlineCheckoutResponse:
    return create_online_checkout(
        payload=payload,
        request=request,
        current_user=current_user,
        db=db,
    )


@router.post(
    "/callback",
    response_model=PaymentCallbackResponse,
    summary="Xử lý webhook / IPN callback từ cổng thanh toán an toàn",
    description="Xác thực chữ ký số theo gateway, xử lý Idempotent chống lặp và lưu log audit.",
)
def handle_payment_callback_post(
    payload: PaymentCallbackRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PaymentCallbackResponse:
    client_ip = "127.0.0.1"
    if request.client and request.client.host:
        client_ip = request.client.host

    return process_payment_callback(
        db=db,
        transaction_reference=payload.transaction_reference,
        method=payload.method,
        response_code=payload.response_code,
        secure_hash=payload.secure_hash,
        extra_params=payload.extra_params,
        ip_address=client_ip,
    )


@router.get(
    "/callback",
    response_model=PaymentCallbackResponse,
    summary="Xử lý callback GET (Return URL từ trình duyệt)",
)
def handle_payment_callback_get(
    request: Request,
    transaction_reference: str = Query(..., description="Mã tham chiếu đối soát"),
    method: str = Query(..., description="Cổng thanh toán"),
    response_code: str = Query("00", description="Mã phản hồi từ gateway"),
    secure_hash: str | None = Query(None, description="Chữ ký hash"),
    db: Session = Depends(get_db),
) -> PaymentCallbackResponse:
    client_ip = "127.0.0.1"
    if request.client and request.client.host:
        client_ip = request.client.host

    # Lấy toàn bộ query params làm extra_params để xác thực chữ ký nếu cần
    params = dict(request.query_params)
    if not secure_hash:
        secure_hash = (
            params.get("vnp_SecureHash")
            or params.get("signature")
            or params.get("mac")
        )

    return process_payment_callback(
        db=db,
        transaction_reference=transaction_reference,
        method=method,
        response_code=response_code,
        secure_hash=secure_hash,
        extra_params=params,
        ip_address=client_ip,
    )


@router.get(
    "/logs/{transaction_ref}",
    response_model=list[PaymentWebhookLogResponse],
    summary="Xem lịch sử audit log của webhook theo transaction_reference",
)
def get_transaction_webhook_logs(
    transaction_ref: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PaymentWebhookLogResponse]:
    payment = get_payment_by_transaction_ref(db, transaction_ref)
    is_admin = current_user.role.strip().upper() == "ADMIN"
    if not is_admin:
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giao dịch không tồn tại.",
            )
        if payment.order is None or payment.order.customer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền xem log giao dịch này.",
            )
    logs = get_webhook_logs(db=db, transaction_ref=transaction_ref)
    return [PaymentWebhookLogResponse.model_validate(log) for log in logs]


@router.get(
    "/gateways",
    summary="Danh sách các cổng thanh toán trực tuyến được hỗ trợ",
)
def list_supported_gateways() -> dict[str, list[str]]:
    return {
        "supported_gateways": sorted(list(SUPPORTED_ONLINE_GATEWAYS)),
    }


@router.get(
    "/transaction/{transaction_ref}",
    summary="Xem trạng thái một giao dịch thanh toán",
)
def get_transaction_status(
    transaction_ref: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    payment = get_payment_by_transaction_ref(db, transaction_ref)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Giao dịch không tồn tại.",
        )
    is_admin = current_user.role.strip().upper() == "ADMIN"
    if not is_admin and (payment.order is None or payment.order.customer_id != current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem giao dịch này.",
        )
    return {
        "transaction_reference": payment.transaction_reference or "",
        "method": payment.method,
        "amount": str(payment.amount),
        "status": payment.status,
        "attempt_number": str(payment.attempt_number),
    }
