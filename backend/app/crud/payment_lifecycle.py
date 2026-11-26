"""CRUD và nghiệp vụ xử lý Payment fail, Callback lặp (Idempotent), Hết hạn và Hủy đơn giải phóng hàng đúng một lần.
Tiêu chí chấp nhận:
1. Payment callback xử lý idempotent:
   - Callback SUCCESS lặp -> giữ nguyên SUCCESS, không tạo giao dịch/đơn trùng.
   - Callback FAILED lặp -> giữ nguyên FAILED, không hoàn tồn kho lần 2.
   - Callback FAILED gửi muộn sau SUCCESS -> bị chặn, không hạ cấp giao dịch thành công.
2. Thất bại / hết hạn giải phóng hàng đúng một lần:
   - Khi thanh toán online thất bại (mã phản hồi khác '00') hoặc hết hạn (expired/timeout),
     đơn hàng chuyển sang CANCELLED và giải phóng tồn kho cho các biến thể và sản phẩm.
   - Bảo đảm hoàn tồn đúng 1 lần: Kiểm tra bản ghi OrderCancellation và trạng thái trước khi hoàn tồn.
3. Hủy đơn tuân thủ State Machine:
   - Cho phép hủy ở PENDING hoặc CONFIRMED.
   - Chặn hủy đơn đã giao (DELIVERED) hoặc đang giao (SHIPPED).
   - Chặn hủy đơn đã hủy (CANCELLED).
   - Lưu lý do hủy và lịch sử chuyển trạng thái (OrderStatusHistory).
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

from app.models.order import Order, OrderStatus, VALID_STATUS_TRANSITIONS
from app.models.order_cancellation import OrderCancellation
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.payment_log import PaymentWebhookLog
from app.models.product import Product
from app.models.variant import ProductVariant
from app.schemas.payment_lifecycle import (
    ExpirePaymentResponse,
    OrderStateTransitionsResponse,
    PaymentLifecycleCallbackResponse,
    StateMachineCancelOrderResponse,
)
from app.services.payment_gateway import (
    is_supported_online_gateway,
    verify_gateway_signature,
)

logger = logging.getLogger("payment.lifecycle")


def release_order_inventory_exactly_once(
    db: Session,
    order: Order,
    reason: str,
    cancelled_by: str = "SYSTEM",
    user_id: int | None = None,
) -> tuple[bool, int]:
    """Hoàn trả số lượng tồn kho cho các mặt hàng trong đơn hàng ĐÚNG MỘT LẦN DUY NHẤT.
    Trả về: (inventory_released: bool, restocked_items_count: int)
    - Nếu đã hoàn tồn trước đó: trả về (False, 0)
    - Nếu hoàn tồn thành công lần đầu: trả về (True, tổng_số_lượng_hoàn)
    """
    # 1. Kiểm tra xem đơn hàng đã có bản ghi OrderCancellation chưa
    existing_cancellation = db.scalar(
        select(OrderCancellation).where(OrderCancellation.order_id == order.id)
    )
    if existing_cancellation is not None and existing_cancellation.inventory_restocked:
        logger.info(f"Đơn hàng '{order.order_code}' đã được hoàn tồn trước đó. Bỏ qua hoàn tồn lần 2.")
        return False, 0

    # 2. Hoàn trả tồn kho cho từng ProductVariant và Product
    restocked_count = 0
    for item in order.items:
        qty = item.quantity
        if item.variant_id:
            variant = db.get(ProductVariant, item.variant_id)
            if variant:
                variant.stock += qty
                if variant.product and variant.product.stock is not None:
                    variant.product.stock += qty
        elif item.product_id:
            prod = db.get(Product, item.product_id)
            if prod and prod.stock is not None:
                prod.stock += qty

        restocked_count += qty

    # 3. Tạo hoặc cập nhật bản ghi OrderCancellation để khóa không hoàn tồn lần 2
    uid = user_id or order.customer_id
    if existing_cancellation is None:
        cancellation = OrderCancellation(
            order_id=order.id,
            order_code=order.order_code,
            user_id=uid,
            reason=reason,
            cancelled_by=cancelled_by,
            inventory_restocked=True,
            cancelled_at=datetime.now(),
        )
        db.add(cancellation)
    else:
        existing_cancellation.inventory_restocked = True
        existing_cancellation.reason = reason

    return True, restocked_count


def handle_payment_callback_lifecycle(
    db: Session,
    transaction_reference: str,
    method: str,
    response_code: str = "00",
    secure_hash: str | None = None,
    extra_params: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> PaymentLifecycleCallbackResponse:
    """Xử lý webhook callback từ cổng thanh toán kèm tính năng:
    - Xác thực chữ ký HMAC bảo mật.
    - Idempotent chống trùng lặp.
    - Khi thất bại: tự động chuyển Order -> CANCELLED và giải phóng tồn kho đúng 1 lần.
    - Bảo vệ giao dịch SUCCESS không bị ghi đè.
    """
    clean_method = method.strip().upper()
    params = dict(extra_params or {})
    params.setdefault("transaction_reference", transaction_reference)
    params.setdefault("response_code", response_code)
    raw_payload_str = json.dumps(params, ensure_ascii=False)

    if not secure_hash and extra_params:
        secure_hash = (
            extra_params.get("vnp_SecureHash")
            or extra_params.get("signature")
            or extra_params.get("mac")
            or extra_params.get("secure_hash")
        )

    # 1. Tìm bản ghi Payment
    stmt = select(Payment).where(Payment.transaction_reference == transaction_reference)
    payment = db.scalar(stmt)
    if not payment:
        msg = f"Không tìm thấy giao dịch với mã tham chiếu '{transaction_reference}'."
        # Lưu log
        log = PaymentWebhookLog(
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=False,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)

    # 2. Xác thực gateway source
    if payment.method.upper() != clean_method:
        msg = f"Cổng thanh toán '{clean_method}' không khớp với phương thức '{payment.method}' của giao dịch."
        log = PaymentWebhookLog(
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=False,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    order = payment.order

    # 3. Xác thực chữ ký
    is_valid_sig = verify_gateway_signature(
        gateway=clean_method,
        params=params,
        signature=secure_hash,
    )
    if not is_valid_sig:
        msg = f"Chữ ký không hợp lệ từ cổng thanh toán {clean_method}."
        log = PaymentWebhookLog(
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=False,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # 4. XỬ LÝ IDEMPOTENT: Callback lặp
    # A. Nếu giao dịch đã SUCCESS từ trước:
    if payment.status == PaymentStatus.SUCCESS.value:
        msg = "Giao dịch đã được xác nhận thanh toán thành công trước đó (Idempotent - Bỏ qua xử lý lặp)."
        log = PaymentWebhookLog(
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=True,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
        return PaymentLifecycleCallbackResponse(
            success=True,
            is_idempotent=True,
            message=msg,
            order_code=order.order_code,
            order_status=order.status,
            payment_status=payment.status,
            transaction_reference=transaction_reference,
            inventory_released=False,
            restocked_items_count=0,
        )

    # B. Nếu giao dịch đã FAILED từ trước và nhận lại callback thất bại:
    if payment.status == PaymentStatus.FAILED.value and response_code != "00":
        msg = "Giao dịch đã được ghi nhận thất bại trước đó (Idempotent - Không hoàn tồn lần 2)."
        log = PaymentWebhookLog(
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=True,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
        return PaymentLifecycleCallbackResponse(
            success=False,
            is_idempotent=True,
            message=msg,
            order_code=order.order_code,
            order_status=order.status,
            payment_status=payment.status,
            transaction_reference=transaction_reference,
            inventory_released=False,
            restocked_items_count=0,
        )

    # 5. CẬP NHẬT TRẠNG THÁI LẦN ĐẦU
    if response_code == "00":
        # Thanh toán thành công
        payment.mark_as_success(transaction_reference=transaction_reference)
        previous_status = order.status
        if order.status == OrderStatus.PENDING.value:
            order.transition_to(OrderStatus.CONFIRMED.value)
            history = OrderStatusHistory(
                order_id=order.id,
                order_code=order.order_code,
                previous_status=previous_status,
                new_status=OrderStatus.CONFIRMED.value,
                reason="Thanh toán trực tuyến thành công",
                changed_by_role="GATEWAY",
            )
            db.add(history)

        msg = "Xác nhận thanh toán thành công từ cổng thanh toán."
        log = PaymentWebhookLog(
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=True,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
        db.refresh(payment)
        db.refresh(order)

        return PaymentLifecycleCallbackResponse(
            success=True,
            is_idempotent=False,
            message=msg,
            order_code=order.order_code,
            order_status=order.status,
            payment_status=payment.status,
            transaction_reference=transaction_reference,
            inventory_released=False,
            restocked_items_count=0,
        )
    else:
        # Thanh toán thất bại từ cổng: Cập nhật FAILED và giải phóng hàng đúng 1 lần
        payment.mark_as_failed(reason=f"Gateway {clean_method} trả về response_code={response_code}")
        previous_status = order.status
        inventory_released = False
        restocked_count = 0

        # Nếu đơn hàng đang ở PENDING -> Chuyển CANCELLED và giải phóng tồn kho
        if order.status == OrderStatus.PENDING.value and order.can_transition_to(OrderStatus.CANCELLED.value):
            order.transition_to(OrderStatus.CANCELLED.value)
            order.updated_at = datetime.now()

            fail_reason = f"Thanh toán thất bại từ cổng {clean_method} (Mã phản hồi: {response_code})"
            inventory_released, restocked_count = release_order_inventory_exactly_once(
                db=db,
                order=order,
                reason=fail_reason,
                cancelled_by="GATEWAY",
            )

            history = OrderStatusHistory(
                order_id=order.id,
                order_code=order.order_code,
                previous_status=previous_status,
                new_status=OrderStatus.CANCELLED.value,
                reason=fail_reason,
                changed_by_role="GATEWAY",
            )
            db.add(history)

        msg = f"Thanh toán thất bại từ cổng {clean_method} (Mã phản hồi: {response_code})."
        log = PaymentWebhookLog(
            transaction_reference=transaction_reference,
            gateway=clean_method,
            raw_payload=raw_payload_str,
            is_valid_signature=True,
            response_code=response_code,
            message=msg,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
        db.refresh(payment)
        db.refresh(order)

        return PaymentLifecycleCallbackResponse(
            success=False,
            is_idempotent=False,
            message=msg,
            order_code=order.order_code,
            order_status=order.status,
            payment_status=payment.status,
            transaction_reference=transaction_reference,
            inventory_released=inventory_released,
            restocked_items_count=restocked_count,
        )


def handle_expired_payment_and_release_stock(
    db: Session,
    transaction_reference: str | None = None,
    order_code: str | None = None,
    reason: str = "Giao dịch thanh toán trực tuyến đã hết hạn",
) -> ExpirePaymentResponse:
    """Xử lý giao dịch thanh toán hết hạn (Payment Expiration / Timeout) và giải phóng hàng đúng 1 lần:
    - Nếu đơn đã bị hủy / hết hạn trước đó -> Trả về Idempotent response, không hoàn tồn lần 2.
    - Nếu đơn hợp lệ (PENDING) -> Chuyển sang CANCELLED, hoàn tồn cho các biến thể và sản phẩm.
    """
    if not transaction_reference and not order_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cần cung cấp transaction_reference hoặc order_code để xử lý hết hạn.",
        )

    # 1. Tìm Order
    order: Order | None = None
    payment: Payment | None = None

    if transaction_reference:
        payment = db.scalar(select(Payment).where(Payment.transaction_reference == transaction_reference))
        if payment:
            order = payment.order
    elif order_code:
        order = db.scalar(select(Order).where(Order.order_code == order_code))
        if order:
            payment = db.scalar(
                select(Payment)
                .where(Payment.order_id == order.id)
                .order_by(Payment.attempt_number.desc())
            )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy đơn hàng hoặc giao dịch thanh toán tương ứng.",
        )

    now = datetime.now()

    # 2. Xử lý Idempotent: Nếu đơn hàng đã bị hủy trước đó
    if order.status == OrderStatus.CANCELLED.value:
        return ExpirePaymentResponse(
            message="Đơn hàng đã ở trạng thái hủy trước đó (Idempotent - Không hoàn tồn lần 2).",
            order_code=order.order_code,
            payment_status=payment.status if payment else PaymentStatus.CANCELLED.value,
            order_status=order.status,
            is_idempotent=True,
            inventory_released=False,
            restocked_items_count=0,
            expired_at=now,
        )

    # 3. Kiểm tra State Machine: Đơn đã giao (DELIVERED) hoặc đã thanh toán (CONFIRMED/PAID) không được hết hạn
    if order.status == OrderStatus.DELIVERED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng đã được giao thành công (DELIVERED), không thể xử lý hết hạn.",
        )
    if order.status == OrderStatus.SHIPPED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng đang vận chuyển (SHIPPED), không thể xử lý hết hạn.",
        )
    if payment and payment.status == PaymentStatus.SUCCESS.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Giao dịch thanh toán đã thành công, không thể xử lý hết hạn.",
        )

    # 4. Thực hiện hết hạn và giải phóng tồn kho đúng 1 lần
    previous_status = order.status
    if not order.can_transition_to(OrderStatus.CANCELLED.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quy tắc State Machine không cho phép chuyển từ '{order.status}' sang CANCELLED.",
        )

    order.transition_to(OrderStatus.CANCELLED.value)
    order.updated_at = now

    if payment and payment.status == PaymentStatus.PENDING.value:
        payment.status = PaymentStatus.CANCELLED.value
        payment.updated_at = now

    # Giải phóng tồn kho đúng 1 lần
    inventory_released, restocked_count = release_order_inventory_exactly_once(
        db=db,
        order=order,
        reason=reason,
        cancelled_by="SYSTEM",
    )

    # Ghi log lịch sử trạng thái
    history = OrderStatusHistory(
        order_id=order.id,
        order_code=order.order_code,
        previous_status=previous_status,
        new_status=OrderStatus.CANCELLED.value,
        reason=reason,
        changed_by_role="SYSTEM",
    )
    db.add(history)
    db.commit()
    db.refresh(order)

    return ExpirePaymentResponse(
        message=f"Đơn hàng '{order.order_code}' đã được xử lý hết hạn và giải phóng tồn kho thành công.",
        order_code=order.order_code,
        payment_status=payment.status if payment else PaymentStatus.CANCELLED.value,
        order_status=order.status,
        is_idempotent=False,
        inventory_released=inventory_released,
        restocked_items_count=restocked_count,
        expired_at=now,
    )


def cancel_order_with_state_machine_guard(
    db: Session,
    order_code: str,
    reason: str,
    user_id: int | None = None,
    cancelled_by: str = "CUSTOMER",
) -> StateMachineCancelOrderResponse:
    """Hủy đơn hàng tuân thủ nghiêm ngặt State Machine và giải phóng tồn kho đúng 1 lần:
    - Cho phép: PENDING -> CANCELLED, CONFIRMED -> CANCELLED.
    - Chặn: DELIVERED -> 400 Bad Request ("không được phép hủy trái quy tắc").
    - Chặn: SHIPPED -> 400 Bad Request ("đang trong quá trình vận chuyển").
    - Chặn: CANCELLED -> 400 Bad Request ("đã ở trạng thái hủy").
    - Hoàn trả số lượng tồn kho đúng 1 lần.
    - Lưu lý do và lịch sử trạng thái OrderStatusHistory.
    """
    if not reason or not reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lý do hủy đơn hàng không được để trống.",
        )
    clean_reason = reason.strip()
    if len(clean_reason) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lý do hủy đơn hàng phải có ít nhất 3 ký tự.",
        )

    # 1. Tìm đơn hàng
    order = db.scalar(select(Order).where(Order.order_code == order_code.strip()))
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng '{order_code}'.",
        )

    # Kiểm tra quyền nếu là Customer
    if cancelled_by == "CUSTOMER" and user_id is not None and order.customer_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng '{order_code}'.",
        )

    # 2. KIỂM TRA QUY TẮC STATE MACHINE
    if order.status == OrderStatus.DELIVERED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng đã được giao thành công (DELIVERED), không được phép hủy trái quy tắc.",
        )

    if order.status == OrderStatus.SHIPPED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng đang trong quá trình vận chuyển (SHIPPED), không thể hủy.",
        )

    if order.status == OrderStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng đã ở trạng thái hủy (CANCELLED). Không thể hủy lại.",
        )

    if not order.can_transition_to(OrderStatus.CANCELLED.value):
        allowed = VALID_STATUS_TRANSITIONS.get(order.status, set())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Quy tắc State Machine không cho phép chuyển đơn từ '{order.status}' sang CANCELLED. "
                f"Các trạng thái hợp lệ: {', '.join(sorted(allowed))}."
            ),
        )

    previous_status = order.status
    now = datetime.now()

    # 3. Chuyển trạng thái Order sang CANCELLED
    order.transition_to(OrderStatus.CANCELLED.value)
    order.updated_at = now

    # 4. Hủy các thanh toán PENDING nếu có
    payments = db.scalars(select(Payment).where(Payment.order_id == order.id)).all()
    for p in payments:
        if p.status == PaymentStatus.PENDING.value:
            p.status = PaymentStatus.CANCELLED.value
            p.updated_at = now

    # 5. Giải phóng hàng đúng 1 lần
    inventory_released, restocked_count = release_order_inventory_exactly_once(
        db=db,
        order=order,
        reason=clean_reason,
        cancelled_by=cancelled_by,
        user_id=user_id or order.customer_id,
    )

    # 6. Ghi log lịch sử trạng thái
    history = OrderStatusHistory(
        order_id=order.id,
        order_code=order.order_code,
        previous_status=previous_status,
        new_status=OrderStatus.CANCELLED.value,
        reason=clean_reason,
        changed_by_role=cancelled_by,
        changed_by_user_id=user_id,
    )
    db.add(history)
    db.commit()
    db.refresh(order)

    return StateMachineCancelOrderResponse(
        message=f"Đơn hàng '{order.order_code}' đã được hủy thành công và giải phóng hàng.",
        order_code=order.order_code,
        previous_status=previous_status,
        current_status=order.status,
        reason=clean_reason,
        cancelled_by=cancelled_by,
        inventory_released=inventory_released,
        restocked_items_count=restocked_count,
        cancelled_at=now,
    )


def get_order_state_transitions(db: Session, order_code: str) -> OrderStateTransitionsResponse:
    """Tra cứu trạng thái hiện tại và danh sách các trạng thái tiếp theo hợp lệ theo State Machine."""
    order = db.scalar(select(Order).where(Order.order_code == order_code.strip()))
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng '{order_code}'.",
        )

    allowed = sorted(list(VALID_STATUS_TRANSITIONS.get(order.status, set())))
    is_terminal = len(allowed) == 0

    return OrderStateTransitionsResponse(
        order_code=order.order_code,
        current_status=order.status,
        allowed_next_statuses=allowed,
        is_terminal=is_terminal,
    )
