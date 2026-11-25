"""CRUD và nghiệp vụ Quản trị Voucher dành cho Admin.
Tiêu chí chấp nhận:
1. ADMIN TẠO/SỬA/KHÓA/XEM VOUCHER:
   - Tạo mới voucher.
   - Sửa thông tin voucher.
   - Khóa/mở khóa voucher (chuyển trạng thái INACTIVE/ACTIVE).
   - Xem danh sách và chi tiết voucher toàn hệ thống.
2. CODE DUY NHẤT:
   - Chuẩn hóa chữ hoa (upper).
   - Kiểm tra mã voucher không trùng lặp trong hệ thống (chặn tạo hoặc đổi sang mã đã tồn tại) -> 400 Bad Request.
3. NGÀY BẮT ĐẦU < NGÀY KẾT THÚC:
   - Kiểm tra nghiêm ngặt valid_from < valid_to.
   - Nếu valid_from >= valid_to -> 400 Bad Request.
4. KHÔNG ÁP DỤNG MÃ BỊ KHÓA / HẾT HẠN:
   - Mã có status != 'ACTIVE' (INACTIVE, DEPLETED...) -> Từ chối áp dụng (400 Bad Request).
   - Mã đã quá valid_to -> Từ chối áp dụng (400 Bad Request).
   - Mã chưa đến valid_from -> Từ chối áp dụng (400 Bad Request).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.admin_voucher_log import AdminVoucherLog
from app.models.voucher import DiscountType, Voucher, VoucherStatus
from app.schemas.admin_voucher import (
    AdminCreateVoucherRequest,
    AdminTestApplyVoucherResponse,
    AdminUpdateVoucherRequest,
    AdminVoucherResponse,
)


def admin_get_voucher(db: Session, voucher_id_or_code: str | int) -> Voucher:
    """Tìm voucher theo id hoặc code, trả về 404 nếu không tìm thấy."""
    identifier_str = str(voucher_id_or_code).strip()
    if identifier_str.isdigit():
        cond = (Voucher.id == int(identifier_str)) | (Voucher.code == identifier_str.upper())
    else:
        cond = (Voucher.code == identifier_str.upper())

    voucher = db.scalar(select(Voucher).where(cond))
    if not voucher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy mã voucher '{identifier_str}'.",
        )
    return voucher


def admin_create_voucher(
    db: Session,
    payload: AdminCreateVoucherRequest,
    admin_id: int = 1,
) -> Voucher:
    """Tạo mới Voucher cho Admin:
    - Code duy nhất: kiểm tra trùng lặp mã.
    - Ngày bắt đầu < ngày kết thúc: kiểm tra valid_from < valid_to.
    """
    clean_code = payload.code.strip().upper()

    # 1. Tiêu chí: Code duy nhất
    existing = db.scalar(select(Voucher).where(Voucher.code == clean_code))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mã voucher '{clean_code}' đã tồn tại trong hệ thống. Vui lòng chọn mã khác.",
        )

    # 2. Tiêu chí: Ngày bắt đầu < ngày kết thúc
    if payload.valid_from >= payload.valid_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thời gian bắt đầu (valid_from) phải nhỏ hơn thời gian kết thúc (valid_to).",
        )

    clean_type = payload.discount_type.strip().upper()
    if clean_type not in {DiscountType.PERCENTAGE.value, DiscountType.FIXED_AMOUNT.value}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="discount_type phải là 'PERCENTAGE' hoặc 'FIXED_AMOUNT'.",
        )

    if clean_type == DiscountType.PERCENTAGE.value and payload.discount_value > Decimal("100.00"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Giảm giá phần trăm không được vượt quá 100%.",
        )

    now = datetime.now()
    voucher = Voucher(
        code=clean_code,
        name=payload.name,
        description=payload.description,
        discount_type=clean_type,
        discount_value=payload.discount_value,
        max_discount_amount=payload.max_discount_amount,
        min_order_amount=payload.min_order_amount,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        usage_limit=payload.usage_limit,
        status=payload.status.strip().upper(),
        created_at=now,
        updated_at=now,
    )
    db.add(voucher)
    db.flush()

    # Ghi log thao tác
    log = AdminVoucherLog(
        voucher_id=voucher.id,
        voucher_code=voucher.code,
        admin_id=admin_id,
        action="CREATE",
        details=f"Tạo mới voucher '{voucher.code}'",
        created_at=now,
    )
    db.add(log)

    db.commit()
    db.refresh(voucher)
    return voucher


def admin_update_voucher(
    db: Session,
    voucher_id_or_code: str | int,
    payload: AdminUpdateVoucherRequest,
    admin_id: int = 1,
) -> Voucher:
    """Sửa thông tin Voucher:
    - Kiểm tra tính hợp lệ của thời hạn (ngày bắt đầu < ngày kết thúc).
    - Cập nhật các trường cấu hình.
    """
    voucher = admin_get_voucher(db, voucher_id_or_code)

    new_from = payload.valid_from if payload.valid_from is not None else voucher.valid_from
    new_to = payload.valid_to if payload.valid_to is not None else voucher.valid_to

    # Tiêu chí: Ngày bắt đầu < ngày kết thúc
    if new_from >= new_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thời gian bắt đầu (valid_from) phải nhỏ hơn thời gian kết thúc (valid_to).",
        )

    if payload.name is not None:
        voucher.name = payload.name
    if payload.description is not None:
        voucher.description = payload.description
    if payload.discount_type is not None:
        clean_type = payload.discount_type.strip().upper()
        if clean_type not in {DiscountType.PERCENTAGE.value, DiscountType.FIXED_AMOUNT.value}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="discount_type phải là 'PERCENTAGE' hoặc 'FIXED_AMOUNT'.",
            )
        voucher.discount_type = clean_type

    if payload.discount_value is not None:
        if voucher.discount_type == DiscountType.PERCENTAGE.value and payload.discount_value > Decimal("100.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Giảm giá phần trăm không được vượt quá 100%.",
            )
        voucher.discount_value = payload.discount_value

    if payload.max_discount_amount is not None:
        voucher.max_discount_amount = payload.max_discount_amount
    if payload.min_order_amount is not None:
        voucher.min_order_amount = payload.min_order_amount
    if payload.valid_from is not None:
        voucher.valid_from = payload.valid_from
    if payload.valid_to is not None:
        voucher.valid_to = payload.valid_to
    if payload.usage_limit is not None:
        voucher.usage_limit = payload.usage_limit
    if payload.status is not None:
        voucher.status = payload.status.strip().upper()

    now = datetime.now()
    voucher.updated_at = now

    log = AdminVoucherLog(
        voucher_id=voucher.id,
        voucher_code=voucher.code,
        admin_id=admin_id,
        action="UPDATE",
        details="Cập nhật cấu hình voucher",
        created_at=now,
    )
    db.add(log)

    db.commit()
    db.refresh(voucher)
    return voucher


def admin_lock_voucher(
    db: Session,
    voucher_id_or_code: str | int,
    reason: str | None = None,
    admin_id: int = 1,
) -> Voucher:
    """Khóa Voucher: Chuyển trạng thái sang INACTIVE để không cho phép áp dụng."""
    voucher = admin_get_voucher(db, voucher_id_or_code)
    voucher.status = VoucherStatus.INACTIVE.value
    now = datetime.now()
    voucher.updated_at = now

    log = AdminVoucherLog(
        voucher_id=voucher.id,
        voucher_code=voucher.code,
        admin_id=admin_id,
        action="LOCK",
        details=f"Khóa voucher: {reason or 'Không có lý do cụ thể'}",
        created_at=now,
    )
    db.add(log)

    db.commit()
    db.refresh(voucher)
    return voucher


def admin_unlock_voucher(
    db: Session,
    voucher_id_or_code: str | int,
    admin_id: int = 1,
) -> Voucher:
    """Mở khóa Voucher: Chuyển trạng thái sang ACTIVE."""
    voucher = admin_get_voucher(db, voucher_id_or_code)
    now = datetime.now()

    # Nếu voucher đã hết hạn, chuyển sang EXPIRED thay vì ACTIVE
    if now > voucher.valid_to:
        voucher.status = VoucherStatus.EXPIRED.value
    else:
        voucher.status = VoucherStatus.ACTIVE.value

    voucher.updated_at = now

    log = AdminVoucherLog(
        voucher_id=voucher.id,
        voucher_code=voucher.code,
        admin_id=admin_id,
        action="UNLOCK",
        details="Mở khóa voucher",
        created_at=now,
    )
    db.add(log)

    db.commit()
    db.refresh(voucher)
    return voucher


def admin_list_vouchers(
    db: Session,
    status_filter: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 10,
) -> tuple[list[Voucher], int]:
    """Xem danh sách toàn bộ voucher trong hệ thống kèm phân trang và tìm kiếm."""
    if page < 1:
        page = 1
    if limit < 1:
        limit = 10

    stmt = select(Voucher)
    count_stmt = select(func.count(Voucher.id))

    if status_filter and status_filter.strip():
        clean_status = status_filter.strip().upper()
        stmt = stmt.where(Voucher.status == clean_status)
        count_stmt = count_stmt.where(Voucher.status == clean_status)

    if search and search.strip():
        term = f"%{search.strip().upper()}%"
        stmt = stmt.where((Voucher.code.ilike(term)) | (Voucher.name.ilike(term)))
        count_stmt = count_stmt.where((Voucher.code.ilike(term)) | (Voucher.name.ilike(term)))

    total = db.scalar(count_stmt) or 0
    if total == 0:
        return [], 0

    offset = (page - 1) * limit
    stmt = stmt.order_by(Voucher.created_at.desc(), Voucher.id.desc()).offset(offset).limit(limit)
    vouchers = list(db.scalars(stmt))
    return vouchers, total


def admin_test_apply_voucher(
    db: Session,
    code: str,
    order_amount: Decimal | float | int,
    current_time: datetime | None = None,
) -> AdminTestApplyVoucherResponse:
    """Kiểm tra điều kiện áp dụng voucher:
    Tiêu chí chấp nhận: KHÔNG áp dụng mã bị khóa / hết hạn:
    - Nếu bị khóa (INACTIVE/LOCKED): Từ chối 400 Bad Request.
    - Nếu hết hạn (now > valid_to hoặc EXPIRED): Từ chối 400 Bad Request.
    - Nếu chưa đến ngày hiệu lực: Từ chối 400 Bad Request.
    - Nếu hết lượt dùng: Từ chối 400 Bad Request.
    - Nếu chưa đủ min_order_amount: Từ chối 400 Bad Request.
    """
    now = current_time or datetime.now()
    amount = Decimal(str(order_amount))

    voucher = admin_get_voucher(db, code)

    # 1. Tiêu chí: Không áp dụng mã bị khóa
    if voucher.status in {VoucherStatus.INACTIVE.value, "LOCKED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không thể áp dụng mã '{voucher.code}': Mã voucher đang bị khóa bởi quản trị viên (trạng thái: {voucher.status}).",
        )

    # 2. Tiêu chí: Không áp dụng mã hết hạn
    if now > voucher.valid_to or voucher.status == VoucherStatus.EXPIRED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không thể áp dụng mã '{voucher.code}': Mã voucher đã hết hạn sử dụng từ ngày {voucher.valid_to.strftime('%d/%m/%Y %H:%M')}.",
        )

    # 3. Kiểm tra ngày bắt đầu
    if now < voucher.valid_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không thể áp dụng mã '{voucher.code}': Mã voucher chưa có hiệu lực (bắt đầu từ {voucher.valid_from.strftime('%d/%m/%Y %H:%M')}).",
        )

    # 4. Kiểm tra hết lượt dùng
    if (voucher.usage_limit is not None and voucher.used_count >= voucher.usage_limit) or voucher.status == VoucherStatus.DEPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không thể áp dụng mã '{voucher.code}': Mã voucher đã hết số lượt sử dụng.",
        )

    # 5. Kiểm tra giá trị đơn hàng tối thiểu
    if amount < voucher.min_order_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Không thể áp dụng mã '{voucher.code}': Đơn hàng trị giá {amount:,.0f}đ "
                f"chưa đạt giá trị tối thiểu {voucher.min_order_amount:,.0f}đ."
            ),
        )

    # Tính toán mức giảm
    discount = voucher.calculate_discount(order_amount=amount, current_time=now)
    final = max(Decimal("0.00"), amount - discount)

    return AdminTestApplyVoucherResponse(
        valid=True,
        code=voucher.code,
        order_amount=amount,
        discount_amount=discount,
        final_amount=final,
        message=f"Mã voucher '{voucher.code}' hợp lệ và áp dụng thành công.",
    )
