"""Truy vấn và cập nhật tồn kho theo cách nguyên tử."""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.inventory_movement import InventoryMovement
from app.models.variant import ProductVariant


def get_variant(db: Session, variant_id: int) -> ProductVariant | None:
    return db.scalar(
        select(ProductVariant).where(ProductVariant.id == variant_id)
    )


def list_variants(db: Session) -> list[ProductVariant]:
    return list(
        db.scalars(
            select(ProductVariant)
            .join(ProductVariant.product)
            .order_by(ProductVariant.id)
        )
    )


def get_movements(db: Session, variant_id: int) -> list[InventoryMovement]:
    return list(
        db.scalars(
            select(InventoryMovement)
            .where(InventoryMovement.variant_id == variant_id)
            .order_by(InventoryMovement.id.desc())
        )
    )


def change_stock(
    db: Session,
    variant: ProductVariant,
    delta: int,
    movement_type: str,
    reason: str | None,
) -> InventoryMovement:
    before = variant.stock
    after = before + delta
    if after < 0:
        raise ValueError("Stock cannot be negative")

    result = db.execute(
        update(ProductVariant)
        .where(ProductVariant.id == variant.id, ProductVariant.stock == before)
        .values(stock=after)
    )
    if result.rowcount != 1:
        raise RuntimeError("Inventory changed concurrently; please retry")

    movement = InventoryMovement(
        variant_id=variant.id,
        movement_type=movement_type,
        quantity=delta,
        stock_before=before,
        stock_after=after,
        reason=reason,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement
