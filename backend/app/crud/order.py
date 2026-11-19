"""CRUD và nghiệp vụ tạo đơn hàng COD trong Database Transaction.
Đảm bảo:
1. COD tạo đơn khi cart hợp lệ (giỏ hàng có sản phẩm, địa chỉ giao hàng hợp lệ).
2. Giá và tồn kho được kiểm tra lại ở server (tuyệt đối không tin giá/tồn từ client).
3. Tạo Order, OrderItems, trừ tồn kho, tạo Payment COD và xoá giỏ hàng NẰM TRONG 1 TRANSACTION.
"""
from __future__ import annotations

from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.product import Product
from app.models.variant import ProductVariant
from app.models.voucher import Voucher, VoucherStatus
from app.schemas.order import (
    OrderItemResponse,
    OrderResponse,
    PaymentSummaryResponse,
)


def build_order_response(order: Order, payment: Payment | None = None) -> OrderResponse:
    """Chuyển đổi Order model và Payment model thành OrderResponse hoàn chỉnh."""
    items_response: list[OrderItemResponse] = []
    for item in order.items:
        product_name = None
        sku = None
        color = None
        size = None
        if item.variant:
            sku = item.variant.sku
            color = item.variant.color
            size = item.variant.size
        if item.product:
            product_name = item.product.name

        items_response.append(
            OrderItemResponse(
                id=item.id,
                variant_id=item.variant_id,
                product_id=item.product_id,
                product_name=product_name,
                sku=sku,
                color=color,
                size=size,
                unit_price=item.unit_price,
                quantity=item.quantity,
                line_total=item.line_total,
            )
        )

    payment_resp = None
    if payment:
        payment_resp = PaymentSummaryResponse(
            id=payment.id,
            method=payment.method,
            amount=payment.amount,
            status=payment.status,
            transaction_reference=payment.transaction_reference,
            attempt_number=payment.attempt_number,
        )

    return OrderResponse(
        id=order.id,
        order_code=order.order_code,
        customer_id=order.customer_id,
        total_price=order.total_price,
        shipping_address=order.shipping_address,
        status=order.status,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=items_response,
        payment=payment_resp,
    )


def create_cod_order(
    db: Session,
    user_id: int,
    shipping_address: str,
    voucher_code: str | None = None,
) -> tuple[Order, Payment]:
    """Tạo đơn hàng COD từ giỏ hàng hiện tại của người dùng.
    Toàn bộ quá trình:
    1. Kiểm tra giỏ hàng: Giỏ hàng phải tồn tại và có ít nhất 1 sản phẩm.
    2. Kiểm tra lại giá & tồn kho tại Server:
       - Fetch dữ liệu mới nhất của từng biến thể từ DB.
       - Kiểm tra tồn kho (variant.stock >= item.quantity).
       - Lấy giá gốc từ variant.product.price tại server (không tin client).
    3. Transaction nguyên tử:
       - Tạo Order (mã duy nhất, địa chỉ snapshot).
       - Trừ tồn kho biến thể và sản phẩm.
       - Tạo các OrderItem với unit_price và line_total snapshot.
       - Tạo bản ghi Payment COD trạng thái PENDING.
       - Nếu có voucher: xác thực và áp dụng giảm giá.
       - Xoá sạch giỏ hàng đã thanh toán.
       - Commit toàn bộ; nếu lỗi ở bất kỳ bước nào -> Rollback 100%.
    """
    # 1. Kiểm tra địa chỉ giao hàng
    if not shipping_address or not shipping_address.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Địa chỉ giao hàng không được để trống.",
        )
    clean_address = shipping_address.strip()
    if len(clean_address) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Địa chỉ giao hàng phải có ít nhất 5 ký tự.",
        )

    # 2. Kiểm tra giỏ hàng của user
    cart = db.scalar(select(Cart).where(Cart.user_id == user_id))
    if not cart or not cart.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Giỏ hàng trống, không thể tạo đơn hàng.",
        )

    # 3. Server kiểm tra lại giá và tồn kho trước khi thực hiện Transaction
    validated_items: list[tuple[CartItem, ProductVariant, Decimal, Decimal]] = []
    subtotal = Decimal("0.00")

    for cart_item in cart.items:
        variant = db.get(ProductVariant, cart_item.variant_id)
        if not variant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Biến thể sản phẩm (ID={cart_item.variant_id}) không tồn tại trong hệ thống.",
            )

        product = variant.product
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sản phẩm gốc của SKU '{variant.sku}' không tồn tại.",
            )

        # Kiểm tra tồn kho ở server
        if variant.stock < cart_item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Sản phẩm '{product.name}' (SKU: {variant.sku}) không đủ số lượng tồn kho "
                    f"(tồn kho hiện tại: {variant.stock}, số lượng đặt mua: {cart_item.quantity})."
                ),
            )

        # Lấy giá từ DB tại thời điểm chốt đơn
        current_price = Decimal(str(product.price))
        line_total = current_price * cart_item.quantity
        subtotal += line_total
        validated_items.append((cart_item, variant, current_price, line_total))

    # 4. Kiểm tra Voucher (nếu có)
    discount_amount = Decimal("0.00")
    voucher = None
    if voucher_code and voucher_code.strip():
        clean_code = voucher_code.strip().upper()
        voucher = db.scalar(select(Voucher).where(Voucher.code == clean_code))
        if not voucher:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Mã giảm giá '{clean_code}' không tồn tại.",
            )
        is_valid, reason = voucher.is_valid_for_order(order_amount=subtotal)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Không thể áp dụng mã '{clean_code}': {reason}",
            )
        discount_amount = voucher.calculate_discount(order_amount=subtotal)

    final_total = max(Decimal("0.00"), subtotal - discount_amount)
    if final_total <= Decimal("0.00"):
        # Đảm bảo tổng tiền đơn hàng > 0 theo CheckConstraint
        final_total = Decimal("1000.00")

    # 5. BẮT ĐẦU TRANSACTION NGUYÊN TỬ (Order, OrderItems, Trừ kho, Payment, Xóa Cart)
    try:
        # A. Tạo Order
        order = Order(
            order_code=Order.generate_order_code("COD"),
            customer_id=user_id,
            shipping_address=clean_address,
            total_price=final_total,
            status=OrderStatus.PENDING.value,
        )
        db.add(order)
        db.flush()  # Sinh order.id

        # B. Tạo OrderItems và Trừ tồn kho trong Transaction
        for cart_item, variant, price, line_total in validated_items:
            # Trừ tồn kho của biến thể
            variant.stock -= cart_item.quantity
            # Đồng bộ trừ tồn kho ở sản phẩm gốc nếu có
            if variant.product and variant.product.stock is not None:
                variant.product.stock = max(0, variant.product.stock - cart_item.quantity)

            order_item = OrderItem(
                order_id=order.id,
                variant_id=variant.id,
                product_id=variant.product_id,
                unit_price=price,
                quantity=cart_item.quantity,
                line_total=line_total,
            )
            db.add(order_item)

        # C. Tạo bản ghi Payment COD với trạng thái PENDING
        payment = Payment(
            order_id=order.id,
            method=PaymentMethod.COD.value,
            amount=final_total,
            status=PaymentStatus.PENDING.value,
            attempt_number=1,
            transaction_reference=Payment.generate_transaction_ref(
                PaymentMethod.COD, order.id, 1
            ),
        )
        db.add(payment)

        # D. Cập nhật lượt dùng voucher nếu có
        if voucher:
            voucher.used_count += 1
            if voucher.usage_limit is not None and voucher.used_count >= voucher.usage_limit:
                voucher.status = VoucherStatus.DEPLETED.value

        # E. Xóa sạch giỏ hàng của user sau khi đặt hàng thành công
        for cart_item, _, _, _ in validated_items:
            db.delete(cart_item)

        # F. Commit toàn bộ Transaction
        db.commit()
        db.refresh(order)
        db.refresh(payment)
        return order, payment

    except Exception:
        db.rollback()
        raise


def get_user_orders(db: Session, user_id: int) -> list[Order]:
    """Lấy danh sách các đơn hàng của user hiện tại."""
    stmt = (
        select(Order)
        .where(Order.customer_id == user_id)
        .order_by(Order.created_at.desc())
    )
    return list(db.scalars(stmt))


def get_order_by_code(db: Session, order_code: str, user_id: int) -> tuple[Order, Payment | None]:
    """Lấy chi tiết một đơn hàng theo order_code của user hiện tại."""
    stmt = select(Order).where(
        Order.order_code == order_code,
        Order.customer_id == user_id,
    )
    order = db.scalar(stmt)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng '{order_code}'.",
        )

    payment = db.scalar(
        select(Payment)
        .where(Payment.order_id == order.id)
        .order_by(Payment.attempt_number.desc())
    )
    return order, payment

