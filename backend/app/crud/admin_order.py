"""CRUD và nghiệp vụ Quản trị đơn hàng dành cho Admin toàn hệ thống.
Tiêu chí chấp nhận:
1. ADMIN LỌC/XEM ĐƠN TOÀN HỆ THỐNG:
   - Không giới hạn bởi một customer_id hay store_id cụ thể.
   - Hỗ trợ đa dạng bộ lọc: status, customer_id, store_id, order_code, from_date, to_date, min_price, max_price.
   - Xem chi tiết toàn diện: sản phẩm, khách hàng, store, thanh toán, audit log, lịch sử trạng thái.
2. CẬP NHẬT TRẠNG THÁI THEO QUYỀN VÀ QUY TẮC:
   - Chỉ Admin mới được thực thi.
   - Tuân thủ quy tắc State Machine (VALID_STATUS_TRANSITIONS).
   - Đơn đã giao (DELIVERED) hoặc đã hủy (CANCELLED) không bị thay đổi trái quy tắc -> 400 Bad Request.
   - Khi hủy đơn: bắt buộc phải có lý do (reason) và giải phóng tồn kho.
3. THAO TÁC QUAN TRỌNG ĐƯỢC GHI LOG:
   - Ghi lại chi tiết mọi hành động cập nhật trạng thái, hủy đơn vào bảng admin_order_audit_logs.
   - Đồng bộ ghi vào order_status_histories với changed_by_role="ADMIN".
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.admin_audit_log import AdminOrderAuditLog
from app.models.order import Order, OrderStatus, VALID_STATUS_TRANSITIONS
from app.models.order_cancellation import OrderCancellation
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment, PaymentStatus
from app.models.product import Product
from app.models.store_order import StoreOrder
from app.models.user import User
from app.models.variant import ProductVariant
from app.schemas.admin_order import (
    AdminCustomerInfoResponse,
    AdminOrderDetailResponse,
    AdminOrderItemResponse,
    AdminOrderAuditLogResponse,
    AdminOrderActionResponse,
    AdminPaymentResponse,
)
from app.schemas.vendor_order import OrderStatusHistoryResponse


def get_admin_order_store_id(db: Session, order: Order) -> int | None:
    """Xác định store_id của đơn hàng (nếu có)."""
    so = db.scalar(select(StoreOrder).where(StoreOrder.order_id == order.id))
    if so is not None:
        return so.store_id

    if hasattr(order, "store_id") and getattr(order, "store_id", None) is not None:
        return getattr(order, "store_id")

    for it in order.items:
        if it.product and hasattr(it.product, "store_id"):
            sid = getattr(it.product, "store_id", None)
            if sid is not None:
                return sid
    return None


def build_admin_order_detail_response(db: Session, order: Order) -> AdminOrderDetailResponse:
    """Xây dựng dữ liệu phản hồi chi tiết toàn diện của một đơn hàng dành cho Admin."""
    store_id = get_admin_order_store_id(db, order)

    # Thông tin khách hàng
    customer_resp = None
    if order.customer:
        customer_resp = AdminCustomerInfoResponse(
            id=order.customer.id,
            full_name=order.customer.full_name,
            email=order.customer.email,
            status=order.customer.status,
        )

    # Chi tiết sản phẩm
    items_resp: list[AdminOrderItemResponse] = []
    for it in order.items:
        prod_name = it.product.name if it.product else None
        sku = it.variant.sku if it.variant else None
        color = it.variant.color if it.variant else None
        size = it.variant.size if it.variant else None

        items_resp.append(
            AdminOrderItemResponse(
                id=it.id,
                variant_id=it.variant_id,
                product_id=it.product_id,
                product_name=prod_name,
                sku=sku,
                color=color,
                size=size,
                unit_price=Decimal(str(it.unit_price)),
                quantity=it.quantity,
                line_total=Decimal(str(it.line_total)),
            )
        )

    # Thông tin thanh toán
    payment = db.scalar(
        select(Payment)
        .where(Payment.order_id == order.id)
        .order_by(Payment.attempt_number.desc(), Payment.id.desc())
        .limit(1)
    )
    payment_resp = None
    if payment:
        payment_resp = AdminPaymentResponse(
            id=payment.id,
            method=payment.method,
            amount=Decimal(str(payment.amount)),
            status=payment.status,
            transaction_reference=payment.transaction_reference,
            attempt_number=payment.attempt_number,
        )

    # Danh sách audit log của Admin
    audit_logs = db.scalars(
        select(AdminOrderAuditLog)
        .where(AdminOrderAuditLog.order_id == order.id)
        .order_by(AdminOrderAuditLog.created_at.desc(), AdminOrderAuditLog.id.desc())
    ).all()
    audit_resp = [AdminOrderAuditLogResponse.model_validate(log) for log in audit_logs]

    # Danh sách lịch sử trạng thái
    histories = db.scalars(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order.id)
        .order_by(OrderStatusHistory.created_at.asc(), OrderStatusHistory.id.asc())
    ).all()
    history_resp = [OrderStatusHistoryResponse.model_validate(h) for h in histories]

    return AdminOrderDetailResponse(
        id=order.id,
        order_code=order.order_code,
        customer_id=order.customer_id,
        customer=customer_resp,
        store_id=store_id,
        total_price=Decimal(str(order.total_price)),
        shipping_address=order.shipping_address,
        status=order.status,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=items_resp,
        payment=payment_resp,
        audit_logs=audit_resp,
        status_history=history_resp,
    )


def list_all_orders_admin(
    db: Session,
    status_filter: str | None = None,
    customer_id: int | None = None,
    store_id: int | None = None,
    order_code: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    page: int = 1,
    limit: int = 10,
) -> tuple[list[Order], int]:
    """Admin lọc và xem toàn bộ đơn hàng trong hệ thống theo nhiều tiêu chí."""
    if page < 1:
        page = 1
    if limit < 1:
        limit = 10

    stmt = select(Order)
    count_stmt = select(func.count(Order.id))

    # Bộ lọc trạng thái
    if status_filter and status_filter.strip():
        stmt = stmt.where(Order.status == status_filter.strip().upper())
        count_stmt = count_stmt.where(Order.status == status_filter.strip().upper())

    # Bộ lọc khách hàng
    if customer_id is not None:
        stmt = stmt.where(Order.customer_id == customer_id)
        count_stmt = count_stmt.where(Order.customer_id == customer_id)

    # Bộ lọc mã đơn hàng
    if order_code and order_code.strip():
        clean_code = order_code.strip()
        stmt = stmt.where(Order.order_code.ilike(f"%{clean_code}%"))
        count_stmt = count_stmt.where(Order.order_code.ilike(f"%{clean_code}%"))

    # Bộ lọc theo khoảng ngày
    if from_date is not None:
        stmt = stmt.where(Order.created_at >= from_date)
        count_stmt = count_stmt.where(Order.created_at >= from_date)
    if to_date is not None:
        stmt = stmt.where(Order.created_at <= to_date)
        count_stmt = count_stmt.where(Order.created_at <= to_date)

    # Bộ lọc theo giá trị đơn hàng
    if min_price is not None:
        stmt = stmt.where(Order.total_price >= min_price)
        count_stmt = count_stmt.where(Order.total_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Order.total_price <= max_price)
        count_stmt = count_stmt.where(Order.total_price <= max_price)

    # Bộ lọc theo store_id
    if store_id is not None:
        so_order_ids = list(
            db.scalars(select(StoreOrder.order_id).where(StoreOrder.store_id == store_id))
        )
        stmt = stmt.where(Order.id.in_(so_order_ids))
        count_stmt = count_stmt.where(Order.id.in_(so_order_ids))

    total = db.scalar(count_stmt) or 0
    if total == 0:
        return [], 0

    offset = (page - 1) * limit
    stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).offset(offset).limit(limit)
    orders = list(db.scalars(stmt))
    return orders, total


def get_admin_order(db: Session, order_code_or_id: str | int) -> Order:
    """Lấy đơn hàng bất kỳ trong hệ thống theo order_code hoặc id."""
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
    return order


def admin_update_order_status(
    db: Session,
    order_code_or_id: str | int,
    new_status: str,
    admin_id: int,
    reason: str | None = None,
    admin_note: str | None = None,
    ip_address: str | None = None,
) -> AdminOrderActionResponse:
    """Admin cập nhật trạng thái đơn hàng theo quyền và quy tắc State Machine, đồng thời ghi Audit Log."""
    order = get_admin_order(db, order_code_or_id)
    target_status = new_status.strip().upper()

    valid_enum_values = {s.value for s in OrderStatus}
    if target_status not in valid_enum_values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trạng thái '{new_status}' không hợp lệ. Danh sách hợp lệ: {', '.join(sorted(valid_enum_values))}.",
        )

    # 1. Kiểm tra quy tắc State Machine
    if order.status == OrderStatus.DELIVERED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng đã được giao thành công (DELIVERED), không thể cập nhật trạng thái trái quy tắc.",
        )

    if order.status == OrderStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đơn hàng đã ở trạng thái hủy (CANCELLED), không thể thay đổi trạng thái tiếp.",
        )

    if target_status == order.status:
        return AdminOrderActionResponse(
            message=f"Đơn hàng '{order.order_code}' đã ở trạng thái '{target_status}'.",
            order_code=order.order_code,
            previous_status=order.status,
            current_status=order.status,
            reason=reason or admin_note,
            audit_log_id=0,
            updated_at=order.updated_at,
        )

    allowed = VALID_STATUS_TRANSITIONS.get(order.status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Không thể chuyển trạng thái từ '{order.status}' sang '{target_status}'. "
                f"Quy tắc State Machine chỉ cho phép chuyển sang: {', '.join(sorted(allowed))}."
            ),
        )

    # 2. Quy tắc khi hủy đơn (CANCELLED): Bắt buộc có lý do
    clean_reason = (reason or admin_note or "").strip()
    if target_status == OrderStatus.CANCELLED.value:
        if not clean_reason or len(clean_reason) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Hủy đơn hàng bắt buộc phải có lý do (tối thiểu 3 ký tự).",
            )

    previous_status = order.status
    now = datetime.now()

    try:
        order.status = target_status
        order.updated_at = now

        # Nếu hủy đơn -> Giải phóng tồn kho và cập nhật Payment
        if target_status == OrderStatus.CANCELLED.value:
            for it in order.items:
                if it.variant_id:
                    v = db.get(ProductVariant, it.variant_id)
                    if v:
                        v.stock += it.quantity
                        if v.product and v.product.stock is not None:
                            v.product.stock += it.quantity
                elif it.product_id:
                    p = db.get(Product, it.product_id)
                    if p and p.stock is not None:
                        p.stock += it.quantity

            # Hủy payment PENDING
            payments = db.scalars(select(Payment).where(Payment.order_id == order.id)).all()
            for pay in payments:
                if pay.status == PaymentStatus.PENDING.value:
                    pay.status = PaymentStatus.CANCELLED.value
                    pay.updated_at = now

            cancellation = OrderCancellation(
                order_id=order.id,
                order_code=order.order_code,
                user_id=order.customer_id,
                reason=clean_reason,
                cancelled_by="ADMIN",
                inventory_restocked=True,
                cancelled_at=now,
            )
            db.add(cancellation)

        # 3. GHI LOG THAO TÁC QUAN TRỌNG: Lưu vào admin_order_audit_logs
        action_name = "CANCEL_ORDER" if target_status == OrderStatus.CANCELLED.value else "UPDATE_STATUS"
        audit_log = AdminOrderAuditLog(
            order_id=order.id,
            order_code=order.order_code,
            admin_id=admin_id,
            action=action_name,
            previous_status=previous_status,
            new_status=target_status,
            reason=clean_reason or None,
            ip_address=ip_address,
            created_at=now,
        )
        db.add(audit_log)

        # Đồng bộ lưu lịch sử trạng thái OrderStatusHistory
        store_id = get_admin_order_store_id(db, order)
        history = OrderStatusHistory(
            order_id=order.id,
            order_code=order.order_code,
            store_id=store_id,
            previous_status=previous_status,
            new_status=target_status,
            reason=clean_reason or "Admin cập nhật trạng thái",
            changed_by_role="ADMIN",
            changed_by_user_id=admin_id,
            created_at=now,
        )
        db.add(history)

        db.commit()
        db.refresh(order)
        db.refresh(audit_log)

        return AdminOrderActionResponse(
            message=f"Admin cập nhật trạng thái đơn '{order.order_code}' sang '{target_status}' thành công.",
            order_code=order.order_code,
            previous_status=previous_status,
            current_status=target_status,
            reason=clean_reason or None,
            audit_log_id=audit_log.id,
            updated_at=order.updated_at,
        )

    except Exception:
        db.rollback()
        raise


def get_order_audit_logs_list(db: Session, order_code_or_id: str | int) -> list[AdminOrderAuditLog]:
    """Xem toàn bộ audit log thao tác quan trọng của Admin trên đơn hàng."""
    order = get_admin_order(db, order_code_or_id)
    stmt = (
        select(AdminOrderAuditLog)
        .where(AdminOrderAuditLog.order_id == order.id)
        .order_by(AdminOrderAuditLog.created_at.desc(), AdminOrderAuditLog.id.desc())
    )
    return list(db.scalars(stmt))
