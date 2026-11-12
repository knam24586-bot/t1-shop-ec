"""CRUD cho Category."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


def get_categories(db: Session) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.id.desc())))


def get_category(db: Session, category_id: int) -> Category | None:
    return db.get(Category, category_id)


def get_category_by_slug(db: Session, slug: str) -> Category | None:
    return db.scalar(select(Category).where(Category.slug == slug))


def create_category(db: Session, data: CategoryCreate) -> Category:
    category = Category(**data.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def update_category(
    db: Session, category: Category, data: CategoryUpdate
) -> Category:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    db.commit()
    db.refresh(category)
    return category


def disable_category(db: Session, category: Category) -> Category:
    category.status = "Inactive"
    db.commit()
    db.refresh(category)
    return category
