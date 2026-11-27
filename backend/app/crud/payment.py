"""CRUD và nghiệp vụ khởi tạo thanh toán trực tuyến (Online Checkout) và xác thực Callback an toàn.
Đáp ứng đầy đủ:
1. Online checkout tạo giao dịch và URL/token theo gateway cấu hình (VNPAY, MOMO, ZALOPAY...).
2. Webhook xác thực chữ ký/nguồn theo gateway (HMAC-SHA512/SHA256).
3. Xử lý IDEMPOTENT: Callback lặp lại KHÔNG tạo thanh toán/đơn trùng, giữ nguyên trạng thái an toàn.
4. Lưu log kết quả xử lý webhook vào database (bảng payment_webhook_logs).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.payment_log import PaymentWebhookLog
from app.schemas.payment import (
    OnlineCheckoutResponse,
    PaymentCallbackResponse,
)
from app.services.payment_gateway import (
    SUPPORTED_ONLINE_GATEWAYS,
    build_gateway_payment_session,
    is_supported_online_gateway,
    verify_gateway_signature,
)

logger = logging.getLogger("payment.webhook")


def initiate_online_checkout(
    db: Session,
    user_id: int,
    order_code: str,
    method: str,
    return_url: str | None = None,
    ip_address: str = "127.0.0.1",
) -> OnlineCheckoutResponse:
    """Khởi tạo yêu cầu thanh toán online cho đơn hàng:
    - Kiểm tra đơn hàng hợp lệ, thuộc quyền sở hữu của user hiện tại.
    - Kiểm tra đơn chưa bị huỷ và chưa từng thanh toán thành công.
    - Kiểm tra cổng thanh toán online có hỗ trợ hay không.
    - Quản lý số lần thử (attempt_number tự tăng).
    - Sinh mã đối soát duy nhất (transaction_reference).
    - Tạo giao dịch Payment với trạng thái PENDING (tuyệt đối KHÔNG đánh dấu PAID).
    - Sinh payment_url và payment_token theo cấu hình của gateway.
    - Trả về kết quả khởi tạo cho client.
    """
    # 1. Kiểm tra đơn hàng có tồn tại không
    stmt = select(Order).where(Order.order_code == order_code)
    order = db.scalar(stmt)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng với mã '{order_code}'.",
        )

    # 2. Kiểm tra quyền sở hữu đơn hàng (User chỉ được thanh toán đơn của mình)
    if order.customer_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thực hiện thanh toán cho đơn hàng này.",
        )

    # 3. Kiểm tra trạng thái đơn hàng
    if order.status == OrderStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng này đã bị huỷ, không thể khởi tạo thanh toán.",
        )

    # Kiểm tra xem đơn hàng đã có giao dịch nào thanh toán thành công chưa
    success_payment = db.scalar(
        select(Payment).where(
            Payment.order_id == order.id,
            Payment.status == PaymentStatus.SUCCESS.value,
        )
    )
    if success_payment is not None or order.status in [
        OrderStatus.CONFIRMED.value,
        OrderStatus.PROCESSING.value,
        OrderStatus.SHIPPED.value,
        OrderStatus.DELIVERED.value,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng này đã được thanh toán thành công, không thể tạo thêm giao dịch.",
        )

    # 4. Kiểm tra số tiền đơn hàng
    if order.total_price <= Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Số tiền đơn hàng không hợp lệ để thực hiện thanh toán trực tuyến.",
        )

    # 5. Kiểm tra cổng thanh toán có được hỗ trợ không
    clean_method = method.strip().upper()
    if not is_supported_online_gateway(clean_method):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Phương thức thanh toán '{method}' không được hỗ trợ hoặc không phải cổng online. "
                f"Các cổng hợp lệ: {', '.join(sorted(SUPPORTED_ONLINE_GATEWAYS))}."
            ),
        )

    # 6. Tính số thứ tự lần thử (attempt_number)
    existing_payments = db.scalars(
        select(Payment)
        .where(Payment.order_id == order.id)
        .order_by(Payment.attempt_number.desc())
    ).all()
    attempt_number = (existing_payments[0].attempt_number + 1) if existing_payments else 1

    # 7. Sinh mã tham chiếu giao dịch đối soát duy nhất
    transaction_ref = Payment.generate_transaction_ref(
        clean_method, order.id, attempt_number
    )

    # 8. Sinh payment_url và payment_token từ service Gateway
    try:
        payment_url, payment_token, expires_at = build_gateway_payment_session(
            method=clean_method,
            order_id=order.id,
            order_code=order.order_code,
            amount=order.total_price,
            transaction_ref=transaction_ref,
            ip_address=ip_address,
            return_url=return_url,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Lỗi khi khởi tạo URL cổng thanh toán {clean_method}: {str(e)}",
        )

    # 9. Lưu bản ghi Payment vào DB với trạng thái PENDING
    # TIÊU CHÍ QUAN TRỌNG: TUYỆT ĐỐI KHÔNG ĐÁNH DẤU PAID TRƯỚC KHI CÓ CALLBACK HỢP LỆ
    payment = Payment(
        order_id=order.id,
        method=clean_method,
        amount=order.total_price,
        status=PaymentStatus.PENDING.value,
        attempt_number=attempt_number,
        transaction_reference=transaction_ref,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    return OnlineCheckoutResponse(
        payment_id=payment.id,
        order_id=order.id,
        order_code=order.order_code,
        method=payment.method,
        amount=payment.amount,
        status=payment.status,  # Luôn là PENDING
        transaction_reference=payment.transaction_reference,
        attempt_number=payment.attempt_number,
        payment_url=payment_url,
        payment_token=payment_token,
        gateway_name=clean_method,
        created_at=payment.created_at,
        expires_at=expires_at,
    )


def log_webhook_result(
    db: Session,
    transaction_reference: str,
    gateway: str,
    raw_payload: str,
    is_valid_signature: bool,
    response_code: str | None,
    message: str,
    ip_address: str | None = None,
) -> PaymentWebhookLog:
    """Lưu bản ghi log kết quả xử lý webhook vào DB."""
    webhook_log = PaymentWebhookLog(
        transaction_reference=transaction_reference,
        gateway=gateway,
        raw_payload=raw_payload,
        is_valid_signature=is_valid_signature,
        response_code=response_code,
        message=message,
        ip_address=ip_address,
    )
    db.add(webhook_log)
    db.commit()
    db.refresh(webhook_log)
    logger.info(
        f"Webhook Log saved: ref={transaction_reference}, gateway={gateway}, "
        f"valid_sig={is_valid_signature}, msg={message}"
    )
    return webhook_log


def process_payment_callback(
    db: Session,
    transaction_reference: str,
    method: str,
    response_code: str = "00",
    secure_hash: str | None = None,
    extra_params: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> PaymentCallbackResponse:
    """Xử lý an toàn callback / IPN từ cổng thanh toán:
    1. Xác thực chữ ký số theo gateway (VNPAY, MoMo, ZaloPay).
    2. Xử lý Idempotent: Nếu giao dịch đã PAID/SUCCESS từ trước -> bỏ qua, không tạo đơn/thanh toán trùng.
    3. Cập nhật trạng thái Payment và Order chỉ khi chữ ký hợp lệ và response_code='00'.
    4. Lưu vết toàn bộ kết quả vào PaymentWebhookLog.
    """
    clean_method = method.strip().upper()
    params = dict(extra_params or {})
    params.setdefault("transaction_reference", transaction_reference)
    params.setdefault("response_code", response_code)
    raw_payload_str = json.dumps(params, ensure_ascii=False)

    # Fallback trích xuất secure_hash nếu được gửi trong extra_params
    if not secure_hash and extra_params:
        secure_hash = (
            extra_params.get("vnp_SecureHash")
            or extra_params.get("signature")
            or extra_params.get("mac")
            or extra_params.get("secure_hash")
        )

    # 1. Tìm bản ghi giao dịch thanh toán
    stmt = select(Payment).where(Payment.transaction_reference == transaction_reference)
    payment = db.scalar(stmt)
    if not payment:
        msg = f"Không tìm thấy giao dịch với mã tham chiếu '{transaction_reference}'."
        log_webhook_result(
            db=db,
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=False,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)

    # 2. XÁC THỰC NGUỒN CỔNG THANH TOÁN (GATEWAY SOURCE)
    if payment.method.upper() != clean_method:
        msg = f"Cổng thanh toán '{clean_method}' không khớp với phương thức '{payment.method}' của giao dịch."
        log_webhook_result(
            db=db,
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=False,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    order = payment.order

    # 3. XÁC THỰC CHỮ KÝ THEO GATEWAY
    is_valid_sig = verify_gateway_signature(
        gateway=clean_method,
        params=params,
        signature=secure_hash,
    )
    if not is_valid_sig:
        msg = f"Chữ ký không hợp lệ từ cổng thanh toán {clean_method}."
        log_webhook_result(
            db=db,
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=False,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )

    # 4. XỬ LÝ IDEMPOTENT (Chống lặp lại callback)
    # Nếu giao dịch đã ở trạng thái SUCCESS từ trước:
    if payment.status == PaymentStatus.SUCCESS.value:
        msg = "Giao dịch đã được xác nhận thanh toán thành công trước đó (Idempotent - Bỏ qua xử lý lặp)."
        log_webhook_result(
            db=db,
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=True,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        # Trả về kết quả thành công mà KHÔNG tạo thanh toán hay đơn hàng mới
        return PaymentCallbackResponse(
            success=True,
            is_idempotent=True,
            message=msg,
            order_code=order.order_code,
            order_status=order.status,
            payment_status=payment.status,
            transaction_reference=transaction_reference,
        )

    # Nếu giao dịch đã ở trạng thái FAILED từ trước và nhận lại callback thất bại:
    if payment.status == PaymentStatus.FAILED.value and response_code != "00":
        msg = "Giao dịch đã được ghi nhận thất bại trước đó (Idempotent)."
        log_webhook_result(
            db=db,
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=True,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        return PaymentCallbackResponse(
            success=False,
            is_idempotent=True,
            message=msg,
            order_code=order.order_code,
            order_status=order.status,
            payment_status=payment.status,
            transaction_reference=transaction_reference,
        )

    # 4. CẬP NHẬT TRẠNG THÁI LẦN ĐẦU
    if response_code == "00":
        # Thanh toán thành công
        payment.mark_as_success(transaction_reference=transaction_reference)
        if order.status == OrderStatus.PENDING.value:
            order.transition_to(OrderStatus.CONFIRMED.value)

        msg = "Xác nhận thanh toán thành công từ cổng thanh toán."
        log_webhook_result(
            db=db,
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=True,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        db.commit()
        db.refresh(payment)
        db.refresh(order)

        return PaymentCallbackResponse(
            success=True,
            is_idempotent=False,
            message=msg,
            order_code=order.order_code,
            order_status=order.status,
            payment_status=payment.status,
            transaction_reference=transaction_reference,
        )
    else:
        # Thanh toán thất bại từ cổng
        payment.mark_as_failed(reason=f"Gateway {clean_method} trả về response_code={response_code}")
        msg = f"Thanh toán thất bại từ cổng {clean_method} (Mã phản hồi: {response_code})."
        log_webhook_result(
            db=db,
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=True,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        db.commit()
        db.refresh(payment)

        return PaymentCallbackResponse(
            success=False,
            is_idempotent=False,
            message=msg,
            order_code=order.order_code,
            order_status=order.status,
            payment_status=payment.status,
            transaction_reference=transaction_reference,
        )


def get_payment_by_transaction_ref(db: Session, transaction_ref: str) -> Payment | None:
    """Tìm bản ghi thanh toán theo transaction_reference."""
    return db.scalar(select(Payment).where(Payment.transaction_reference == transaction_ref))


def get_webhook_logs(db: Session, transaction_ref: str | None = None) -> list[PaymentWebhookLog]:
    """Lấy danh sách log webhook đã lưu."""
    stmt = select(PaymentWebhookLog)
    if transaction_ref:
        stmt = stmt.where(PaymentWebhookLog.transaction_reference == transaction_ref)
    stmt = stmt.order_by(PaymentWebhookLog.created_at.desc())
    return list(db.scalars(stmt))
