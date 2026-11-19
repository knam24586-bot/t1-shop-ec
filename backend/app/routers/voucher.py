"""API Router cho kiểm tra và áp dụng mã giảm giá (Voucher).
Cung cấp các API:
- POST /vouchers/check hoặc /vouchers/validate hoặc /vouchers/apply: Kiểm tra mã, thời hạn, điều kiện và tính mức giảm.
- GET /vouchers/check: Kiểm tra mã qua query parameters.
- GET /vouchers: Xem danh sách các voucher đang hoạt động.
- GET /vouchers/{code}: Xem chi tiết một voucher.
"""
from __future__ import annotations

from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.crud.voucher import (
    get_voucher_by_code,
    list_active_vouchers,
    validate_and_calculate_voucher,
)
from app.db.session import get_db
from app.schemas.voucher import (
    VoucherCheckRequest,
    VoucherCheckResponse,
    VoucherResponse,
)

router = APIRouter(prefix="/vouchers", tags=["Vouchers"])


@router.post(
    "/check",
    response_model=VoucherCheckResponse,
    summary="Kiểm tra mã voucher và tính toán mức giảm giá",
    description="Kiểm tra mã, thời hạn, điều kiện đơn tối thiểu, số lượt dùng. Trả về mức giảm và tổng tiền sau giảm. Tuyệt đối không tin số tiền từ client.",
)
def check_voucher(
    payload: VoucherCheckRequest,
    db: Session = Depends(get_db),
) -> VoucherCheckResponse:
    return validate_and_calculate_voucher(
        db=db,
        code=payload.code,
        order_amount=payload.order_amount,
    )


@router.post(
    "/validate",
    response_model=VoucherCheckResponse,
    summary="Kiểm tra mã voucher (Alias /validate)",
)
def validate_voucher_alias(
    payload: VoucherCheckRequest,
    db: Session = Depends(get_db),
) -> VoucherCheckResponse:
    return check_voucher(payload=payload, db=db)


@router.post(
    "/apply",
    response_model=VoucherCheckResponse,
    summary="Kiểm tra và tính toán giảm giá để áp dụng cho đơn hàng (Alias /apply)",
)
def apply_voucher_alias(
    payload: VoucherCheckRequest,
    db: Session = Depends(get_db),
) -> VoucherCheckResponse:
    return check_voucher(payload=payload, db=db)


@router.get(
    "/check",
    response_model=VoucherCheckResponse,
    summary="Kiểm tra voucher qua Query Parameters",
)
def check_voucher_get(
    code: str = Query(..., description="Mã voucher cần kiểm tra"),
    order_amount: Decimal = Query(..., gt=0, description="Tổng giá trị đơn hàng trước giảm"),
    db: Session = Depends(get_db),
) -> VoucherCheckResponse:
    return validate_and_calculate_voucher(
        db=db,
        code=code,
        order_amount=order_amount,
    )


@router.get(
    "",
    response_model=list[VoucherResponse],
    summary="Danh sách các mã voucher đang hoạt động",
)
def get_active_vouchers(
    db: Session = Depends(get_db),
) -> list[VoucherResponse]:
    vouchers = list_active_vouchers(db=db)
    return [VoucherResponse.model_validate(v) for v in vouchers]


@router.get(
    "/{code}",
    response_model=VoucherResponse,
    summary="Xem thông tin chi tiết một voucher theo code",
)
def get_voucher_detail(
    code: str,
    db: Session = Depends(get_db),
) -> VoucherResponse:
    voucher = get_voucher_by_code(db=db, code=code)
    if not voucher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy mã giảm giá '{code.strip().upper()}'.",
        )
    return VoucherResponse.model_validate(voucher)

