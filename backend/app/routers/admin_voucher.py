"""API Router cho Administrator tạo, sửa, khóa, mở khóa và xem Voucher.
Cung cấp các endpoint:
- POST /admin/vouchers: Tạo mới voucher (code duy nhất, ngày bắt đầu < ngày kết thúc).
- GET /admin/vouchers: Xem danh sách voucher toàn hệ thống (kèm lọc status, tìm kiếm, phân trang).
- GET /admin/vouchers/{identifier}: Xem chi tiết một voucher theo ID hoặc Code.
- PUT /admin/vouchers/{identifier}: Cập nhật thông tin voucher.
- PATCH /admin/vouchers/{identifier}: Cập nhật một phần voucher.
- POST /admin/vouchers/{identifier}/lock: Khóa voucher (chuyển sang INACTIVE).
- POST /admin/vouchers/{identifier}/unlock: Mở khóa voucher.
- POST /admin/vouchers/test-apply: Thử nghiệm áp dụng voucher (chặn mã bị khóa/hết hạn).
"""
from __future__ import annotations

import math
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.crud.admin_voucher import (
    admin_create_voucher,
    admin_get_voucher,
    admin_list_vouchers,
    admin_lock_voucher,
    admin_test_apply_voucher,
    admin_unlock_voucher,
    admin_update_voucher,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.admin_voucher import (
    AdminCreateVoucherRequest,
    AdminLockVoucherRequest,
    AdminTestApplyVoucherRequest,
    AdminTestApplyVoucherResponse,
    AdminUpdateVoucherRequest,
    AdminVoucherActionResponse,
    AdminVoucherListResponse,
    AdminVoucherResponse,
)

router = APIRouter(prefix="/admin/vouchers", tags=["Admin Vouchers"])


def _admin_auth(
    x_role: Annotated[str | None, Header(alias="X-Role")] = None,
    x_user_id: Annotated[int | None, Header(alias="X-User-Id")] = 1,
    db: Session = Depends(get_db),
) -> int:
    """Xác thực quyền Administrator:
    - Chấp nhận X-Role: ADMIN hoặc User có role == 'ADMIN'.
    - Các vai trò khác bị từ chối 403 Forbidden.
    """
    normalized_role = x_role.upper() if x_role else ""
    user_id = x_user_id if x_user_id is not None else 1
    user = db.get(User, user_id)

    if user and user.role and user.role.upper() == "ADMIN":
        return user.id

    if normalized_role == "ADMIN":
        return user_id

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Quyền truy cập bị từ chối. Chỉ dành riêng cho Administrator.",
    )


@router.post(
    "",
    response_model=AdminVoucherActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin tạo mới mã Voucher",
    description="Tạo mới voucher với mã duy nhất, kiểm tra ngày bắt đầu < ngày kết thúc.",
)
def create_voucher_endpoint(
    payload: AdminCreateVoucherRequest,
    admin_id: int = Depends(_admin_auth),
    db: Session = Depends(get_db),
) -> AdminVoucherActionResponse:
    voucher = admin_create_voucher(db=db, payload=payload, admin_id=admin_id)
    return AdminVoucherActionResponse(
        message=f"Tạo mới mã voucher '{voucher.code}' thành công.",
        voucher=AdminVoucherResponse.model_validate(voucher),
    )


@router.get(
    "",
    response_model=AdminVoucherListResponse,
    summary="Admin xem danh sách toàn bộ Voucher",
    description="Xem tất cả voucher trong hệ thống, hỗ trợ lọc trạng thái (ACTIVE, INACTIVE, EXPIRED...), tìm kiếm theo code/name và phân trang.",
)
def list_vouchers_endpoint(
    status: str | None = Query(None, description="Lọc theo trạng thái (ACTIVE, INACTIVE, EXPIRED, DEPLETED)"),
    search: str | None = Query(None, description="Tìm kiếm theo mã hoặc tên voucher"),
    page: int = Query(1, ge=1, description="Số trang (bắt đầu từ 1)"),
    limit: int = Query(10, ge=1, le=100, description="Số lượng mỗi trang"),
    admin_id: int = Depends(_admin_auth),
    db: Session = Depends(get_db),
) -> AdminVoucherListResponse:
    vouchers, total = admin_list_vouchers(
        db=db,
        status_filter=status,
        search=search,
        page=page,
        limit=limit,
    )
    items = [AdminVoucherResponse.model_validate(v) for v in vouchers]
    total_pages = math.ceil(total / limit) if limit > 0 else 0

    return AdminVoucherListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get(
    "/{identifier}",
    response_model=AdminVoucherResponse,
    summary="Admin xem chi tiết một Voucher theo ID hoặc Code",
)
def get_voucher_detail_endpoint(
    identifier: str,
    admin_id: int = Depends(_admin_auth),
    db: Session = Depends(get_db),
) -> AdminVoucherResponse:
    voucher = admin_get_voucher(db, identifier)
    return AdminVoucherResponse.model_validate(voucher)


@router.put(
    "/{identifier}",
    response_model=AdminVoucherActionResponse,
    summary="Admin sửa thông tin Voucher (PUT)",
)
@router.patch(
    "/{identifier}",
    response_model=AdminVoucherActionResponse,
    include_in_schema=False,
)
def update_voucher_endpoint(
    identifier: str,
    payload: AdminUpdateVoucherRequest,
    admin_id: int = Depends(_admin_auth),
    db: Session = Depends(get_db),
) -> AdminVoucherActionResponse:
    voucher = admin_update_voucher(
        db=db,
        voucher_id_or_code=identifier,
        payload=payload,
        admin_id=admin_id,
    )
    return AdminVoucherActionResponse(
        message=f"Cập nhật mã voucher '{voucher.code}' thành công.",
        voucher=AdminVoucherResponse.model_validate(voucher),
    )


@router.post(
    "/{identifier}/lock",
    response_model=AdminVoucherActionResponse,
    summary="Admin khóa Voucher (chuyển sang trạng thái INACTIVE)",
)
@router.patch(
    "/{identifier}/lock",
    response_model=AdminVoucherActionResponse,
    include_in_schema=False,
)
def lock_voucher_endpoint(
    identifier: str,
    payload: AdminLockVoucherRequest = AdminLockVoucherRequest(),
    admin_id: int = Depends(_admin_auth),
    db: Session = Depends(get_db),
) -> AdminVoucherActionResponse:
    voucher = admin_lock_voucher(
        db=db,
        voucher_id_or_code=identifier,
        reason=payload.reason,
        admin_id=admin_id,
    )
    return AdminVoucherActionResponse(
        message=f"Đã khóa mã voucher '{voucher.code}' thành công.",
        voucher=AdminVoucherResponse.model_validate(voucher),
    )


@router.post(
    "/{identifier}/unlock",
    response_model=AdminVoucherActionResponse,
    summary="Admin mở khóa Voucher (chuyển sang trạng thái ACTIVE)",
)
@router.patch(
    "/{identifier}/unlock",
    response_model=AdminVoucherActionResponse,
    include_in_schema=False,
)
def unlock_voucher_endpoint(
    identifier: str,
    admin_id: int = Depends(_admin_auth),
    db: Session = Depends(get_db),
) -> AdminVoucherActionResponse:
    voucher = admin_unlock_voucher(
        db=db,
        voucher_id_or_code=identifier,
        admin_id=admin_id,
    )
    return AdminVoucherActionResponse(
        message=f"Đã mở khóa mã voucher '{voucher.code}' thành công.",
        voucher=AdminVoucherResponse.model_validate(voucher),
    )


@router.post(
    "/test-apply",
    response_model=AdminTestApplyVoucherResponse,
    summary="Kiểm tra thử nghiệm áp dụng Voucher (chặn mã bị khóa hoặc hết hạn)",
)
def test_apply_voucher_endpoint(
    payload: AdminTestApplyVoucherRequest,
    admin_id: int = Depends(_admin_auth),
    db: Session = Depends(get_db),
) -> AdminTestApplyVoucherResponse:
    return admin_test_apply_voucher(
        db=db,
        code=payload.code,
        order_amount=payload.order_amount,
        current_time=payload.current_time,
    )
