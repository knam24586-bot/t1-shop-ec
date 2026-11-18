# T1 Shop EC

T1 Shop EC là cửa hàng thương mại điện tử với backend FastAPI/MySQL và frontend HTML/CSS/JavaScript thuần.

## Khởi động nhanh

1. Làm theo [hướng dẫn backend](backend/README.md) để cấu hình MySQL, khởi tạo schema và chạy API.
2. Mở thư mục `frontend` bằng Live Server và mở `frontend/index.html`. Trang mặc định chuyển đến homepage.
3. Mở Shop, tạo tài khoản hoặc đăng nhập, thêm sản phẩm mẫu vào giỏ, rồi đặt hàng COD.

Schema được tạo hoặc nâng cấp bằng một lệnh duy nhất từ `backend/`:

```powershell
python -m app.db.migrate
```

SQLAlchemy models là nguồn schema chính. `backend/sql/init.sql` là bản SQL tham chiếu được sinh từ models, không phải quy trình khởi tạo thứ hai.

## Các API chính

- Authentication: `/api/auth/register`, `/api/auth/login`, `/api/auth/me`
- Products: `/api/products`
- Cart: `/api/cart`
- Checkout và đơn hàng: `/api/orders/checkout`, `/api/orders/{id}`
- Wishlist: `/api/wishlist`
- API docs: `http://127.0.0.1:8000/docs`

API được bảo vệ nhận JWT qua `Authorization: Bearer <token>`. User role và quyền sở hữu store/cart/order được kiểm tra ở backend.

## Cấu trúc

```text
backend/   FastAPI, SQLAlchemy models, migrations, SQL snapshot
frontend/  Trang bán hàng, đăng nhập, giỏ hàng và thanh toán COD
```
