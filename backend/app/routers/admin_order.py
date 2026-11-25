"""API Router cho Administrator theo dõi, lọc, và cập nhật đơn hàng toàn hệ thống.
Cung cấp các endpoint:
- GET /admin/orders: Lọc và xem danh sách đơn hàng toàn hệ thống (đa tiêu chí, phân trang).
- GET /admin/orders/{order_code}: Xem chi tiết toàn diện đơn hàng (khách hàng, sản phẩm, thanh toán, audit log).
- PATCH hoặc PUT /admin/orders/{order_code}/status: Cập nhật trạng thái theo quyền và quy tắc State Machine.
- POST /admin/orders/{order_code}/cancel: Admin hủy đơn hàng kèm lý do, hoàn tồn và ghi log.
- GET /admin/orders/{order_code}/audit-logs: Tra cứu lịch sử kiểm toán thao tác quan trọng của Admin.
- GET /admin/orders/{order_code}/history: Tra cứu lịch sử trạng thái của đơn hàng.
"""
from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.crud.admin_order import (
    admin_update_order_status,
    build_admin_order_detail_response,
    get_admin_order,
    get_order_audit_logs_list,
    list_all_orders_admin,
)
from app.crud.vendor_order import get_order_status_history_list
from app.db.session import get_db
from app.models.user import User
from app.schemas.admin_order import (
    AdminCancelOrderRequest,
    AdminOrderActionResponse,
    AdminOrderAuditLogResponse,
    AdminOrderDetailResponse,
    AdminOrderListResponse,
    AdminUpdateOrderStatusRequest,
)
from app.schemas.vendor_order import OrderStatusHistoryResponse

router = APIRouter(prefix="/admin/orders", tags=["Admin Orders"])


def _admin_context(
    x_role: Annotated[str | None, Header(alias="X-Role")] = None,
    x_user_id: Annotated[int | None, Header(alias="X-User-Id")] = 1,
    db: Session = Depends(get_db),
) -> tuple[int, str]:
    """Kiểm tra và xác thực quyền Administrator.
    - Chấp nhận X-Role: ADMIN hoặc User có role == 'ADMIN'.
    - Các vai trò khác (CUSTOMER, VENDOR) bị từ chối 403 Forbidden.
    """
    normalized_role = x_role.upper() if x_role else ""

    # Tra cứu user trong database nếu có x_user_id
    user_id = x_user_id if x_user_id is not None else 1
    user = db.get(User, user_id)

    if user and user.role and user.role.upper() == "ADMIN":
        return user.id, "ADMIN"

    if normalized_role == "ADMIN":
        return user_id, "ADMIN"

    # Không có quyền Administrator
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Quyền truy cập bị từ chối. Chỉ dành riêng cho Administrator.",
    )


@router.get(
    "",
    response_model=AdminOrderListResponse,
    summary="Admin theo dõi và lọc đơn hàng toàn hệ thống",
    description=(
        "Cho phép Administrator xem và lọc toàn bộ đơn hàng trong hệ thống theo nhiều tiêu chí: "
        "status, customer_id, store_id, order_code, from_date, to_date, min_price, max_price, kèm phân trang."
    ),
)
def list_orders_for_admin(
    status: str | None = Query(None, description="Lọc theo trạng thái đơn hàng (PENDING, CONFIRMED, ...)"),
    customer_id: int | None = Query(None, description="Lọc theo ID khách hàng"),
    store_id: int | None = Query(None, description="Lọc theo ID Store quản lý"),
    order_code: str | None = Query(None, description="Tìm kiếm theo mã đơn hàng"),
    from_date: datetime | None = Query(None, description="Từ ngày (ISO datetime)"),
    to_date: datetime | None = Query(None, description="Đến ngày (ISO datetime)"),
    min_price: Decimal | None = Query(None, description="Giá trị đơn hàng tối thiểu"),
    max_price: Decimal | None = Query(None, description="Giá trị đơn hàng tối đa"),
    page: int = Query(1, ge=1, description="Số trang (bắt đầu từ 1)"),
    limit: int = Query(10, ge=1, le=100, description="Số đơn hàng mỗi trang"),
    admin_ctx: tuple[int, str] = Depends(_admin_context),
    db: Session = Depends(get_db),
) -> AdminOrderListResponse:
    orders, total = list_all_orders_admin(
        db=db,
        status_filter=status,
        customer_id=customer_id,
        store_id=store_id,
        order_code=order_code,
        from_date=from_date,
        to_date=to_date,
        min_price=min_price,
        max_price=max_price,
        page=page,
        limit=limit,
    )
    items = [build_admin_order_detail_response(db, ord_obj) for ord_obj in orders]
    total_pages = math.ceil(total / limit) if limit > 0 else 0

    return AdminOrderListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get(
    "/{order_code}",
    response_model=AdminOrderDetailResponse,
    summary="Admin xem chi tiết toàn diện một đơn hàng",
    description="Xem toàn bộ thông tin đơn hàng, khách hàng, sản phẩm, thanh toán và audit log của Admin.",
)
def get_order_detail_for_admin(
    order_code: str,
    admin_ctx: tuple[int, str] = Depends(_admin_context),
    db: Session = Depends(get_db),
) -> AdminOrderDetailResponse:
    order = get_admin_order(db, order_code)
    return build_admin_order_detail_response(db, order)


@router.patch(
    "/{order_code}/status",
    response_model=AdminOrderActionResponse,
    summary="Admin cập nhật trạng thái đơn hàng theo quyền và quy tắc State Machine",
    description="Cập nhật trạng thái đơn hàng, ghi nhận lý do và lưu vết kiểm toán (Audit Log).",
)
@router.put(
    "/{order_code}/status",
    response_model=AdminOrderActionResponse,
    include_in_schema=False,
)
def update_order_status_admin_endpoint(
    order_code: str,
    payload: AdminUpdateOrderStatusRequest,
    request: Request,
    admin_ctx: tuple[int, str] = Depends(_admin_context),
    db: Session = Depends(get_db),
) -> AdminOrderActionResponse:
    admin_id, _ = admin_ctx
    client_ip = request.client.host if request.client else None
    return admin_update_order_status(
        db=db,
        order_code_or_id=order_code,
        new_status=payload.status,
        admin_id=admin_id,
        reason=payload.reason,
        admin_note=payload.admin_note,
        ip_address=client_ip,
    )


@router.post(
    "/{order_code}/cancel",
    response_model=AdminOrderActionResponse,
    summary="Admin hủy đơn hàng (kèm lý do bắt buộc, hoàn tồn và ghi audit log)",
)
def cancel_order_admin_endpoint(
    order_code: str,
    payload: AdminCancelOrderRequest,
    request: Request,
    admin_ctx: tuple[int, str] = Depends(_admin_context),
    db: Session = Depends(get_db),
) -> AdminOrderActionResponse:
    admin_id, _ = admin_ctx
    client_ip = request.client.host if request.client else None
    return admin_update_order_status(
        db=db,
        order_code_or_id=order_code,
        new_status="CANCELLED",
        admin_id=admin_id,
        reason=payload.reason,
        admin_note=payload.admin_note,
        ip_address=client_ip,
    )


@router.get(
    "/{order_code}/audit-logs",
    response_model=list[AdminOrderAuditLogResponse],
    summary="Admin tra cứu lịch sử kiểm toán thao tác quan trọng trên đơn hàng",
)
def get_order_audit_logs_endpoint(
    order_code: str,
    admin_ctx: tuple[int, str] = Depends(_admin_context),
    db: Session = Depends(get_db),
) -> list[AdminOrderAuditLogResponse]:
    logs = get_order_audit_logs_list(db, order_code)
    return [AdminOrderAuditLogResponse.model_validate(log) for log in logs]


@router.get(
    "/{order_code}/history",
    response_model=list[OrderStatusHistoryResponse],
    summary="Admin tra cứu toàn bộ dòng thời gian lịch sử trạng thái của đơn hàng",
)
def get_order_status_history_admin_endpoint(
    order_code: str,
    admin_ctx: tuple[int, str] = Depends(_admin_context),
    db: Session = Depends(get_db),
) -> list[OrderStatusHistoryResponse]:
    order = get_admin_order(db, order_code)
    stmt = (
        get_order_status_history_list(db, order_code, store_id=0)
        if False
        else None
    )
    # Tra cứu toàn bộ lịch sử trạng thái cho order này
    from app.models.order_status_history import OrderStatusHistory
    from sqlalchemy import select

    histories = db.scalars(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order.id)
        .order_by(OrderStatusHistory.created_at.asc(), OrderStatusHistory.id.asc())
    ).all()
    return [OrderStatusHistoryResponse.model_validate(h) for h in histories]
