"""CRUD và nghiệp vụ hủy đơn hàng, kiểm tra điều kiện và giải phóng tồn kho.
Tiêu chí chấp nhận:
1. CHỈ HỦY ĐƠN Ở TRẠNG THÁI CHO PHÉP:
   - Cho phép hủy đơn ở trạng thái PENDING hoặc CONFIRMED.
   - Đơn đã giao (DELIVERED) KHÔNG được phép hủy trái quy tắc -> 400 Bad Request.
   - Đơn đang vận chuyển (SHIPPED) không được hủy -> 400 Bad Request.
   - Đơn đã hủy trước đó (CANCELLED) không được hủy lại -> 400 Bad Request.
2. LƯU LÝ DO:
   - Bắt buộc có lý do (tối thiểu 3 ký tự).
   - Lưu vào bảng order_cancellations kèm timestamp, người hủy, order_id, order_code.
3. GIẢI PHÓNG/HOÀN TỒN ĐÚNG MỘT LẦN:
   - Hoàn trả chính xác số lượng của từng biến thể (variant.stock) và sản phẩm (product.stock).
   - Cơ chế bảo vệ: kiểm tra trạng thái trước khi hoàn tồn, kiểm tra bản ghi hủy đã tồn tại,
     và ràng buộc Unique trên order_id để đảm bảo hoàn tồn đúng 1 lần duy nhất trong Database Transaction.
"""
from __future__ import annotations

from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.order_cancellation import OrderCancellation
from app.models.payment import Payment, PaymentStatus
from app.models.product import Product
from app.models.variant import ProductVariant
from app.schemas.order_cancellation import CancelOrderResponse

# Các trạng thái hợp lệ được phép hủy đơn
ALLOWED_CANCELLATION_STATUSES = {
    OrderStatus.PENDING.value,
    OrderStatus.CONFIRMED.value,
}


def process_order_cancellation(
    db: Session,
    order_code_or_id: str | int,
    user_id: int,
    reason: str,
    cancelled_by: str = "CUSTOMER",
) -> CancelOrderResponse:
    """Thực hiện quy trình kiểm tra và hủy đơn hàng nguyên tử trong Database Transaction:
    1. Kiểm tra tính hợp lệ của lý do hủy (reason).
    2. Tìm đơn hàng và kiểm tra quyền sở hữu (Customer chỉ hủy đơn của mình).
    3. Kiểm tra điều kiện trạng thái hủy:
       - Nếu DELIVERED -> Chặn hủy (không bị hủy trái quy tắc).
       - Nếu CANCELLED -> Chặn hủy trùng lặp (đã hủy trước đó).
       - Nếu không thuộc ALLOWED_CANCELLATION_STATUSES -> Chặn hủy.
    4. Kiểm tra đảm bảo tồn kho chưa được hoàn trước đó (giải phóng tồn kho đúng 1 lần).
    5. Trong Transaction nguyên tử:
       - Cập nhật trạng thái Order -> CANCELLED.
       - Hoàn trả số lượng tồn kho cho ProductVariant và Product.
       - Cập nhật Payment PENDING -> CANCELLED.
       - Lưu bản ghi OrderCancellation với lý do và đánh dấu inventory_restocked=True.
       - Commit toàn bộ thay đổi.
    """
    # 1. Kiểm tra lý do hủy
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

    identifier_str = str(order_code_or_id).strip()
    if not identifier_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã đơn hàng không hợp lệ.",
        )

    # 2. Tìm đơn hàng
    if identifier_str.isdigit():
        cond = (Order.id == int(identifier_str)) | (Order.order_code == identifier_str)
    else:
        cond = (Order.order_code == identifier_str)

    order = db.scalar(select(Order).where(cond))
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng '{identifier_str}'.",
        )

    # Kiểm tra quyền sở hữu: Customer chỉ được hủy đơn của chính mình
    if order.customer_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng '{identifier_str}'.",
        )

    # 3. Kiểm tra điều kiện trạng thái đơn hàng
    # Quy tắc bắt buộc: Đơn đã giao (DELIVERED) không được hủy trái quy tắc
    if order.status == OrderStatus.DELIVERED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng đã được giao thành công (DELIVERED), không được phép hủy trái quy tắc.",
        )

    # Đơn hàng đã ở trạng thái CANCELLED -> chặn hủy lại (chống hoàn tồn lần 2)
    if order.status == OrderStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng đã ở trạng thái hủy (CANCELLED). Không thể hủy lại.",
        )

    # Đơn đang giao hàng (SHIPPED)
    if order.status == OrderStatus.SHIPPED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng đang trong quá trình vận chuyển (SHIPPED), không thể hủy.",
        )

    # Đơn ở các trạng thái khác không cho phép
    if order.status not in ALLOWED_CANCELLATION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Không thể hủy đơn hàng ở trạng thái '{order.status}'. "
                f"Chỉ cho phép hủy đơn khi ở trạng thái PENDING hoặc CONFIRMED."
            ),
        )

    # 4. Kiểm tra bản ghi hủy trước đó để bảo đảm hoàn tồn đúng 1 lần
    existing_cancellation = db.scalar(
        select(OrderCancellation).where(OrderCancellation.order_id == order.id)
    )
    if existing_cancellation is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng này đã có bản ghi hủy và đã được hoàn tồn trước đó.",
        )

    previous_status = order.status
    now = datetime.now()

    # 5. TRANSACTION NGUYÊN TỬ: Cập nhật Order, hoàn tồn kho, hủy Payment, lưu lý do
    try:
        # A. Cập nhật trạng thái đơn hàng sang CANCELLED
        order.status = OrderStatus.CANCELLED.value
        order.updated_at = now

        # B. Giải phóng tồn kho: Hoàn trả số lượng cho biến thể và sản phẩm gốc
        restocked_items_count = 0
        for item in order.items:
            # Hoàn tồn cho biến thể
            if item.variant_id:
                variant = db.get(ProductVariant, item.variant_id)
                if variant:
                    variant.stock += item.quantity
                    # Đồng bộ hoàn tồn kho sản phẩm gốc nếu có quản lý stock
                    if variant.product and variant.product.stock is not None:
                        variant.product.stock += item.quantity
            elif item.product_id:
                product = db.get(Product, item.product_id)
                if product and product.stock is not None:
                    product.stock += item.quantity

            restocked_items_count += item.quantity

        # C. Hủy các thanh toán PENDING liên quan nếu có
        payments = db.scalars(select(Payment).where(Payment.order_id == order.id)).all()
        for payment in payments:
            if payment.status == PaymentStatus.PENDING.value:
                payment.status = PaymentStatus.CANCELLED.value
                payment.updated_at = now

        # D. Lưu lý do hủy vào bảng order_cancellations
        cancellation = OrderCancellation(
            order_id=order.id,
            order_code=order.order_code,
            user_id=user_id,
            reason=clean_reason,
            cancelled_by=cancelled_by,
            inventory_restocked=True,
            cancelled_at=now,
        )
        db.add(cancellation)

        # Commit toàn bộ transaction
        db.commit()
        db.refresh(order)
        db.refresh(cancellation)

        return CancelOrderResponse(
            message=f"Đơn hàng '{order.order_code}' đã được hủy thành công và hoàn trả tồn kho.",
            order_code=order.order_code,
            previous_status=previous_status,
            current_status=order.status,
            reason=cancellation.reason,
            cancelled_at=cancellation.cancelled_at,
            inventory_restocked=cancellation.inventory_restocked,
            restocked_items_count=restocked_items_count,
        )

    except Exception:
        db.rollback()
        raise


def get_order_cancellation_info(
    db: Session,
    order_code_or_id: str | int,
    user_id: int,
) -> OrderCancellation:
    """Tra cứu thông tin và lý do hủy của một đơn hàng."""
    identifier_str = str(order_code_or_id).strip()
    if identifier_str.isdigit():
        cond = (Order.id == int(identifier_str)) | (Order.order_code == identifier_str)
    else:
        cond = (Order.order_code == identifier_str)

    order = db.scalar(select(Order).where(cond, Order.customer_id == user_id))
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng '{identifier_str}'.",
        )

    cancellation = db.scalar(
        select(OrderCancellation).where(OrderCancellation.order_id == order.id)
    )
    if not cancellation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Đơn hàng '{order.order_code}' chưa có bản ghi thông tin hủy.",
        )
    return cancellation
