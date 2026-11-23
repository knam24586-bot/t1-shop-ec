"""CRUD và nghiệp vụ xử lý đơn hàng dành cho Vendor và Store.
Đảm bảo:
1. VENDOR CHỈ XEM/THAO TÁC ĐƠN THUỘC STORE CỦA MÌNH:
   - Cách ly chặt chẽ theo store_id.
   - Chặn truy cập hoặc cập nhật đơn của Store khác -> 403 Forbidden.
2. CHUYỂN TRẠNG THÁI THEO STATE MACHINE:
   - Tuân thủ nghiêm ngặt VALID_STATUS_TRANSITIONS:
     PENDING -> CONFIRMED / CANCELLED
     CONFIRMED -> PROCESSING / CANCELLED
     PROCESSING -> SHIPPED / CANCELLED
     SHIPPED -> DELIVERED / CANCELLED
     DELIVERED -> Kết thúc (không thể chuyển đổi)
     CANCELLED -> Kết thúc (không thể chuyển đổi)
   - Chuyển sai quy tắc -> 400 Bad Request.
3. TỪ CHỐI / HỦY CẦN LÝ DO VÀ LƯU LỊCH SỬ:
   - Bắt buộc phải có reason (>= 3 ký tự).
   - Lưu vào bảng order_status_histories và order_cancellations.
   - Giải phóng / hoàn tồn kho khi từ chối / hủy đơn.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus, VALID_STATUS_TRANSITIONS
from app.models.order_cancellation import OrderCancellation
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment, PaymentStatus
from app.models.product import Product
from app.models.store_order import StoreOrder
from app.models.variant import ProductVariant
from app.schemas.vendor_order import (
    OrderStatusHistoryResponse,
    VendorOrderActionResponse,
    VendorOrderItemResponse,
    VendorOrderResponse,
)


def link_order_to_store(db: Session, order_id: int, store_id: int) -> StoreOrder:
    """Gắn đơn hàng vào Store cụ thể (hỗ trợ tạo StoreOrder)."""
    existing = db.scalar(select(StoreOrder).where(StoreOrder.order_id == order_id))
    if existing:
        existing.store_id = store_id
        db.commit()
        return existing
    store_order = StoreOrder(order_id=order_id, store_id=store_id)
    db.add(store_order)
    db.commit()
    db.refresh(store_order)
    return store_order


def get_order_store_id(db: Session, order: Order) -> int | None:
    """Lấy store_id của đơn hàng: qua StoreOrder, qua order.store_id hoặc qua item.product.store_id."""
    # 1. Tra cứu qua StoreOrder
    so = db.scalar(select(StoreOrder).where(StoreOrder.order_id == order.id))
    if so is not None:
        return so.store_id

    # 2. Tra cứu qua thuộc tính store_id trên order (nếu có)
    if hasattr(order, "store_id") and getattr(order, "store_id", None) is not None:
        return getattr(order, "store_id")

    # 3. Tra cứu qua sản phẩm trong đơn hàng
    for it in order.items:
        if it.product and hasattr(it.product, "store_id"):
            prod_sid = getattr(it.product, "store_id", None)
            if prod_sid is not None:
                return prod_sid
        if it.variant and it.variant.product and hasattr(it.variant.product, "store_id"):
            prod_sid = getattr(it.variant.product, "store_id", None)
            if prod_sid is not None:
                return prod_sid

    return None


def is_order_in_store(db: Session, order: Order, store_id: int) -> bool:
    """Kiểm tra đơn hàng có thuộc về Store cụ thể hay không."""
    ord_sid = get_order_store_id(db, order)
    return ord_sid == store_id


def build_vendor_order_response(db: Session, order: Order, store_id: int | None = None) -> VendorOrderResponse:
    """Chuyển đổi Order sang VendorOrderResponse kèm danh sách sản phẩm và lịch sử trạng thái."""
    ord_store_id = store_id if store_id is not None else get_order_store_id(db, order)

    items_resp: list[VendorOrderItemResponse] = []
    for it in order.items:
        prod_name = it.product.name if it.product else None
        sku = it.variant.sku if it.variant else None
        color = it.variant.color if it.variant else None
        size = it.variant.size if it.variant else None

        items_resp.append(
            VendorOrderItemResponse(
                id=it.id,
                product_id=it.product_id,
                variant_id=it.variant_id,
                product_name=prod_name,
                sku=sku,
                color=color,
                size=size,
                unit_price=Decimal(str(it.unit_price)),
                quantity=it.quantity,
                line_total=Decimal(str(it.line_total)),
            )
        )

    # Lấy toàn bộ lịch sử trạng thái
    histories = db.scalars(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order.id)
        .order_by(OrderStatusHistory.created_at.asc(), OrderStatusHistory.id.asc())
    ).all()
    history_resp = [OrderStatusHistoryResponse.model_validate(h) for h in histories]

    return VendorOrderResponse(
        id=order.id,
        order_code=order.order_code,
        store_id=ord_store_id,
        customer_id=order.customer_id,
        total_price=Decimal(str(order.total_price)),
        shipping_address=order.shipping_address,
        status=order.status,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=items_resp,
        history=history_resp,
    )


def get_vendor_store_order(db: Session, order_code_or_id: str | int, store_id: int) -> Order:
    """Lấy đơn hàng và kiểm tra quyền: Vendor chỉ xem đơn thuộc Store của mình."""
    identifier_str = str(order_code_or_id).strip()
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

    # Tiêu chí: Vendor chỉ xem đơn thuộc Store của mình
    if not is_order_in_store(db, order, store_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền truy cập đơn hàng này. Đơn hàng không thuộc Store của bạn.",
        )

    return order


def list_vendor_store_orders(
    db: Session,
    store_id: int,
    status_filter: str | None = None,
    page: int = 1,
    limit: int = 10,
) -> tuple[list[Order], int]:
    """Danh sách đơn hàng thuộc Store của Vendor có phân trang và lọc trạng thái."""
    if page < 1:
        page = 1
    if limit < 1:
        limit = 10

    # Lấy toàn bộ order_id thuộc store_id từ StoreOrder
    so_order_ids = list(
        db.scalars(select(StoreOrder.order_id).where(StoreOrder.store_id == store_id))
    )

    if not so_order_ids:
        # Nếu chưa dùng StoreOrder, thử tìm qua item.product.store_id nếu có
        return [], 0

    stmt = select(Order).where(Order.id.in_(so_order_ids))
    if status_filter and status_filter.strip():
        stmt = stmt.where(Order.status == status_filter.strip().upper())

    # Đếm tổng số đơn
    count_stmt = select(func.count(Order.id)).where(Order.id.in_(so_order_ids))
    if status_filter and status_filter.strip():
        count_stmt = count_stmt.where(Order.status == status_filter.strip().upper())
    total = db.scalar(count_stmt) or 0

    if total == 0:
        return [], 0

    offset = (page - 1) * limit
    stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).offset(offset).limit(limit)
    orders = list(db.scalars(stmt))
    return orders, total


def confirm_vendor_order(
    db: Session,
    order_code_or_id: str | int,
    store_id: int,
    user_id: int | None = None,
) -> VendorOrderActionResponse:
    """Vendor xác nhận đơn hàng (PENDING -> CONFIRMED theo state machine)."""
    order = get_vendor_store_order(db, order_code_or_id, store_id)

    # Kiểm tra State Machine
    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Không thể xác nhận đơn hàng đang ở trạng thái '{order.status}'. "
                f"Chỉ cho phép xác nhận khi đơn ở trạng thái PENDING."
            ),
        )

    previous_status = order.status
    now = datetime.now()

    # Cập nhật trạng thái
    order.status = OrderStatus.CONFIRMED.value
    order.updated_at = now

    # Lưu lịch sử trạng thái
    history = OrderStatusHistory(
        order_id=order.id,
        order_code=order.order_code,
        store_id=store_id,
        previous_status=previous_status,
        new_status=order.status,
        reason="Vendor xác nhận đơn hàng",
        changed_by_role="VENDOR",
        changed_by_user_id=user_id,
        created_at=now,
    )
    db.add(history)
    db.commit()
    db.refresh(order)
    db.refresh(history)

    return VendorOrderActionResponse(
        message=f"Đơn hàng '{order.order_code}' đã được xác nhận thành công.",
        order_code=order.order_code,
        previous_status=previous_status,
        current_status=order.status,
        reason=history.reason,
        history_id=history.id,
        updated_at=order.updated_at,
    )


def reject_vendor_order(
    db: Session,
    order_code_or_id: str | int,
    store_id: int,
    reason: str,
    user_id: int | None = None,
) -> VendorOrderActionResponse:
    """Vendor từ chối đơn hàng (PENDING -> CANCELLED kèm lý do và lưu lịch sử, hoàn tồn)."""
    if not reason or not reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lý do từ chối/hủy đơn hàng không được để trống.",
        )
    clean_reason = reason.strip()
    if len(clean_reason) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lý do từ chối/hủy đơn hàng phải có ít nhất 3 ký tự.",
        )

    order = get_vendor_store_order(db, order_code_or_id, store_id)

    # Kiểm tra State Machine
    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Không thể từ chối đơn hàng đang ở trạng thái '{order.status}'. "
                f"Chỉ cho phép từ chối khi đơn ở trạng thái PENDING."
            ),
        )

    previous_status = order.status
    now = datetime.now()

    try:
        # Cập nhật trạng thái
        order.status = OrderStatus.CANCELLED.value
        order.updated_at = now

        # Giải phóng / hoàn trả tồn kho đúng 1 lần
        for item in order.items:
            if item.variant_id:
                variant = db.get(ProductVariant, item.variant_id)
                if variant:
                    variant.stock += item.quantity
                    if variant.product and variant.product.stock is not None:
                        variant.product.stock += item.quantity
            elif item.product_id:
                product = db.get(Product, item.product_id)
                if product and product.stock is not None:
                    product.stock += item.quantity

        # Hủy payment nếu đang PENDING
        payments = db.scalars(select(Payment).where(Payment.order_id == order.id)).all()
        for payment in payments:
            if payment.status == PaymentStatus.PENDING.value:
                payment.status = PaymentStatus.CANCELLED.value
                payment.updated_at = now

        # Lưu bản ghi OrderCancellation
        cancellation = OrderCancellation(
            order_id=order.id,
            order_code=order.order_code,
            user_id=order.customer_id,
            reason=clean_reason,
            cancelled_by="VENDOR",
            inventory_restocked=True,
            cancelled_at=now,
        )
        db.add(cancellation)

        # Lưu lịch sử trạng thái OrderStatusHistory
        history = OrderStatusHistory(
            order_id=order.id,
            order_code=order.order_code,
            store_id=store_id,
            previous_status=previous_status,
            new_status=order.status,
            reason=clean_reason,
            changed_by_role="VENDOR",
            changed_by_user_id=user_id,
            created_at=now,
        )
        db.add(history)

        db.commit()
        db.refresh(order)
        db.refresh(history)

        return VendorOrderActionResponse(
            message=f"Đơn hàng '{order.order_code}' đã bị từ chối và hoàn tồn thành công.",
            order_code=order.order_code,
            previous_status=previous_status,
            current_status=order.status,
            reason=clean_reason,
            history_id=history.id,
            updated_at=order.updated_at,
        )
    except Exception:
        db.rollback()
        raise


def update_vendor_order_status(
    db: Session,
    order_code_or_id: str | int,
    store_id: int,
    new_status: str,
    reason: str | None = None,
    user_id: int | None = None,
) -> VendorOrderActionResponse:
    """Cập nhật trạng thái đơn hàng theo State Machine:
    PENDING -> CONFIRMED / CANCELLED
    CONFIRMED -> PROCESSING / CANCELLED
    PROCESSING -> SHIPPED / CANCELLED
    SHIPPED -> DELIVERED / CANCELLED
    DELIVERED / CANCELLED -> Không thể chuyển đổi tiếp
    """
    order = get_vendor_store_order(db, order_code_or_id, store_id)
    target_status = new_status.strip().upper()

    # Kiểm tra trạng thái đích có hợp lệ theo enum không
    valid_enum_values = {s.value for s in OrderStatus}
    if target_status not in valid_enum_values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trạng thái '{new_status}' không hợp lệ. Các trạng thái hợp lệ: {', '.join(sorted(valid_enum_values))}.",
        )

    # Nếu giữ nguyên trạng thái
    if target_status == order.status:
        return VendorOrderActionResponse(
            message=f"Đơn hàng '{order.order_code}' đã ở trạng thái '{target_status}'.",
            order_code=order.order_code,
            previous_status=order.status,
            current_status=order.status,
            reason=reason,
            updated_at=order.updated_at,
        )

    # 1. Kiểm tra State Machine: chuyển đổi có hợp lệ không
    allowed_transitions = VALID_STATUS_TRANSITIONS.get(order.status, set())
    if target_status not in allowed_transitions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Không thể chuyển trạng thái từ '{order.status}' sang '{target_status}'. "
                f"Quy tắc State Machine chỉ cho phép chuyển sang: "
                f"{', '.join(sorted(allowed_transitions)) if allowed_transitions else 'Không có (trạng thái kết thúc)'}."
            ),
        )

    # 2. Tiêu chí: Từ chối / Hủy cần lý do
    clean_reason = reason.strip() if reason and reason.strip() else None
    if target_status == OrderStatus.CANCELLED.value:
        if not clean_reason or len(clean_reason) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Từ chối/hủy đơn hàng bắt buộc phải có lý do (tối thiểu 3 ký tự).",
            )

    previous_status = order.status
    now = datetime.now()

    try:
        order.status = target_status
        order.updated_at = now

        # Nếu hủy đơn -> giải phóng tồn kho
        if target_status == OrderStatus.CANCELLED.value:
            for item in order.items:
                if item.variant_id:
                    variant = db.get(ProductVariant, item.variant_id)
                    if variant:
                        variant.stock += item.quantity
                        if variant.product and variant.product.stock is not None:
                            variant.product.stock += item.quantity
                elif item.product_id:
                    product = db.get(Product, item.product_id)
                    if product and product.stock is not None:
                        product.stock += item.quantity

            # Hủy payment nếu PENDING
            payments = db.scalars(select(Payment).where(Payment.order_id == order.id)).all()
            for payment in payments:
                if payment.status == PaymentStatus.PENDING.value:
                    payment.status = PaymentStatus.CANCELLED.value
                    payment.updated_at = now

            cancellation = OrderCancellation(
                order_id=order.id,
                order_code=order.order_code,
                user_id=order.customer_id,
                reason=clean_reason,
                cancelled_by="VENDOR",
                inventory_restocked=True,
                cancelled_at=now,
            )
            db.add(cancellation)

        # Lưu lịch sử chuyển đổi trạng thái
        history = OrderStatusHistory(
            order_id=order.id,
            order_code=order.order_code,
            store_id=store_id,
            previous_status=previous_status,
            new_status=target_status,
            reason=clean_reason,
            changed_by_role="VENDOR",
            changed_by_user_id=user_id,
            created_at=now,
        )
        db.add(history)

        db.commit()
        db.refresh(order)
        db.refresh(history)

        return VendorOrderActionResponse(
            message=f"Cập nhật trạng thái đơn '{order.order_code}' sang '{target_status}' thành công.",
            order_code=order.order_code,
            previous_status=previous_status,
            current_status=target_status,
            reason=clean_reason,
            history_id=history.id,
            updated_at=order.updated_at,
        )
    except Exception:
        db.rollback()
        raise


def get_order_status_history_list(
    db: Session,
    order_code_or_id: str | int,
    store_id: int,
) -> list[OrderStatusHistory]:
    """Xem toàn bộ dòng thời gian lịch sử trạng thái của đơn hàng thuộc Store."""
    order = get_vendor_store_order(db, order_code_or_id, store_id)
    stmt = (
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order.id)
        .order_by(OrderStatusHistory.created_at.asc(), OrderStatusHistory.id.asc())
    )
    return list(db.scalars(stmt))
