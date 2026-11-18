"""HTTP endpoints xem và cập nhật cửa hàng thuộc tài khoản hiện tại."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.crud.store import get_store, update_store
from app.db.session import get_db
from app.models.user import User
from app.schemas.store import StoreResponse, StoreUpdate

router = APIRouter(prefix="/api/stores", tags=["stores"])
DbSession = Annotated[Session, Depends(get_db)]


def _require_store_role(user: User) -> tuple[str, int | None]:
    role = user.role.upper()
    if role not in {"ADMIN", "VENDOR"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or vendor access is required.",
        )
    if role == "VENDOR" and user.store_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor account is not assigned to a store.",
        )
    return role, user.store_id


def _get_authorized_store(requested_store_id: int, db: Session, user: User):
    role, assigned_store_id = _require_store_role(user)
    if role == "VENDOR" and requested_store_id != assigned_store_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor can only manage their assigned store.",
        )
    store = get_store(db, requested_store_id)
    if store is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    return store


@router.get("/me", response_model=StoreResponse)
def read_assigned_store(
    db: DbSession,
    current_user: User = Depends(get_current_user),
):
    _, store_id = _require_store_role(current_user)
    if store_id is None:
        raise HTTPException(status_code=404, detail="No store is assigned to this account.")
    return _get_authorized_store(store_id, db, current_user)


@router.patch("/me", response_model=StoreResponse)
@router.put("/me", response_model=StoreResponse)
def edit_assigned_store(
    data: StoreUpdate,
    db: DbSession,
    current_user: User = Depends(get_current_user),
):
    _, store_id = _require_store_role(current_user)
    if store_id is None:
        raise HTTPException(status_code=404, detail="No store is assigned to this account.")
    store = _get_authorized_store(store_id, db, current_user)
    if current_user.role.upper() == "VENDOR" and data.status is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor cannot change store status",
        )
    try:
        return update_store(db, store, data)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Store name already exists for this vendor",
        ) from exc


@router.get("/{store_id}", response_model=StoreResponse)
def read_store(
    store_id: Annotated[int, Path(gt=0)],
    db: DbSession,
    current_user: User = Depends(get_current_user),
):
    return _get_authorized_store(store_id, db, current_user)


@router.patch("/{store_id}", response_model=StoreResponse)
@router.put("/{store_id}", response_model=StoreResponse)
def edit_store(
    store_id: Annotated[int, Path(gt=0)],
    data: StoreUpdate,
    db: DbSession,
    current_user: User = Depends(get_current_user),
):
    store = _get_authorized_store(store_id, db, current_user)
    if current_user.role.upper() == "VENDOR" and data.status is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor cannot change store status",
        )
    try:
        return update_store(db, store, data)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Store name already exists for this vendor",
        ) from exc
