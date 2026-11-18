"""Dependencies dùng chung cho các routers (Authentication, Current User, DB session)."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the current active user from a verified Bearer JWT."""
    payload = decode_access_token(credentials.credentials) if credentials else None
    user_id = int(payload["sub"]) if payload else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None or user.status.casefold() != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token không hợp lệ hoặc tài khoản không hoạt động.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*roles: str):
    allowed_roles = {role.upper() for role in roles}

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.upper() not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thực hiện thao tác này.",
            )
        return current_user

    return dependency

