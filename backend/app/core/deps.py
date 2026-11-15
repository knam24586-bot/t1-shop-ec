"""Dependencies dùng chung cho các routers (Authentication, Current User, DB session)."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User


def get_current_user(
    x_user_id: int = Header(
        default=1,
        alias="X-User-Id",
        description="ID của người dùng hiện tại (Giả lập xác thực người dùng)",
    ),
    db: Session = Depends(get_db),
) -> User:
    """Lấy thông tin người dùng hiện tại từ header X-User-Id.
    Đảm bảo các thao tác API chỉ tác động lên dữ liệu của chính người dùng này.
    """
    user = db.get(User, x_user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Không tìm thấy người dùng với ID={x_user_id}. Vui lòng đăng nhập.",
        )
    return user

