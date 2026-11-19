"""CRUD và logic kiểm tra, tính toán giảm giá của Voucher.
Đảm bảo kiểm tra đầy đủ thời hạn, trạng thái, điều kiện đơn tối thiểu, số lượt dùng,
và KHÔNG TIN số tiền giảm từ client.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.voucher import Voucher, VoucherStatus
from app.schemas.voucher import VoucherCheckResponse, VoucherResponse


def get_voucher_by_code(db: Session, code: str) -> Voucher | None:
    """Tìm voucher theo code (chuẩn hóa chữ hoa và loại bỏ khoảng trắng thừa)."""
    if not code:
        return None
    normalized_code = code.strip().upper()
    stmt = select(Voucher).where(Voucher.code == normalized_code)
    return db.scalar(stmt)


def validate_and_calculate_voucher(
    db: Session,
    code: str,
    order_amount: Decimal | float | int,
    current_time: datetime | None = None,
) -> VoucherCheckResponse:
    """Kiểm tra mã, thời hạn, điều kiện và tính mức giảm.
    Tiêu chí chấp nhận:
    1. Voucher hợp lệ: Trả mức giảm và tổng sau giảm chính xác.
    2. Mã hết hạn / sai điều kiện: Bị từ chối (ném HTTPException 400 hoặc 404 kèm chi tiết).
    3. Không tin số tiền giảm từ client: Mọi phép tính đều dựa trên order_amount và cấu hình trong DB.
    """
    now = current_time or datetime.now()
    amount = Decimal(str(order_amount))
    if amount <= Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tổng tiền đơn hàng phải lớn hơn 0 để áp dụng voucher.",
        )

    voucher = get_voucher_by_code(db, code)
    if not voucher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mã giảm giá '{code.strip().upper()}' không tồn tại.",
        )

    # 1. Kiểm tra trạng thái và thời hạn thông qua phương thức model is_valid_for_order
    is_valid, reason = voucher.is_valid_for_order(order_amount=amount, current_time=now)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không thể áp dụng mã '{voucher.code}': {reason}",
        )

    # 2. Server tự tính toán mức giảm - KHÔNG TIN SỐ TIỀN GIẢM TỪ CLIENT
    discount_amount = voucher.calculate_discount(order_amount=amount, current_time=now)
    final_amount = max(Decimal("0.00"), amount - discount_amount)

    voucher_resp = VoucherResponse(
        id=voucher.id,
        code=voucher.code,
        name=voucher.name,
        description=voucher.description,
        discount_type=voucher.discount_type,
        discount_value=voucher.discount_value,
        max_discount_amount=voucher.max_discount_amount,
        min_order_amount=voucher.min_order_amount,
        valid_from=voucher.valid_from,
        valid_to=voucher.valid_to,
        usage_limit=voucher.usage_limit,
        used_count=voucher.used_count,
        status=voucher.status,
    )

    return VoucherCheckResponse(
        valid=True,
        code=voucher.code,
        discount_type=voucher.discount_type,
        discount_value=voucher.discount_value,
        original_amount=amount,
        discount_amount=discount_amount,
        final_amount=final_amount,
        message=f"Áp dụng mã giảm giá '{voucher.code}' thành công.",
        voucher=voucher_resp,
    )


def list_active_vouchers(
    db: Session,
    current_time: datetime | None = None,
) -> list[Voucher]:
    """Danh sách các voucher đang có hiệu lực và còn lượt dùng."""
    now = current_time or datetime.now()
    stmt = (
        select(Voucher)
        .where(
            Voucher.status == VoucherStatus.ACTIVE.value,
            Voucher.valid_from <= now,
            Voucher.valid_to >= now,
        )
        .order_by(Voucher.created_at.desc())
    )
    vouchers = list(db.scalars(stmt))
    return [v for v in vouchers if v.usage_limit is None or v.used_count < v.usage_limit]

