"""CRUD operations cho Wishlist (Danh sách sản phẩm yêu thích).
Thực hiện các thao tác thêm, xóa, xem danh sách sản phẩm yêu thích,
đảm bảo người dùng chỉ xem/sửa dữ liệu của mình và không tạo item trùng lặp.
"""
from __future__ import annotations

from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.wishlist import Wishlist
from app.schemas.wishlist import (
    WishlistItemResponse,
    WishlistProductResponse,
    WishlistResponse,
)


def build_wishlist_item_response(item: Wishlist) -> WishlistItemResponse:
    """Chuyển đổi Wishlist model thành WishlistItemResponse kèm thông tin chi tiết sản phẩm."""
    product = item.product
    product_resp = None
    product_name = None
    product_slug = None
    product_price = None
    product_stock = None
    product_image_url = None
    product_status = None

    if product is not None:
        price_dec = Decimal(str(product.price)) if product.price is not None else Decimal("0.00")
        product_resp = WishlistProductResponse(
            id=product.id,
            name=product.name,
            slug=product.slug,
            price=price_dec,
            stock=product.stock,
            image_url=product.image_url,
            status=product.status,
        )
        product_name = product.name
        product_slug = product.slug
        product_price = price_dec
        product_stock = product.stock
        product_image_url = product.image_url
        product_status = product.status

    return WishlistItemResponse(
        id=item.id,
        user_id=item.user_id,
        product_id=item.product_id,
        created_at=item.created_at,
        product_name=product_name,
        product_slug=product_slug,
        product_price=product_price,
        product_stock=product_stock,
        product_image_url=product_image_url,
        product_status=product_status,
        product=product_resp,
    )


def build_wishlist_response(items: list[Wishlist]) -> WishlistResponse:
    """Chuyển đổi danh sách Wishlist model thành WishlistResponse."""
    items_response = [build_wishlist_item_response(it) for it in items]
    return WishlistResponse(
        total_items=len(items_response),
        items=items_response,
    )


def get_user_wishlist(db: Session, user_id: int) -> list[Wishlist]:
    """Lấy toàn bộ danh sách yêu thích của người dùng hiện tại (sắp xếp mới nhất trước).
    Chỉ trả về các sản phẩm thuộc về user_id được truyền vào.
    """
    stmt = (
        select(Wishlist)
        .where(Wishlist.user_id == user_id)
        .order_by(Wishlist.created_at.desc(), Wishlist.id.desc())
    )
    return list(db.scalars(stmt))


def get_wishlist_item_by_product(
    db: Session, user_id: int, product_id: int
) -> Wishlist | None:
    """Tìm một mục trong wishlist của user theo product_id."""
    stmt = select(Wishlist).where(
        Wishlist.user_id == user_id,
        Wishlist.product_id == product_id,
    )
    return db.scalar(stmt)


def get_wishlist_item_by_id(
    db: Session, user_id: int, item_id: int
) -> Wishlist | None:
    """Tìm một mục trong wishlist của user theo item_id (primary key)."""
    stmt = select(Wishlist).where(
        Wishlist.id == item_id,
        Wishlist.user_id == user_id,
    )
    return db.scalar(stmt)


def add_product_to_wishlist(
    db: Session, user_id: int, product_id: int
) -> Wishlist:
    """Thêm sản phẩm vào wishlist của user.
    - Kiểm tra sản phẩm có tồn tại không -> 404 nếu không tồn tại.
    - Kiểm tra sản phẩm đã có trong wishlist chưa -> 400 nếu đã có (chặn trùng lặp).
    - Lưu vào DB và trả về model.
    """
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sản phẩm với ID={product_id} không tồn tại.",
        )

    # Tiêu chí: không tạo item trùng
    existing = get_wishlist_item_by_product(db, user_id, product_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sản phẩm '{product.name}' (ID={product_id}) đã có trong danh sách yêu thích.",
        )

    wishlist_item = Wishlist(user_id=user_id, product_id=product_id)
    db.add(wishlist_item)
    try:
        db.commit()
        db.refresh(wishlist_item)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sản phẩm với ID={product_id} đã có trong danh sách yêu thích.",
        )

    return wishlist_item


def remove_from_wishlist(
    db: Session, user_id: int, product_or_item_id: int
) -> WishlistItemResponse:
    """Xóa sản phẩm khỏi wishlist của user.
    Hỗ trợ xóa theo product_id hoặc theo id của mục wishlist.
    Đảm bảo CHỈ xóa item của user hiện tại, không thể xóa của user khác.
    """
    # 1. Tìm theo product_id của user_id
    item = get_wishlist_item_by_product(db, user_id, product_or_item_id)
    # 2. Nếu không tìm thấy, thử tìm theo id của user_id
    if item is None:
        item = get_wishlist_item_by_id(db, user_id, product_or_item_id)

    if item is None:
        # Kiểm tra xem item/product này có nằm trong wishlist của người khác không
        other_item = db.scalar(
            select(Wishlist).where(
                (Wishlist.product_id == product_or_item_id) | (Wishlist.id == product_or_item_id)
            )
        )
        if other_item is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền xóa sản phẩm trong danh sách yêu thích của người dùng khác.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sản phẩm với ID={product_or_item_id} trong danh sách yêu thích của bạn.",
        )

    # Chụp lại thông tin trước khi xóa khỏi session
    item_response = build_wishlist_item_response(item)
    db.delete(item)
    db.commit()
    return item_response


def clear_user_wishlist(db: Session, user_id: int) -> int:
    """Xóa toàn bộ sản phẩm yêu thích của user hiện tại."""
    items = get_user_wishlist(db, user_id)
    count = len(items)
    for item in items:
        db.delete(item)
    db.commit()
    return count
