"""Các truy vấn quản lý cửa hàng."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.store import Store
from app.schemas.store import StoreUpdate


def get_store(db: Session, store_id: int) -> Store | None:
    return db.scalar(select(Store).where(Store.id == store_id))


def update_store(db: Session, store: Store, data: StoreUpdate) -> Store:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(store, field, value)
    db.commit()
    db.refresh(store)
    return store
