"""CRUD = các hàm đọc/ghi DB cho bảng items. Router gọi vào đây, không viết SQL trong router."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.item import Item
from app.schemas.item import ItemCreate, ItemUpdate


def get_items(db: Session, keyword: str | None = None) -> list[Item]:
    query = select(Item).order_by(Item.id.desc())
    if keyword:
        query = query.where(Item.name.contains(keyword))
    return list(db.scalars(query))


def get_item(db: Session, item_id: int) -> Item | None:
    return db.get(Item, item_id)


def create_item(db: Session, data: ItemCreate) -> Item:
    item = Item(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)  # lấy lại id, created_at... do MySQL sinh ra
    return item


def update_item(db: Session, item: Item, data: ItemUpdate) -> Item:
    # exclude_unset: chỉ lấy các trường FE thực sự gửi lên
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


def delete_item(db: Session, item: Item) -> None:
    db.delete(item)
    db.commit()
