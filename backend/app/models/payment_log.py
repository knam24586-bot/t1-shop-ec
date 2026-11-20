"""Model lưu vết (Audit Log) cho Webhook / Callback từ cổng thanh toán."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PaymentWebhookLog(Base):
    __tablename__ = "payment_webhook_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    transaction_reference: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    gateway: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    is_valid_signature: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    response_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<PaymentWebhookLog id={self.id} ref={self.transaction_reference} "
            f"gateway={self.gateway} valid={self.is_valid_signature}>"
        )

