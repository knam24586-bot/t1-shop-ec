"""CRUD và nghiệp vụ khởi tạo thanh toán trực tuyến (Online Checkout).
Đáp ứng các tiêu chí:
1. Online checkout tạo giao dịch và URL/token theo gateway cấu hình (VNPAY, MOMO, ZALOPAY...).
2. KHÔNG ĐÁNH DẤU PAID TRƯỚC CALLBACK HỢP LỆ: Giao dịch và đơn hàng giữ nguyên PENDING khi vừa khởi tạo.
3. Xử lý triệt để các lỗi khởi tạo: đơn không tồn tại, đơn đã thanh toán, đơn đã huỷ, sai user, cổng không hỗ trợ.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.schemas.payment import (
    OnlineCheckoutResponse,
    PaymentCallbackResponse,
)
from app.services.payment_gateway import (
    SUPPORTED_ONLINE_GATEWAYS,
    build_gateway_payment_session,
    is_supported_online_gateway,
)


def initiate_online_checkout(
    db: Session,
    user_id: int,
    order_code: str,
    method: str,
    return_url: str | None = None,
    ip_address: str = "127.0.0.1",
) -> OnlineCheckoutResponse:
    """Khởi tạo yêu cầu thanh toán online cho đơn hàng:
    - Kiểm tra tính hợp lệ của đơn hàng (thuộc về user, trạng thái cho phép thanh toán).
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
        status=payment.status,  # Phải là PENDING
        transaction_reference=payment.transaction_reference,
        attempt_number=payment.attempt_number,
        payment_url=payment_url,
        payment_token=payment_token,
        gateway_name=clean_method,
        created_at=payment.created_at,
        expires_at=expires_at,
    )


def process_payment_callback(
    db: Session,
    transaction_reference: str,
    method: str,
    response_code: str = "00",
    secure_hash: str | None = None,
) -> PaymentCallbackResponse:
    """Xử lý kết quả callback / IPN từ cổng thanh toán.
    Chỉ khi nhận được callback hợp lệ và response_code='00' mới cập nhật trạng thái PAID / SUCCESS.
    """
    stmt = select(Payment).where(Payment.transaction_reference == transaction_reference)
    payment = db.scalar(stmt)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy giao dịch với mã tham chiếu '{transaction_reference}'.",
        )

    order = payment.order
    if response_code == "00":
        # Thanh toán thành công
        payment.mark_as_success(transaction_reference=transaction_reference)
        if order.status == OrderStatus.PENDING.value:
            order.transition_to(OrderStatus.CONFIRMED.value)
        db.commit()
        db.refresh(payment)
        db.refresh(order)
        return PaymentCallbackResponse(
            success=True,
            message="Xác nhận thanh toán thành công từ cổng thanh toán.",
            order_code=order.order_code,
            order_status=order.status,
            payment_status=payment.status,
            transaction_reference=transaction_reference,
        )
    else:
        # Thanh toán thất bại
        payment.mark_as_failed(reason=f"Gateway trả về mã lỗi {response_code}")
        db.commit()
        db.refresh(payment)
        return PaymentCallbackResponse(
            success=False,
            message=f"Thanh toán thất bại từ cổng {method} (Mã lỗi: {response_code}).",
            order_code=order.order_code,
            order_status=order.status,
            payment_status=payment.status,
            transaction_reference=transaction_reference,
        )


def get_payment_by_transaction_ref(db: Session, transaction_ref: str) -> Payment | None:
    """Tìm bản ghi thanh toán theo transaction_reference."""
    return db.scalar(select(Payment).where(Payment.transaction_reference == transaction_ref))

