"""CRUD cho sản phẩm."""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.models.variant import ProductVariant
from app.schemas.product import ProductCreate, ProductUpdate


def get_products(
    db: Session,
    *,
    keyword: str | None = None,
    category_id: int | None = None,
    status: str | None = None,
    store_id: int | None = None,
) -> list[Product]:
    query = select(Product).options(selectinload(Product.variants)).order_by(Product.id.desc())
    if keyword:
        query = query.where(Product.name.contains(keyword))
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if status is not None:
        query = query.where(Product.status == status)
    if store_id is not None:
        query = query.where(Product.store_id == store_id)
    return list(db.scalars(query).unique())


def get_product(db: Session, product_id: int) -> Product | None:
    query = (
        select(Product)
        .options(selectinload(Product.variants))
        .where(Product.id == product_id)
    )
    return db.scalars(query).unique().first()


def get_public_product(db: Session, product_id: int) -> Product | None:
    query = (
        select(Product)
        .options(selectinload(Product.variants))
        .where(Product.id == product_id, Product.status == "Published")
    )
    return db.scalars(query).unique().first()


def create_product(db: Session, data: ProductCreate) -> Product:
    payload = data.model_dump(exclude={"variants"})
    if payload["image_url"] is not None:
        payload["image_url"] = str(payload["image_url"])
    product = Product(**payload)
    product.variants = [ProductVariant(**variant.model_dump()) for variant in data.variants]
    db.add(product)
    db.commit()
    db.refresh(product)
    saved_product = get_product(db, product.id)
    assert saved_product is not None
    return saved_product


def update_product(db: Session, product: Product, data: ProductUpdate) -> Product:
    payload = data.model_dump(exclude_unset=True, exclude={"variants"})
    if payload.get("image_url") is not None:
        payload["image_url"] = str(payload["image_url"])
    for field, value in payload.items():
        setattr(product, field, value)
    if data.variants is not None:
        product.variants.clear()
        product.variants.extend(
            ProductVariant(**variant.model_dump()) for variant in data.variants
        )
    db.commit()
    saved_product = get_product(db, product.id)
    assert saved_product is not None
    return saved_product


def delete_product(db: Session, product: Product) -> None:
    db.delete(product)
    db.commit()
