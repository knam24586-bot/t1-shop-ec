"""Schemas Pydantic cho Admin Voucher APIs.
Tiêu chí chấp nhận:
- Admin tạo/sửa/khóa Voucher.
- Code duy nhất.
- Ngày bắt đầu < Ngày kết thúc (valid_from < valid_to).
- Không áp dụng mã bị khóa/hết hạn.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdminCreateVoucherRequest(BaseModel):
    """Dữ liệu yêu cầu Admin tạo Voucher mới."""
    code: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Mã voucher duy nhất trên toàn hệ thống (tự động chuyển chữ hoa)",
        examples=["T1CHAMPION2026"],
    )
    name: str | None = Field(None, max_length=150, description="Tên chương trình voucher")
    description: str | None = Field(None, max_length=255, description="Mô tả chi tiết")
    discount_type: str = Field(
        "PERCENTAGE",
        description="Kiểu giảm giá: PERCENTAGE (phần trăm) hoặc FIXED_AMOUNT (số tiền cố định)",
        examples=["PERCENTAGE"],
    )
    discount_value: Decimal = Field(
        ...,
        gt=0,
        description="Giá trị giảm (phần trăm 1-100 hoặc số tiền > 0)",
        examples=[15.00],
    )
    max_discount_amount: Decimal | None = Field(
        None,
        gt=0,
        description="Mức giảm tối đa (khi discount_type là PERCENTAGE)",
        examples=[200000.00],
    )
    min_order_amount: Decimal = Field(
        Decimal("0.00"),
        ge=0,
        description="Giá trị đơn hàng tối thiểu để áp dụng",
        examples=[500000.00],
    )
    valid_from: datetime = Field(..., description="Thời gian bắt đầu có hiệu lực")
    valid_to: datetime = Field(..., description="Thời gian kết thúc hiệu lực")
    usage_limit: int | None = Field(
        None,
        ge=1,
        description="Giới hạn tổng số lượt sử dụng (None = không giới hạn)",
        examples=[100],
    )
    status: str = Field(
        "ACTIVE",
        description="Trạng thái ban đầu: ACTIVE hoặc INACTIVE",
        examples=["ACTIVE"],
    )

    @model_validator(mode="after")
    def validate_voucher_rules(self) -> AdminCreateVoucherRequest:
        # Tiêu chí chấp nhận: Ngày bắt đầu < Ngày kết thúc
        if self.valid_from >= self.valid_to:
            raise ValueError("Thời gian bắt đầu (valid_from) phải nhỏ hơn thời gian kết thúc (valid_to).")

        normalized_type = self.discount_type.strip().upper()
        if normalized_type not in {"PERCENTAGE", "FIXED_AMOUNT"}:
            raise ValueError("discount_type phải là 'PERCENTAGE' hoặc 'FIXED_AMOUNT'.")

        if normalized_type == "PERCENTAGE" and self.discount_value > Decimal("100.00"):
            raise ValueError("Giảm giá phần trăm không được vượt quá 100%.")

        return self


class AdminUpdateVoucherRequest(BaseModel):
    """Dữ liệu yêu cầu Admin cập nhật Voucher."""
    name: str | None = Field(None, max_length=150)
    description: str | None = Field(None, max_length=255)
    discount_type: str | None = None
    discount_value: Decimal | None = Field(None, gt=0)
    max_discount_amount: Decimal | None = None
    min_order_amount: Decimal | None = Field(None, ge=0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    usage_limit: int | None = None
    status: str | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> AdminUpdateVoucherRequest:
        if self.valid_from is not None and self.valid_to is not None:
            if self.valid_from >= self.valid_to:
                raise ValueError("Thời gian bắt đầu (valid_from) phải nhỏ hơn thời gian kết thúc (valid_to).")
        return self


class AdminLockVoucherRequest(BaseModel):
    """Dữ liệu yêu cầu khóa Voucher."""
    reason: str | None = Field(None, description="Lý do khóa mã voucher")


class AdminVoucherResponse(BaseModel):
    """Thông tin chi tiết một Voucher dành cho Admin."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str | None = None
    description: str | None = None
    discount_type: str
    discount_value: Decimal
    max_discount_amount: Decimal | None = None
    min_order_amount: Decimal
    valid_from: datetime
    valid_to: datetime
    usage_limit: int | None = None
    used_count: int
    status: str
    created_at: datetime
    updated_at: datetime


class AdminVoucherListResponse(BaseModel):
    """Danh sách Voucher toàn hệ thống kèm phân trang."""
    model_config = ConfigDict(from_attributes=True)

    items: list[AdminVoucherResponse] = Field(default_factory=list)
    total: int
    page: int
    limit: int
    total_pages: int


class AdminVoucherActionResponse(BaseModel):
    """Phản hồi sau khi thực hiện thao tác trên Voucher."""
    model_config = ConfigDict(from_attributes=True)

    message: str
    voucher: AdminVoucherResponse


class AdminTestApplyVoucherRequest(BaseModel):
    """Dữ liệu kiểm tra thử nghiệm áp dụng Voucher."""
    code: str = Field(..., description="Mã voucher cần kiểm tra")
    order_amount: Decimal = Field(..., gt=0, description="Giá trị đơn hàng thử nghiệm")
    current_time: datetime | None = Field(None, description="Thời điểm giả lập kiểm tra")


class AdminTestApplyVoucherResponse(BaseModel):
    """Kết quả thử nghiệm áp dụng Voucher."""
    model_config = ConfigDict(from_attributes=True)

    valid: bool
    code: str
    order_amount: Decimal
    discount_amount: Decimal
    final_amount: Decimal
    message: str
