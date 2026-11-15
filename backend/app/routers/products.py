"""HTTP endpoints quản lý sản phẩm."""
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud.product import (
    create_product,
    delete_product,
    get_product,
    get_public_product,
    get_products,
    update_product,
)
from app.db.session import get_db
from app.models.category import Category
from app.schemas.product import (
    PRODUCT_STATUSES,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)

router = APIRouter(prefix="/api/products", tags=["products"])
DbSession = Annotated[Session, Depends(get_db)]


def _role_context(
    role: Annotated[str | None, Header(alias="X-Role")] = None,
    store_id: Annotated[int | None, Header(alias="X-Store-Id")] = None,
) -> tuple[str, int | None]:
    normalized_role = role.upper() if role else ""
    if normalized_role not in {"ADMIN", "VENDOR"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Role must be ADMIN or VENDOR",
        )
    if normalized_role == "VENDOR" and store_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor requests require X-Store-Id",
        )
    return normalized_role, store_id


def _check_store_access(product_store_id: int | None, role: str, store_id: int | None) -> None:
    if role == "VENDOR" and product_store_id != store_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor can only manage products in their store",
        )


def _check_category(db: Session, category_id: int) -> None:
    if db.get(Category, category_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Category not found",
        )


@router.get("", response_model=list[ProductResponse])
def list_products(
    db: DbSession,
    keyword: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    category_id: Annotated[int | None, Query(gt=0)] = None,
    product_status: Annotated[str | None, Query(alias="status")] = None,
    store_id: Annotated[int | None, Query(gt=0)] = None,
):
    if product_status is not None and product_status not in PRODUCT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of {sorted(PRODUCT_STATUSES)}",
        )
    return get_products(
        db,
        keyword=keyword,
        category_id=category_id,
        status=product_status,
        store_id=store_id,
    )


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    responses={404: {"description": "Product not found"}},
)
def read_product(product_id: int, db: DbSession):
    product = get_public_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get(
    "/{product_id}/details",
    response_model=ProductResponse,
    responses={404: {"description": "Product not found"}},
)
def read_product_details(product_id: int, db: DbSession):
    product = get_public_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def add_product(
    data: ProductCreate,
    db: DbSession,
    context: Annotated[tuple[str, int | None], Depends(_role_context)],
):
    role, store_id = context
    _check_category(db, data.category_id)
    if role == "VENDOR":
        if data.store_id is not None and data.store_id != store_id:
            raise HTTPException(
                status_code=403,
                detail="Product store does not match vendor store",
            )
        data.store_id = store_id
    try:
        return create_product(db, data)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Product slug or variant SKU already exists",
        ) from exc


@router.patch("/{product_id}", response_model=ProductResponse)
def edit_product(
    product_id: int,
    data: ProductUpdate,
    db: DbSession,
    context: Annotated[tuple[str, int | None], Depends(_role_context)],
):
    product = get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    role, store_id = context
    _check_store_access(product.store_id, role, store_id)
    if data.category_id is not None:
        _check_category(db, data.category_id)
    if role == "VENDOR" and data.store_id is not None and data.store_id != store_id:
        raise HTTPException(
            status_code=403,
            detail="Product store does not match vendor store",
        )
    try:
        return update_product(db, product, data)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Product slug or variant SKU already exists",
        ) from exc


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_product(
    product_id: int,
    db: DbSession,
    context: Annotated[tuple[str, int | None], Depends(_role_context)],
):
    product = get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    _check_store_access(product.store_id, *context)
    delete_product(db, product)
