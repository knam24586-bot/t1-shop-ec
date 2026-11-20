"""Dịch vụ tích hợp Cổng thanh toán Online (Payment Gateways: VNPAY, MOMO, ZALOPAY).
Chịu trách nhiệm:
1. Cấu hình các cổng thanh toán online.
2. Khởi tạo URL thanh toán và token giao dịch (tạo chữ ký HMAC bảo mật).
3. Xác thực tính hợp lệ của callback / IPN từ cổng thanh toán (Xác thực chữ ký / nguồn theo gateway).
4. Xử lý các lỗi khởi tạo (cổng không hỗ trợ, sai cấu hình, số tiền không hợp lệ).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import urllib.parse
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from app.models.payment import PaymentMethod


class GatewayConfig:
    """Cấu hình sandbox / production cho các cổng thanh toán."""
    # VNPAY
    VNPAY_TMN_CODE = os.getenv("VNPAY_TMN_CODE", "T1SHOP01")
    VNPAY_HASH_SECRET = os.getenv("VNPAY_HASH_SECRET", "SECRETKEY_VNPAY_T1SHOP_2026")
    VNPAY_BASE_URL = os.getenv("VNPAY_BASE_URL", "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html")

    # MOMO
    MOMO_PARTNER_CODE = os.getenv("MOMO_PARTNER_CODE", "MOMO_T1SHOP")
    MOMO_SECRET_KEY = os.getenv("MOMO_SECRET_KEY", "SECRETKEY_MOMO_T1SHOP_2026")
    MOMO_BASE_URL = os.getenv("MOMO_BASE_URL", "https://test-payment.momo.vn/v2/gateway/api/create")

    # ZALOPAY
    ZALOPAY_APP_ID = os.getenv("ZALOPAY_APP_ID", "2554")
    ZALOPAY_KEY1 = os.getenv("ZALOPAY_KEY1", "SECRETKEY_ZALOPAY_T1SHOP_2026")
    ZALOPAY_BASE_URL = os.getenv("ZALOPAY_BASE_URL", "https://sb-openapi.zalopay.vn/v2/create")

    # Generic secret
    GENERIC_SECRET = os.getenv("GENERIC_GATEWAY_SECRET", "GENERIC_GATEWAY_SECRET_2026")

    # Thời hạn hiệu lực của URL thanh toán (15 phút)
    PAYMENT_TIMEOUT_MINUTES = 15


# Danh sách các cổng thanh toán online được hỗ trợ
SUPPORTED_ONLINE_GATEWAYS = {
    PaymentMethod.VNPAY.value,
    PaymentMethod.MOMO.value,
    PaymentMethod.ZALOPAY.value,
    PaymentMethod.BANK_TRANSFER.value,
    PaymentMethod.CREDIT_CARD.value,
}


def is_supported_online_gateway(method: str) -> bool:
    """Kiểm tra xem phương thức có phải là cổng thanh toán online hợp lệ không."""
    return method.strip().upper() in SUPPORTED_ONLINE_GATEWAYS


def generate_hmac_sha512(secret_key: str, data: str) -> str:
    """Tạo chữ ký HMAC-SHA512."""
    return hmac.new(
        secret_key.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()


def generate_hmac_sha256(secret_key: str, data: str) -> str:
    """Tạo chữ ký HMAC-SHA256."""
    return hmac.new(
        secret_key.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------
# 1. KHỞI TẠO URL VÀ TOKEN CHO CÁC CỔNG
# ---------------------------------------------------------------------
def create_vnpay_payment_url(
    order_id: int,
    order_code: str,
    amount: Decimal,
    transaction_ref: str,
    ip_address: str = "127.0.0.1",
    return_url: str = "http://localhost:8000/api/payments/callback",
) -> tuple[str, str]:
    """Tạo URL thanh toán và mã token cho cổng VNPAY."""
    create_date = datetime.now().strftime("%Y%m%d%H%M%S")
    amount_in_cents = int(amount * 100)  # VNPAY yêu cầu nhân 100

    params: dict[str, Any] = {
        "vnp_Version": "2.1.0",
        "vnp_Command": "pay",
        "vnp_TmnCode": GatewayConfig.VNPAY_TMN_CODE,
        "vnp_Amount": str(amount_in_cents),
        "vnp_CreateDate": create_date,
        "vnp_CurrCode": "VND",
        "vnp_IpAddr": ip_address,
        "vnp_Locale": "vn",
        "vnp_OrderInfo": f"Thanh toan don hang {order_code}",
        "vnp_OrderType": "billpayment",
        "vnp_ReturnUrl": return_url,
        "vnp_TxnRef": transaction_ref,
    }

    sorted_params = sorted(params.items())
    query_string = urllib.parse.urlencode(sorted_params)
    secure_hash = generate_hmac_sha512(GatewayConfig.VNPAY_HASH_SECRET, query_string)

    payment_url = f"{GatewayConfig.VNPAY_BASE_URL}?{query_string}&vnp_SecureHash={secure_hash}"
    payment_token = f"VNPAY-TOKEN-{secure_hash[:24].upper()}"
    return payment_url, payment_token


def create_momo_payment_url(
    order_id: int,
    order_code: str,
    amount: Decimal,
    transaction_ref: str,
    return_url: str = "http://localhost:8000/api/payments/callback",
) -> tuple[str, str]:
    """Tạo URL thanh toán và mã token cho cổng MoMo."""
    raw_signature_str = (
        f"partnerCode={GatewayConfig.MOMO_PARTNER_CODE}&orderId={transaction_ref}"
        f"&amount={int(amount)}&orderInfo=Thanh toan don hang {order_code}"
    )
    signature = generate_hmac_sha256(GatewayConfig.MOMO_SECRET_KEY, raw_signature_str)

    params = {
        "partnerCode": GatewayConfig.MOMO_PARTNER_CODE,
        "orderId": transaction_ref,
        "amount": str(int(amount)),
        "orderInfo": f"Thanh toan don hang {order_code}",
        "redirectUrl": return_url,
        "signature": signature,
    }
    query_string = urllib.parse.urlencode(params)
    payment_url = f"{GatewayConfig.MOMO_BASE_URL}?{query_string}"
    payment_token = f"MOMO-TOKEN-{signature[:24].upper()}"
    return payment_url, payment_token


def create_zalopay_payment_url(
    order_id: int,
    order_code: str,
    amount: Decimal,
    transaction_ref: str,
    return_url: str = "http://localhost:8000/api/payments/callback",
) -> tuple[str, str]:
    """Tạo URL thanh toán và mã token cho cổng ZaloPay."""
    app_time = str(int(datetime.now().timestamp() * 1000))
    raw_signature_str = (
        f"{GatewayConfig.ZALOPAY_APP_ID}|{transaction_ref}|user|{int(amount)}|{app_time}|{return_url}"
    )
    signature = generate_hmac_sha256(GatewayConfig.ZALOPAY_KEY1, raw_signature_str)

    params = {
        "app_id": GatewayConfig.ZALOPAY_APP_ID,
        "app_trans_id": transaction_ref,
        "app_user": "user",
        "app_time": app_time,
        "amount": str(int(amount)),
        "redirect_url": return_url,
        "mac": signature,
    }
    query_string = urllib.parse.urlencode(params)
    payment_url = f"{GatewayConfig.ZALOPAY_BASE_URL}?{query_string}"
    payment_token = f"ZALO-TOKEN-{signature[:24].upper()}"
    return payment_url, payment_token


def build_gateway_payment_session(
    method: str,
    order_id: int,
    order_code: str,
    amount: Decimal,
    transaction_ref: str,
    ip_address: str = "127.0.0.1",
    return_url: str | None = None,
) -> tuple[str, str, datetime]:
    """Khởi tạo URL thanh toán và token tùy theo gateway được chỉ định."""
    method_upper = method.strip().upper()
    if not is_supported_online_gateway(method_upper):
        raise ValueError(
            f"Cổng thanh toán '{method}' không được hỗ trợ. "
            f"Các cổng hợp lệ: {', '.join(sorted(SUPPORTED_ONLINE_GATEWAYS))}"
        )

    if amount <= Decimal("0.00"):
        raise ValueError(f"Số tiền thanh toán phải lớn hơn 0 (nhận được {amount}).")

    cb_url = return_url or "http://localhost:8000/api/payments/callback"

    if method_upper == PaymentMethod.VNPAY.value:
        pay_url, token = create_vnpay_payment_url(
            order_id=order_id,
            order_code=order_code,
            amount=amount,
            transaction_ref=transaction_ref,
            ip_address=ip_address,
            return_url=cb_url,
        )
    elif method_upper == PaymentMethod.MOMO.value:
        pay_url, token = create_momo_payment_url(
            order_id=order_id,
            order_code=order_code,
            amount=amount,
            transaction_ref=transaction_ref,
            return_url=cb_url,
        )
    elif method_upper == PaymentMethod.ZALOPAY.value:
        pay_url, token = create_zalopay_payment_url(
            order_id=order_id,
            order_code=order_code,
            amount=amount,
            transaction_ref=transaction_ref,
            return_url=cb_url,
        )
    else:
        raw = f"order={transaction_ref}&amount={int(amount)}&date={datetime.now().isoformat()}"
        sig = generate_hmac_sha256(GatewayConfig.GENERIC_SECRET, raw)
        pay_url = f"https://gateway.t1shop.vn/checkout?{urllib.parse.urlencode({'ref': transaction_ref, 'sig': sig})}"
        token = f"GATEWAY-TOKEN-{sig[:20].upper()}"

    expires_at = datetime.now() + timedelta(minutes=GatewayConfig.PAYMENT_TIMEOUT_MINUTES)
    return pay_url, token, expires_at


# ---------------------------------------------------------------------
# 2. XÁC THỰC CHỮ KÝ VÀ NGUỒN CỦA WEBHOOK / CALLBACK THEO GATEWAY
# ---------------------------------------------------------------------
def build_vnpay_signature(params: dict[str, Any]) -> str:
    """Tạo chữ ký VNPAY từ tập tham số (loại trừ vnp_SecureHash và vnp_SecureHashType)."""
    has_vnp_prefix = any(k.startswith("vnp_") for k in params.keys())
    filtered = {
        k: str(v)
        for k, v in params.items()
        if (not has_vnp_prefix or k.startswith("vnp_"))
        and k not in ["vnp_SecureHash", "vnp_SecureHashType", "secure_hash"]
        and v is not None and v != ""
    }
    sorted_items = sorted(filtered.items())
    query_str = urllib.parse.urlencode(sorted_items)
    return generate_hmac_sha512(GatewayConfig.VNPAY_HASH_SECRET, query_str)


def verify_vnpay_signature(params: dict[str, Any], secure_hash: str | None) -> bool:
    """Xác thực chữ ký callback từ cổng VNPAY."""
    if not secure_hash:
        return False
    expected_hash = build_vnpay_signature(params)
    return hmac.compare_digest(secure_hash.lower(), expected_hash.lower())


def build_momo_signature(params: dict[str, Any]) -> str:
    """Tạo chữ ký MoMo từ tập tham số."""
    partner_code = params.get("partnerCode") or GatewayConfig.MOMO_PARTNER_CODE
    order_id = params.get("orderId") or params.get("transaction_reference") or ""
    amount = params.get("amount") or ""
    order_info = params.get("orderInfo") or ""
    response_code = params.get("resultCode") or params.get("response_code") or "00"

    raw = f"partnerCode={partner_code}&orderId={order_id}&amount={amount}&orderInfo={order_info}&resultCode={response_code}"
    return generate_hmac_sha256(GatewayConfig.MOMO_SECRET_KEY, raw)


def verify_momo_signature(params: dict[str, Any], signature: str | None) -> bool:
    """Xác thực chữ ký callback từ cổng MoMo."""
    if not signature:
        return False
    expected_sig = build_momo_signature(params)
    return hmac.compare_digest(signature.lower(), expected_sig.lower())


def build_zalopay_signature(params: dict[str, Any]) -> str:
    """Tạo chữ ký ZaloPay từ tập tham số."""
    app_id = params.get("app_id") or GatewayConfig.ZALOPAY_APP_ID
    app_trans_id = params.get("app_trans_id") or params.get("transaction_reference") or ""
    amount = params.get("amount") or ""
    raw = f"{app_id}|{app_trans_id}|{amount}"
    return generate_hmac_sha256(GatewayConfig.ZALOPAY_KEY1, raw)


def verify_zalopay_signature(params: dict[str, Any], mac: str | None) -> bool:
    """Xác thực chữ ký callback từ cổng ZaloPay."""
    if not mac:
        return False
    expected_mac = build_zalopay_signature(params)
    return hmac.compare_digest(mac.lower(), expected_mac.lower())


def verify_gateway_signature(
    gateway: str,
    params: dict[str, Any],
    signature: str | None,
) -> bool:
    """Hàm điều phối xác thực chữ ký theo chuẩn từng cổng thanh toán."""
    gateway_upper = gateway.strip().upper()
    if not signature or not signature.strip():
        return False

    if gateway_upper == PaymentMethod.VNPAY.value:
        return verify_vnpay_signature(params, signature)
    elif gateway_upper == PaymentMethod.MOMO.value:
        return verify_momo_signature(params, signature)
    elif gateway_upper == PaymentMethod.ZALOPAY.value:
        return verify_zalopay_signature(params, signature)
    else:
        # Generic online gateway
        raw = f"{params.get('transaction_reference', '')}|{params.get('response_code', '00')}"
        expected = generate_hmac_sha256(GatewayConfig.GENERIC_SECRET, raw)
        return hmac.compare_digest(signature.lower(), expected.lower())
