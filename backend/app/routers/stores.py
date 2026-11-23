"""HTTP endpoints xem và cập nhật cửa hàng của Vendor."""
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud.store import get_store, update_store
from app.db.session import get_db
from app.schemas.store import StoreResponse, StoreUpdate

router = APIRouter(prefix="/api/stores", tags=["stores"])
DbSession = Annotated[Session, Depends(get_db)]


def _store_context(
    role: Annotated[str | None, Header(alias="X-Role")] = None,
    assigned_store_id: Annotated[int | None, Header(alias="X-Store-Id", ge=1)] = None,
) -> tuple[str, int | None]:
    normalized_role = role.strip().upper() if role else ""
    if normalized_role not in {"ADMIN", "VENDOR"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Role must be ADMIN or VENDOR",
        )
    if normalized_role == "VENDOR" and assigned_store_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Store requests require X-Store-Id",
        )
    return normalized_role, assigned_store_id


def _get_authorized_store(
    requested_store_id: int, db: Session, context: tuple[str, int | None]
):
    role, assigned_store_id = context
    if role == "VENDOR" and requested_store_id != assigned_store_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor can only manage their assigned store",
        )
    store = get_store(db, requested_store_id)
    if store is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    return store


@router.get("/me", response_model=StoreResponse)
def read_assigned_store(
    db: DbSession,
    context: Annotated[tuple[str, int | None], Depends(_store_context)],
):
    if context[1] is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="X-Store-Id is required for this endpoint",
        )
    return _get_authorized_store(context[1], db, context)


@router.patch("/me", response_model=StoreResponse)
@router.put("/me", response_model=StoreResponse)
def edit_assigned_store(
    data: StoreUpdate,
    db: DbSession,
    context: Annotated[tuple[str, int | None], Depends(_store_context)],
):
    if context[1] is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="X-Store-Id is required for this endpoint",
        )
    store = _get_authorized_store(context[1], db, context)
    if context[0] == "VENDOR" and data.status is not None:
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
    context: Annotated[tuple[str, int | None], Depends(_store_context)],
):
    return _get_authorized_store(store_id, db, context)


@router.patch("/{store_id}", response_model=StoreResponse)
@router.put("/{store_id}", response_model=StoreResponse)
def edit_store(
    store_id: Annotated[int, Path(gt=0)],
    data: StoreUpdate,
    db: DbSession,
    context: Annotated[tuple[str, int | None], Depends(_store_context)],
):
    store = _get_authorized_store(store_id, db, context)
    if context[0] == "VENDOR" and data.status is not None:
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
