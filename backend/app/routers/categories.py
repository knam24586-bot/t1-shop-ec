"""Endpoint quản trị danh mục sản phẩm."""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud.category import (
    create_category,
    disable_category,
    get_categories,
    get_category,
    get_category_by_slug,
    update_category,
)
from app.db.session import get_db
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["Categories"])


def require_admin(x_admin_role: str | None = Header(default=None)) -> None:
    if x_admin_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role is required",
        )


def validate_parent(
    db: Session, parent_id: int | None, category_id: int | None = None
) -> None:
    if parent_id is None:
        return
    if category_id is not None and parent_id == category_id:
        raise HTTPException(status_code=400, detail="A category cannot be its own parent")
    if get_category(db, parent_id) is None:
        raise HTTPException(status_code=400, detail="Parent category does not exist")


def ensure_unique_slug(db: Session, slug: str, category_id: int | None = None) -> None:
    category = get_category_by_slug(db, slug)
    if category is not None and category.id != category_id:
        raise HTTPException(status_code=409, detail="Category slug already exists")


@router.get("", response_model=list[CategoryRead])
def list_categories(db: Session = Depends(get_db)) -> list[Category]:
    return get_categories(db)


@router.get("/{category_id}", response_model=CategoryRead)
def read_category(category_id: int, db: Session = Depends(get_db)) -> Category:
    category = get_category(db, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def add_category(data: CategoryCreate, db: Session = Depends(get_db)) -> Category:
    validate_parent(db, data.parent_id)
    ensure_unique_slug(db, data.slug)
    try:
        return create_category(db, data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category already exists")


@router.put(
    "/{category_id}",
    response_model=CategoryRead,
    dependencies=[Depends(require_admin)],
)
def edit_category(
    category_id: int, data: CategoryUpdate, db: Session = Depends(get_db)
) -> Category:
    category = get_category(db, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    validate_parent(db, data.parent_id, category_id)
    if data.slug is not None:
        ensure_unique_slug(db, data.slug, category_id)
    try:
        return update_category(db, category, data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category already exists")


@router.patch(
    "/{category_id}/disable",
    response_model=CategoryRead,
    dependencies=[Depends(require_admin)],
)
def deactivate_category(
    category_id: int, db: Session = Depends(get_db)
) -> Category:
    category = get_category(db, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return disable_category(db, category)
