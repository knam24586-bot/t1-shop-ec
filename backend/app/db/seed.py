"""Idempotent local seed data for the T1 Shop MVP."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.passwords import hash_password
from app.db.session import SessionLocal
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.models.variant import ProductVariant


def seed_demo_data(db: Session) -> None:
    """Create demo records only when their stable identifiers are absent."""
    category = db.scalar(
        select(Category).where(Category.slug == "mvp-demo-products")
    )
    if category is None:
        category = Category(
            name="Sản phẩm mẫu",
            slug="mvp-demo-products",
            status="Active",
        )
        db.add(category)
        db.flush()

    product = db.scalar(select(Product).where(Product.slug == "mvp-demo-product"))
    if product is None:
        product = Product(
            category_id=category.id,
            name="Sản phẩm mẫu T1 Shop",
            slug="mvp-demo-product",
            description="Sản phẩm được tạo tự động để kiểm tra luồng mua hàng.",
            price=Decimal("99000.00"),
            rating=Decimal("0.0"),
            stock=20,
            status="Published",
        )
        db.add(product)
        db.flush()

    variant = db.scalar(
        select(ProductVariant).where(ProductVariant.sku == "MVP-DEMO-001")
    )
    if variant is None:
        variant = ProductVariant(
            product_id=product.id,
            sku="MVP-DEMO-001",
            stock=20,
        )
        db.add(variant)

    email = settings.SEED_DEMO_USER_EMAIL.strip().lower()
    if settings.SEED_DEMO_USER_PASSWORD and email:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(
                User(
                    full_name=settings.SEED_DEMO_USER_NAME.strip()
                    or "T1Shop Demo Customer",
                    email=email,
                    password_hash=hash_password(settings.SEED_DEMO_USER_PASSWORD),
                    role="CUSTOMER",
                    status="Active",
                )
            )


def main() -> None:
    with SessionLocal.begin() as db:
        seed_demo_data(db)
    print("Đã seed dữ liệu mẫu (nếu chưa tồn tại).")


if __name__ == "__main__":
    main()
