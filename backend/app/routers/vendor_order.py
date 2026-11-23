"""API Router cho Vendor xem, xác nhận/từ chối và cập nhật đơn hàng của Store.
Cung cấp các endpoint:
- GET /vendor/orders: Vendor xem danh sách đơn hàng thuộc Store của mình (có lọc status, phân trang).
- GET /vendor/orders/{order_code}: Vendor xem chi tiết đơn hàng thuộc Store.
- POST /vendor/orders/{order_code}/confirm: Vendor xác nhận đơn hàng (PENDING -> CONFIRMED).
- POST /vendor/orders/{order_code}/reject: Vendor từ chối đơn hàng (PENDING -> CANCELLED kèm lý do).
- PATCH hoặc PUT /vendor/orders/{order_code}/status: Cập nhật trạng thái theo State Machine.
- GET /vendor/orders/{order_code}/history: Xem lịch sử các lần chuyển trạng thái của đơn.
"""
from __future__ import annotations

import math
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.crud.vendor_order import (
    build_vendor_order_response,
    confirm_vendor_order,
    get_order_status_history_list,
    get_vendor_store_order,
    list_vendor_store_orders,
    reject_vendor_order,
    update_vendor_order_status,
)
from app.db.session import get_db
from app.schemas.vendor_order import (
    OrderStatusHistoryResponse,
    VendorOrderActionResponse,
    VendorOrderListResponse,
    VendorOrderRejectRequest,
    VendorOrderResponse,
    VendorOrderUpdateStatusRequest,
)

router = APIRouter(prefix="/vendor/orders", tags=["Vendor Orders"])
store_orders_router = APIRouter(prefix="/stores", tags=["Store Vendor Orders"])


def _vendor_context(
    x_role: Annotated[str | None, Header(alias="X-Role")] = None,
    x_store_id: Annotated[int | None, Header(alias="X-Store-Id")] = None,
    x_user_id: Annotated[int | None, Header(alias="X-User-Id")] = 1,
) -> tuple[str, int, int]:
    """Xác thực vai trò và Store được gán cho Vendor.
    - Role phải là VENDOR hoặc ADMIN.
    - Bắt buộc có X-Store-Id để biết Store quản lý.
    """
    normalized_role = x_role.upper() if x_role else ""
    if not normalized_role:
        # Nếu có store_id thì mặc định role là VENDOR
        if x_store_id is not None:
            normalized_role = "VENDOR"
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-Role must be ADMIN or VENDOR",
            )

    if normalized_role not in {"ADMIN", "VENDOR"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Role must be ADMIN or VENDOR",
        )

    if x_store_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor requests require X-Store-Id",
        )

    user_id = x_user_id if x_user_id is not None else 1
    return normalized_role, x_store_id, user_id


@router.get(
    "",
    response_model=VendorOrderListResponse,
    summary="Vendor xem danh sách đơn hàng thuộc Store của mình",
    description="Chỉ hiển thị các đơn hàng thuộc Store của Vendor (X-Store-Id). Hỗ trợ lọc trạng thái và phân trang.",
)
def list_orders_for_vendor(
    status: str | None = Query(None, description="Lọc theo trạng thái đơn hàng (PENDING, CONFIRMED, ...)"),
    page: int = Query(1, ge=1, description="Số trang (bắt đầu từ 1)"),
    limit: int = Query(10, ge=1, le=100, description="Số đơn hàng mỗi trang"),
    context: tuple[str, int, int] = Depends(_vendor_context),
    db: Session = Depends(get_db),
) -> VendorOrderListResponse:
    _, store_id, _ = context
    orders, total = list_vendor_store_orders(
        db=db,
        store_id=store_id,
        status_filter=status,
        page=page,
        limit=limit,
    )
    items = [build_vendor_order_response(db, ord_obj, store_id=store_id) for ord_obj in orders]
    total_pages = math.ceil(total / limit) if limit > 0 else 0

    return VendorOrderListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get(
    "/{order_code}",
    response_model=VendorOrderResponse,
    summary="Vendor xem chi tiết một đơn hàng thuộc Store của mình",
    description="Chỉ cho phép xem nếu đơn hàng thuộc đúng Store của Vendor (X-Store-Id).",
)
def get_order_detail_for_vendor(
    order_code: str,
    context: tuple[str, int, int] = Depends(_vendor_context),
    db: Session = Depends(get_db),
) -> VendorOrderResponse:
    _, store_id, _ = context
    order = get_vendor_store_order(db, order_code, store_id)
    return build_vendor_order_response(db, order, store_id=store_id)


@router.post(
    "/{order_code}/confirm",
    response_model=VendorOrderActionResponse,
    summary="Vendor xác nhận đơn hàng (PENDING -> CONFIRMED)",
)
def confirm_order_endpoint(
    order_code: str,
    context: tuple[str, int, int] = Depends(_vendor_context),
    db: Session = Depends(get_db),
) -> VendorOrderActionResponse:
    _, store_id, user_id = context
    return confirm_vendor_order(
        db=db,
        order_code_or_id=order_code,
        store_id=store_id,
        user_id=user_id,
    )


@router.post(
    "/{order_code}/reject",
    response_model=VendorOrderActionResponse,
    summary="Vendor từ chối đơn hàng (PENDING -> CANCELLED kèm lý do và lưu lịch sử)",
)
def reject_order_endpoint(
    order_code: str,
    payload: VendorOrderRejectRequest,
    context: tuple[str, int, int] = Depends(_vendor_context),
    db: Session = Depends(get_db),
) -> VendorOrderActionResponse:
    _, store_id, user_id = context
    return reject_vendor_order(
        db=db,
        order_code_or_id=order_code,
        store_id=store_id,
        reason=payload.reason,
        user_id=user_id,
    )


@router.patch(
    "/{order_code}/status",
    response_model=VendorOrderActionResponse,
    summary="Vendor cập nhật trạng thái đơn hàng theo State Machine",
)
@router.put(
    "/{order_code}/status",
    response_model=VendorOrderActionResponse,
    include_in_schema=False,
)
def update_order_status_endpoint(
    order_code: str,
    payload: VendorOrderUpdateStatusRequest,
    context: tuple[str, int, int] = Depends(_vendor_context),
    db: Session = Depends(get_db),
) -> VendorOrderActionResponse:
    _, store_id, user_id = context
    return update_vendor_order_status(
        db=db,
        order_code_or_id=order_code,
        store_id=store_id,
        new_status=payload.status,
        reason=payload.reason,
        user_id=user_id,
    )


@router.get(
    "/{order_code}/history",
    response_model=list[OrderStatusHistoryResponse],
    summary="Xem toàn bộ lịch sử chuyển trạng thái của đơn hàng",
)
def get_order_history_endpoint(
    order_code: str,
    context: tuple[str, int, int] = Depends(_vendor_context),
    db: Session = Depends(get_db),
) -> list[OrderStatusHistoryResponse]:
    _, store_id, _ = context
    histories = get_order_status_history_list(db, order_code, store_id)
    return [OrderStatusHistoryResponse.model_validate(h) for h in histories]


# Mount thêm các endpoint dạng /stores/{store_id}/orders
@store_orders_router.get(
    "/{store_id}/orders",
    response_model=VendorOrderListResponse,
    summary="Danh sách đơn hàng của Store (Alias /stores/{store_id}/orders)",
)
def list_store_orders_alias(
    store_id: int,
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    context: tuple[str, int, int] = Depends(_vendor_context),
    db: Session = Depends(get_db),
) -> VendorOrderListResponse:
    role, assigned_store_id, _ = context
    if role == "VENDOR" and store_id != assigned_store_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor can only manage their assigned store",
        )
    orders, total = list_vendor_store_orders(
        db=db,
        store_id=store_id,
        status_filter=status,
        page=page,
        limit=limit,
    )
    items = [build_vendor_order_response(db, ord_obj, store_id=store_id) for ord_obj in orders]
    total_pages = math.ceil(total / limit) if limit > 0 else 0

    return VendorOrderListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )
