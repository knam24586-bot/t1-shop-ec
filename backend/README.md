# T1 Shop EC — Backend

FastAPI, SQLAlchemy 2 và MySQL 8. SQLAlchemy models là nguồn schema chính; các migration có revision được áp dụng qua một lệnh duy nhất.

## Khởi tạo hoặc nâng cấp database

Từ thư mục `backend`, cấu hình `.env`, sau đó chạy:

```powershell
python -m app.db.migrate
```

Lệnh này tạo database khi tài khoản DB có quyền, tạo các bảng còn thiếu, nâng cấp schema cũ, ghi revision đã áp dụng và tạo dữ liệu mẫu cho trang Shop. Chạy lại lệnh này an toàn; dữ liệu hiện có được giữ lại. Không chạy `sql/init.sql` bằng Workbench hoặc để Docker tự nạp file SQL.

`sql/init.sql` là bản SQL tham chiếu được sinh từ model hiện tại. Cập nhật bản tham chiếu sau khi sửa model bằng:

```powershell
python -m app.db.migrate --write-sql
```

## Cài đặt và chạy local

```powershell
cd backend
copy .env.example .env
```

Điền kết nối MySQL trong `.env`, cài dependency và khởi tạo schema:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.db.migrate
uvicorn app.main:app --reload
```

Mặc định API ở `http://127.0.0.1:8000`; Swagger tại `/docs`; health check tại `/api/health`.

## MySQL bằng Docker

```powershell
cd backend
docker compose up -d
copy .env.example .env
```

Trong `.env`, dùng `DB_HOST=127.0.0.1`, `DB_PORT=3307`, `DB_USER=app_user`, `DB_PASSWORD=app_password`, `DB_NAME=t1shop_db`, rồi chạy đúng lệnh `python -m app.db.migrate` như trên. Compose chỉ cung cấp MySQL; schema được tạo và nâng cấp bởi migrator.

## Đăng nhập và quyền

- `POST /api/auth/register`: tạo tài khoản CUSTOMER và trả access token.
- `POST /api/auth/login`: đăng nhập bằng email/mật khẩu.
- Các API cần tài khoản nhận `Authorization: Bearer <access_token>`.
- Role và `store_id` được đọc từ bản ghi User hiện tại trong database. Không dùng `X-User-Id`, `X-Role`, `X-Store-Id` hay `X-Admin-Role` để cấp quyền.
- Để tạo administrator đầu tiên, đặt `BOOTSTRAP_ADMIN_EMAIL` và `BOOTSTRAP_ADMIN_PASSWORD` (ít nhất 12 ký tự) trong `.env`, rồi chạy migrator. Tài khoản chỉ được tạo nếu email chưa tồn tại; migrator không tự nâng quyền tài khoản cũ.
- `JWT_SECRET` trong ví dụ chỉ dành cho local development. Trước khi đặt `APP_ENV=production`, thay bằng secret ngẫu nhiên riêng dài tối thiểu 32 ký tự.

## Luồng mua hàng hiện có

1. Đăng ký hoặc đăng nhập.
2. `GET /api/products`, `GET/POST/PUT/DELETE /api/cart` để xem và sửa giỏ hàng.
3. `POST /api/orders/checkout` với địa chỉ giao hàng và `payment_method: "COD"`.
4. Trong cùng transaction, backend kiểm tra tồn kho, tạo order/order items/payment, giảm tồn kho biến thể và sản phẩm, rồi dọn cart.
5. `GET /api/orders/{id}` chỉ trả đơn hàng thuộc tài khoản đang đăng nhập.

Checkout luôn lấy giá từ database, khóa các dòng tồn kho khi xử lý và rollback toàn bộ nếu có lỗi.
