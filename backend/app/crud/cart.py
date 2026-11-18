"""CRUD operations cho Cart và CartItem.
Thực hiện các thao tác đọc/ghi Database, kiểm tra quyền của user hiện tại, biến thể và tồn kho.
"""
from __future__ import annotations

from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.product import Product
from app.models.variant import ProductVariant
from app.schemas.cart import CartItemResponse, CartResponse


def get_or_create_user_cart(db: Session, user_id: int) -> Cart:
    """Lấy giỏ hàng của user hiện tại. Nếu chưa có thì tự động tạo mới."""
    cart = db.scalar(select(Cart).where(Cart.user_id == user_id))
    if not cart:
        cart = Cart(user_id=user_id, status="Active")
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def build_cart_response(cart: Cart) -> CartResponse:
    """Chuyển đổi Cart model thành CartResponse kèm thông tin chi tiết từng variant và tổng tiền."""
    total_items = 0
    total_amount = Decimal("0.00")
    items_response: list[CartItemResponse] = []

    for item in cart.items:
        variant: ProductVariant | None = item.variant
        price = Decimal("0.00")
        stock = 0
        product_name = None
        sku = None
        color = None
        size = None
        product_id = None

        if variant is not None:
            sku = variant.sku
            color = variant.color
            size = variant.size
            stock = variant.stock
            product_id = variant.product_id
            if variant.product is not None:
                price = Decimal(str(variant.product.price))
                product_name = variant.product.name

        line_total = price * Decimal(item.quantity)
        total_items += item.quantity
        total_amount += line_total

        items_response.append(
            CartItemResponse(
                id=item.id,
                cart_id=item.cart_id,
                variant_id=item.variant_id,
                product_id=product_id,
                product_name=product_name,
                sku=sku,
                color=color,
                size=size,
                price=price,
                stock=stock,
                quantity=item.quantity,
                line_total=line_total,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )

    return CartResponse(
        cart_id=cart.id,
        user_id=cart.user_id,
        status=cart.status,
        total_items=total_items,
        total_amount=total_amount,
        items=items_response,
    )


def add_item_to_cart(
    db: Session,
    user_id: int,
    variant_id: int | None,
    product_id: int | None,
    quantity: int,
) -> CartResponse:
    """Thêm sản phẩm vào giỏ hàng:
    - Kiểm tra số lượng > 0.
    - Kiểm tra biến thể tồn tại.
    - Kiểm tra tồn kho (tồn kho hiện tại >= số lượng sau khi thêm).
    - Quy tắc gộp giỏ: Nếu biến thể đã có trong giỏ của user thì cộng dồn số lượng.
    """
    if quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Số lượng thêm vào giỏ hàng phải lớn hơn 0 (nhận được {quantity}).",
        )

    # 1. Resolve a variant from the requested product when the client has no variant picker.
    if variant_id is None and product_id is not None:
        variant_id = db.scalar(
            select(ProductVariant.id)
            .join(Product)
            .where(
                ProductVariant.product_id == product_id,
                ProductVariant.stock > 0,
                Product.status == "Published",
            )
            .order_by(ProductVariant.id)
            .limit(1)
        )
        if variant_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sản phẩm hiện không có biến thể còn hàng.",
            )

    # 2. Check the variant and its published parent product.
    variant = db.scalar(
        select(ProductVariant)
        .join(Product)
        .where(
            ProductVariant.id == variant_id,
            Product.status == "Published",
        )
    )
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sản phẩm hoặc biến thể không tồn tại hoặc không được bán.",
        )
    if product_id is not None and variant.product_id != product_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Biến thể không thuộc sản phẩm đã chọn.",
        )

    # 3. Lấy giỏ hàng của user hiện tại
    cart = get_or_create_user_cart(db, user_id)

    # 4. Kiểm tra mục đã có trong giỏ chưa và kiểm tra tồn kho
    existing_item = next((i for i in cart.items if i.variant_id == variant_id), None)
    current_qty = existing_item.quantity if existing_item else 0
    requested_total_qty = current_qty + quantity

    if requested_total_qty > variant.stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Sản phẩm '{variant.sku}' không đủ tồn kho. "
                f"Yêu cầu: {requested_total_qty} (đang có {current_qty} trong giỏ + thêm {quantity}), "
                f"tồn kho hiện có: {variant.stock}."
            ),
        )

    # 5. Áp dụng quy tắc gộp giỏ
    if existing_item:
        existing_item.quantity = requested_total_qty
    else:
        new_item = CartItem(cart_id=cart.id, variant_id=variant_id, quantity=quantity)
        db.add(new_item)

    db.commit()
    db.refresh(cart)
    return build_cart_response(cart)


def update_cart_item_quantity(
    db: Session,
    user_id: int,
    item_id: int,
    new_quantity: int,
) -> CartResponse:
    """Cập nhật số lượng sản phẩm trong giỏ:
    - Kiểm tra số lượng > 0.
    - Kiểm tra mục tồn tại.
    - CHỈ THAO TÁC TRÊN CART CỦA USER HIỆN TẠI (tránh sửa cart của người khác).
    - Kiểm tra tồn kho của variant.
    """
    if new_quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Số lượng cập nhật phải lớn hơn 0 (nhận được {new_quantity}).",
        )

    # 1. Tìm CartItem
    item = db.get(CartItem, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy mục giỏ hàng với ID={item_id}.",
        )

    # 2. Kiểm tra quyền: Chỉ thao tác trên giỏ hàng của user hiện tại
    if item.cart.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thao tác trên giỏ hàng của người dùng khác.",
        )

    # 3. Kiểm tra tồn kho của variant
    variant = item.variant
    if variant and new_quantity > variant.stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Số lượng cập nhật ({new_quantity}) vượt quá số lượng tồn kho ({variant.stock}) "
                f"của biến thể '{variant.sku}'."
            ),
        )

    # 4. Cập nhật số lượng
    item.quantity = new_quantity
    db.commit()

    cart = db.get(Cart, item.cart_id)
    return build_cart_response(cart)


def delete_cart_item(
    db: Session,
    user_id: int,
    item_id: int,
) -> CartResponse:
    """Xóa một sản phẩm khỏi giỏ:
    - Kiểm tra mục tồn tại.
    - CHỈ THAO TÁC TRÊN CART CỦA USER HIỆN TẠI.
    - Xóa CartItem khỏi DB.
    """
    item = db.get(CartItem, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy mục giỏ hàng với ID={item_id}.",
        )

    # Kiểm tra quyền sở hữu
    if item.cart.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thao tác trên giỏ hàng của người dùng khác.",
        )

    cart_id = item.cart_id
    db.delete(item)
    db.commit()

    cart = db.get(Cart, cart_id)
    return build_cart_response(cart)


def clear_cart(
    db: Session,
    user_id: int,
) -> CartResponse:
    """Xóa sạch toàn bộ sản phẩm trong giỏ hàng của user hiện tại."""
    cart = get_or_create_user_cart(db, user_id)
    for item in list(cart.items):
        db.delete(item)
    db.commit()
    db.refresh(cart)
    return build_cart_response(cart)

