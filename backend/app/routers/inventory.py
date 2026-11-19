"""API nhập, điều chỉnh, kiểm tra và tra cứu lịch sử tồn kho."""
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.crud.inventory import change_stock, get_movements, get_variant, list_variants
from app.db.session import get_db
from app.models.variant import ProductVariant
from app.schemas.inventory import (
    InventoryAdjust,
    InventoryMovementResponse,
    InventoryReceive,
    InventoryResponse,
    InventorySet,
)

router = APIRouter(prefix="/api/inventory", tags=["inventory"])
DbSession = Annotated[Session, Depends(get_db)]


def _role_context(
    role: Annotated[str | None, Header(alias="X-Role")] = None,
    store_id: Annotated[int | None, Header(alias="X-Store-Id")] = None,
) -> tuple[str, int | None]:
    normalized = role.upper() if role else ""
    if normalized not in {"ADMIN", "VENDOR"}:
        raise HTTPException(status_code=401, detail="X-Role must be ADMIN or VENDOR")
    if normalized == "VENDOR" and store_id is None:
        raise HTTPException(status_code=403, detail="Vendor requests require X-Store-Id")
    return normalized, store_id


def _authorized_variant(
    variant_id: int, db: Session, context: tuple[str, int | None]
) -> ProductVariant:
    variant = get_variant(db, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    role, store_id = context
    if role == "VENDOR" and variant.product.store_id != store_id:
        raise HTTPException(
            status_code=403,
            detail="Vendor can only manage inventory in their store",
        )
    return variant


def _response(variant: ProductVariant) -> InventoryResponse:
    return InventoryResponse(
        variant_id=variant.id,
        sku=variant.sku,
        product_id=variant.product_id,
        product_name=variant.product.name,
        stock=variant.stock,
    )


@router.get("", response_model=list[InventoryResponse])
def read_inventory(db: DbSession, context=Depends(_role_context)):
    role, store_id = context
    variants = list_variants(db)
    if role == "VENDOR":
        variants = [item for item in variants if item.product.store_id == store_id]
    return [_response(item) for item in variants]


@router.get("/{variant_id}", response_model=InventoryResponse)
def read_variant_inventory(
    variant_id: Annotated[int, Path(gt=0)],
    db: DbSession,
    context=Depends(_role_context),
):
    return _response(_authorized_variant(variant_id, db, context))


@router.post("/{variant_id}/receive", response_model=InventoryResponse)
def receive_inventory(
    data: InventoryReceive,
    variant_id: Annotated[int, Path(gt=0)],
    db: DbSession,
    context=Depends(_role_context),
):
    variant = _authorized_variant(variant_id, db, context)
    try:
        change_stock(db, variant, data.quantity, "RECEIPT", data.reason)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(variant)
    return _response(variant)


@router.post("/{variant_id}/adjust", response_model=InventoryResponse)
def adjust_inventory(
    data: InventoryAdjust,
    variant_id: Annotated[int, Path(gt=0)],
    db: DbSession,
    context=Depends(_role_context),
):
    variant = _authorized_variant(variant_id, db, context)
    try:
        change_stock(db, variant, data.quantity, "ADJUSTMENT", data.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(variant)
    return _response(variant)


@router.put("/{variant_id}", response_model=InventoryResponse)
def set_inventory(
    data: InventorySet,
    variant_id: Annotated[int, Path(gt=0)],
    db: DbSession,
    context=Depends(_role_context),
):
    variant = _authorized_variant(variant_id, db, context)
    delta = data.stock - variant.stock
    if delta == 0:
        return _response(variant)
    try:
        change_stock(db, variant, delta, "SET", data.reason)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(variant)
    return _response(variant)


@router.get(
    "/{variant_id}/movements",
    response_model=list[InventoryMovementResponse],
)
def read_inventory_movements(
    variant_id: Annotated[int, Path(gt=0)],
    db: DbSession,
    context=Depends(_role_context),
):
    _authorized_variant(variant_id, db, context)
    return get_movements(db, variant_id)
