"""Schemas Pydantic cho Voucher APIs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class VoucherCheckRequest(BaseModel):
    """Dữ liệu gửi lên để kiểm tra/áp dụng mã giảm giá."""
    code: str = Field(..., min_length=1, description="Mã voucher (VD: T1CHAMPION)")
    order_amount: Decimal = Field(..., gt=0, description="Tổng giá trị đơn hàng trước giảm (bắt buộc > 0)")
    # Client có thể cố tình gửi số tiền giảm giả mạo (để test tiêu chí 'không tin số tiền giảm từ client')
    # Server sẽ hoàn toàn bỏ qua hoặc ghi đè giá trị này và tự tính toán lại từ DB
    client_discount: Decimal | None = Field(
        None,
        description="Số tiền giảm từ client gửi lên (Server KHÔNG TIN và sẽ tự tính lại)",
    )


class VoucherResponse(BaseModel):
    """Thông tin chi tiết một voucher."""
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


class VoucherCheckResponse(BaseModel):
    """Kết quả kiểm tra và tính toán giảm giá của Voucher."""
    valid: bool = Field(True, description="Voucher có hợp lệ hay không")
    code: str = Field(..., description="Mã voucher")
    discount_type: str = Field(..., description="Kiểu giảm giá (PERCENTAGE hoặc FIXED_AMOUNT)")
    discount_value: Decimal = Field(..., description="Giá trị cấu hình giảm (% hoặc số tiền)")
    original_amount: Decimal = Field(..., description="Tổng giá trị đơn hàng trước giảm")
    discount_amount: Decimal = Field(..., description="Mức tiền được giảm (Server tính toán, không tin client)")
    final_amount: Decimal = Field(..., description="Tổng số tiền sau khi đã trừ giảm giá")
    message: str = Field(..., description="Thông báo kết quả kiểm tra")
    voucher: VoucherResponse | None = Field(None, description="Chi tiết voucher (nếu cần)")

