"""HTTP endpoints quản lý sản phẩm."""
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud.product import (
    create_product,
    delete_product,
    filter_public_products,
    get_product,
    get_public_product,
    get_products,
    search_public_products,
    update_product,
)
from app.crud.product_image import (
    IMAGE_EXTENSIONS,
    delete_product_image,
    get_product_image,
    get_product_images,
    image_has_valid_signature,
    save_product_image,
)
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.category import Category
from app.models.user import User
from app.schemas.product import (
    PRODUCT_STATUSES,
    ProductCreate,
    ProductImageResponse,
    ProductResponse,
    ProductSearchResponse,
    ProductUpdate,
)

router = APIRouter(prefix="/api/products", tags=["products"])
DbSession = Annotated[Session, Depends(get_db)]
IMAGE_CHUNK_SIZE = 64 * 1024


def _role_context(
    current_user: Annotated[User, Depends(get_current_user)],
) -> tuple[str, int | None]:
    normalized_role = current_user.role.upper()
    if normalized_role not in {"ADMIN", "VENDOR"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or vendor access is required.",
        )
    store_id = current_user.store_id
    if normalized_role == "VENDOR" and store_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor account is not assigned to a store.",
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
    if product_status not in {None, "Published"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only published products are available through the public catalog.",
        )
    return get_products(
        db,
        keyword=keyword,
        category_id=category_id,
        status=product_status or "Published",
        store_id=store_id,
    )


@router.get("/search", response_model=ProductSearchResponse)
def search_products(
    db: DbSession,
    keyword: Annotated[str | None, Query(alias="q", max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    normalized_keyword = keyword.strip() if keyword is not None else ""
    if not normalized_keyword:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query parameter 'q' must not be empty",
        )
    items, total = search_public_products(
        db,
        keyword=normalized_keyword,
        page=page,
        page_size=page_size,
    )
    return ProductSearchResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/filter", response_model=ProductSearchResponse)
def filter_products(
    db: DbSession,
    category_id: Annotated[int | None, Query(gt=0)] = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    min_rating: Annotated[Decimal | None, Query(ge=0, le=5)] = None,
    max_rating: Annotated[Decimal | None, Query(ge=0, le=5)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_price must be less than or equal to max_price",
        )
    if min_rating is not None and max_rating is not None and min_rating > max_rating:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_rating must be less than or equal to max_rating",
        )

    items, total = filter_public_products(
        db,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        max_rating=max_rating,
        page=page,
        page_size=page_size,
    )
    return ProductSearchResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
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


@router.get(
    "/{product_id}/images",
    response_model=list[ProductImageResponse],
    responses={404: {"description": "Product not found"}},
)
def list_product_images(product_id: int, db: DbSession):
    product = get_public_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return get_product_images(db, product_id)


@router.post(
    "/{product_id}/images",
    response_model=ProductImageResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_product_image(
    product_id: int,
    db: DbSession,
    image: Annotated[UploadFile, File(...)],
    context: Annotated[tuple[str, int | None], Depends(_role_context)],
):
    product = get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    _check_store_access(product.store_id, *context)

    content_type = image.content_type or ""
    if content_type not in settings.allowed_image_types.intersection(IMAGE_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG, GIF, and WebP images are supported",
        )

    chunks: list[bytes] = []
    total_size = 0
    header = b""
    while True:
        chunk = image.file.read(IMAGE_CHUNK_SIZE)
        if not chunk:
            break
        if not header:
            header = chunk[:12]
        total_size += len(chunk)
        if total_size > settings.MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Image must not exceed {settings.MAX_IMAGE_SIZE_BYTES} bytes",
            )
        chunks.append(chunk)

    if not chunks or not image_has_valid_signature(content_type, header):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Uploaded file is not a valid image",
        )

    try:
        return save_product_image(
            db,
            product_id=product_id,
            content_type=content_type,
            chunks=chunks,
            size_bytes=total_size,
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store image",
        ) from exc


@router.delete(
    "/{product_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_product_image(
    product_id: int,
    image_id: int,
    db: DbSession,
    context: Annotated[tuple[str, int | None], Depends(_role_context)],
):
    product = get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    _check_store_access(product.store_id, *context)
    image = get_product_image(db, product_id, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    delete_product_image(db, image)


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
