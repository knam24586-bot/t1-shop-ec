"""API Router cho các thao tác giỏ hàng (Xem, Thêm, Sửa, Xóa).
Đảm bảo chỉ thao tác trên cart của user hiện tại, kiểm tra variant và tồn kho.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.crud.cart import (
    add_item_to_cart,
    build_cart_response,
    clear_cart,
    delete_cart_item,
    get_or_create_user_cart,
    update_cart_item_quantity,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.cart import (
    CartActionMessage,
    CartItemAdd,
    CartItemUpdate,
    CartResponse,
)

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.get(
    "",
    response_model=CartResponse,
    summary="Xem giỏ hàng của người dùng hiện tại",
    description="Lấy toàn bộ danh sách sản phẩm trong giỏ hàng, thông tin biến thể, đơn giá, tồn kho và tổng tiền.",
)
def get_cart(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartResponse:
    cart = get_or_create_user_cart(db, current_user.id)
    return build_cart_response(cart)


@router.post(
    "/items",
    response_model=CartActionMessage,
    status_code=status.HTTP_201_CREATED,
    summary="Thêm sản phẩm vào giỏ hàng",
    description="Kiểm tra variant, kiểm tra tồn kho và áp dụng quy tắc gộp giỏ nếu biến thể đã có sẵn.",
)
def add_to_cart(
    payload: CartItemAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartActionMessage:
    updated_cart = add_item_to_cart(
        db=db,
        user_id=current_user.id,
        variant_id=payload.variant_id,
        quantity=payload.quantity,
    )
    return CartActionMessage(
        message="Thêm sản phẩm vào giỏ hàng thành công.",
        cart=updated_cart,
    )


@router.put(
    "/items/{item_id}",
    response_model=CartActionMessage,
    summary="Cập nhật số lượng sản phẩm trong giỏ hàng",
    description="Chỉ thao tác trên giỏ của user hiện tại, kiểm tra tồn kho của biến thể.",
)
def update_item_quantity(
    item_id: int,
    payload: CartItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartActionMessage:
    updated_cart = update_cart_item_quantity(
        db=db,
        user_id=current_user.id,
        item_id=item_id,
        new_quantity=payload.quantity,
    )
    return CartActionMessage(
        message="Cập nhật số lượng sản phẩm thành công.",
        cart=updated_cart,
    )


@router.delete(
    "/items/{item_id}",
    response_model=CartActionMessage,
    summary="Xóa một sản phẩm khỏi giỏ hàng",
    description="Chỉ thao tác trên giỏ hàng của user hiện tại, xóa CartItem tương ứng.",
)
def remove_from_cart(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartActionMessage:
    updated_cart = delete_cart_item(
        db=db,
        user_id=current_user.id,
        item_id=item_id,
    )
    return CartActionMessage(
        message="Xóa sản phẩm khỏi giỏ hàng thành công.",
        cart=updated_cart,
    )


@router.delete(
    "",
    response_model=CartActionMessage,
    summary="Xóa toàn bộ sản phẩm trong giỏ hàng",
    description="Dọn sạch giỏ hàng của người dùng hiện tại.",
)
def clear_user_cart(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartActionMessage:
    updated_cart = clear_cart(db=db, user_id=current_user.id)
    return CartActionMessage(
        message="Đã làm trống giỏ hàng thành công.",
        cart=updated_cart,
    )

