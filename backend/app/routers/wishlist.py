"""API Router cho danh sách sản phẩm yêu thích (Wishlist).
Cung cấp các API: Xem (List), Thêm (Add), Xóa (Delete/Remove).
Đảm bảo:
- Không tạo item trùng (Unique constraint + validation).
- Người dùng chỉ xem/sửa Wishlist của chính mình (Current User ownership).
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.crud.wishlist import (
    add_product_to_wishlist,
    build_wishlist_item_response,
    build_wishlist_response,
    clear_user_wishlist,
    get_user_wishlist,
    remove_from_wishlist,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.wishlist import (
    WishlistActionMessage,
    WishlistAddRequest,
    WishlistItemResponse,
    WishlistResponse,
)

router = APIRouter(prefix="/wishlist", tags=["Wishlist"])


@router.get(
    "",
    summary="Xem danh sách sản phẩm yêu thích của người dùng hiện tại",
    description="Chỉ trả về các sản phẩm trong wishlist của chính user đang đăng nhập. Mặc định trả về list, hỗ trợ ?format=summary để lấy tổng số lượng.",
)
def get_wishlist(
    format: str = Query("list", description="Định dạng: 'list' (mặc định) hoặc 'summary'"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    items = get_user_wishlist(db, current_user.id)
    if format == "summary":
        return build_wishlist_response(items)
    return [build_wishlist_item_response(it) for it in items]


@router.get(
    "/summary",
    response_model=WishlistResponse,
    summary="Xem danh sách yêu thích kèm tổng số lượng (summary format)",
)
def get_wishlist_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WishlistResponse:
    items = get_user_wishlist(db, current_user.id)
    return build_wishlist_response(items)


@router.post(
    "",
    response_model=WishlistActionMessage,
    status_code=status.HTTP_201_CREATED,
    summary="Thêm sản phẩm vào danh sách yêu thích",
    description="Thêm sản phẩm vào wishlist của user hiện tại. Kiểm tra tồn tại và chặn tạo item trùng lặp.",
)
def add_to_wishlist(
    payload: WishlistAddRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WishlistActionMessage:
    item = add_product_to_wishlist(db, current_user.id, payload.product_id)
    return WishlistActionMessage(
        message="Thêm sản phẩm vào danh sách yêu thích thành công.",
        item=build_wishlist_item_response(item),
    )


@router.post(
    "/items",
    response_model=WishlistActionMessage,
    status_code=status.HTTP_201_CREATED,
    summary="Thêm sản phẩm vào danh sách yêu thích (Alias /items)",
)
def add_to_wishlist_alias(
    payload: WishlistAddRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WishlistActionMessage:
    return add_to_wishlist(payload=payload, current_user=current_user, db=db)


@router.delete(
    "/clear",
    summary="Xóa toàn bộ danh sách yêu thích của người dùng hiện tại",
)
def clear_wishlist(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    count = clear_user_wishlist(db, current_user.id)
    return {
        "message": "Đã xóa toàn bộ danh sách yêu thích.",
        "deleted_count": count,
    }


@router.delete(
    "/products/{product_id}",
    response_model=WishlistActionMessage,
    summary="Xóa sản phẩm khỏi danh sách yêu thích theo mã sản phẩm (product_id)",
)
def remove_by_product_id(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WishlistActionMessage:
    deleted_item = remove_from_wishlist(db, current_user.id, product_id)
    return WishlistActionMessage(
        message=f"Đã xóa sản phẩm ID={product_id} khỏi danh sách yêu thích.",
        item=deleted_item,
    )


@router.delete(
    "/items/{item_id}",
    response_model=WishlistActionMessage,
    summary="Xóa sản phẩm khỏi danh sách yêu thích theo ID của mục wishlist (item_id)",
)
def remove_by_item_id(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WishlistActionMessage:
    deleted_item = remove_from_wishlist(db, current_user.id, item_id)
    return WishlistActionMessage(
        message=f"Đã xóa mục ID={item_id} khỏi danh sách yêu thích.",
        item=deleted_item,
    )


@router.delete(
    "/{product_id}",
    response_model=WishlistActionMessage,
    summary="Xóa sản phẩm khỏi danh sách yêu thích",
    description="Xóa theo product_id hoặc item_id. Chỉ người sở hữu mới được quyền xóa.",
)
def remove_wishlist_item(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WishlistActionMessage:
    deleted_item = remove_from_wishlist(db, current_user.id, product_id)
    return WishlistActionMessage(
        message="Đã xóa sản phẩm khỏi danh sách yêu thích.",
        item=deleted_item,
    )
