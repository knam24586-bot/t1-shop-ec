# Backend T1 Shop EC

Backend của dự án thương mại điện tử T1 Shop EC, xây dựng bằng FastAPI và
SQLAlchemy, kết nối MySQL qua PyMySQL. Tên database chuẩn là `t1shop_db`.

## Chức năng hiện có

- Kết nối MySQL bằng cấu hình trong `.env`
- Health check kiểm tra trạng thái API và database
- CRUD mẫu cho bảng `items`
- API đọc công khai sản phẩm và danh mục
- API quản lý Store và tồn kho
- SQLAlchemy models cho sản phẩm, giỏ hàng, đơn hàng, thanh toán, người dùng,
  nhà cung cấp, cửa hàng và các bảng lịch sử liên quan
- CORS để frontend gọi API
- Swagger UI tự sinh tại `/docs`

## Public Product API

Các endpoint đọc sản phẩm không yêu cầu xác thực và chỉ trả sản phẩm có trạng
thái `Published` thuộc danh mục `Active`. Kết quả được phân trang với thứ tự ổn
định theo ID giảm dần.

| Method | URL | Mô tả |
|---|---|---|
| GET | `/api/products` | Danh sách sản phẩm công khai |
| GET | `/api/products/{id}` | Chi tiết sản phẩm công khai |
| GET | `/api/products/search?q=...` | Tìm kiếm có phân trang |
| GET | `/api/products/filter` | Lọc theo danh mục, giá và đánh giá |

Sản phẩm Draft/Archived không xuất hiện trong kết quả công khai.

## Register / Login / Logout

| Method | URL | Mô tả |
|---|---|---|
| POST | `/api/auth/register` | Tạo tài khoản khách hàng |
| POST | `/api/auth/login` | Đăng nhập bằng email hoặc số điện thoại; trả JWT và role |
| GET | `/api/auth/me` | Trả thông tin tài khoản từ bearer token hiện tại |
| POST | `/api/auth/logout` | Thu hồi access token đã cấp cho tài khoản |

Đăng ký nhận `full_name`, `email`, `phone` và `password`; email/số điện thoại
được chuẩn hóa và phải duy nhất. Tài khoản mới luôn có role `CUSTOMER`. Mật khẩu
được lưu dưới dạng hash PBKDF2. Các API cần đăng nhập nhận
`Authorization: Bearer <access_token>`; danh tính, role và Store được đọc từ
token đã ký và bản ghi User, không tin `X-User-Id`, `X-Role`, `X-Admin-Role` hay
`X-Store-Id` từ client.

Access token hết hạn theo `ACCESS_TOKEN_EXPIRE_MINUTES`. Logout tăng
`token_version` trong database để thu hồi token ngay. Role `ADMIN`/`VENDOR` và
`store_id` phải được cấp ở backend/database; API đăng ký không cho chọn chúng.

Secret JWT lấy từ `JWT_SECRET_KEY` trong `.env`. Tạo secret riêng bằng:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Không dùng secret mẫu trong `.env.example` khi chia sẻ hoặc triển khai.

Lỗi API trả cùng cấu trúc `success`, `error.code`, `error.message`,
`error.details` và `request_id`. Middleware ghi log method/path/status và request
ID; response có header `X-Request-ID`. Stack trace chỉ nằm trong log server,
không trả về client.

## Category API

Các endpoint danh mục nằm dưới `/api/categories`. Endpoint đọc không yêu cầu
quyền; endpoint tạo, cập nhật và vô hiệu hóa yêu cầu tài khoản có role `ADMIN`
trong database và header `Authorization: Bearer <access_token>`.

| Method | URL | Mô tả |
|---|---|---|
| GET | `/api/categories` | Danh sách danh mục |
| GET | `/api/categories/{id}` | Chi tiết danh mục |
| POST | `/api/categories` | Tạo danh mục |
| PUT | `/api/categories/{id}` | Cập nhật danh mục |
| PATCH | `/api/categories/{id}/disable` | Chuyển trạng thái sang `Inactive` |

Body tạo/cập nhật hỗ trợ `name`, `slug`, `status` và `parent_id`. `slug` phải ở
dạng chữ thường, số và dấu gạch ngang; `parent_id` phải trỏ tới danh mục tồn tại
và không được trỏ tới chính danh mục đó.

## Vendor Store API

Vendor chỉ được truy cập Store có `store_id` gắn với tài khoản trong database.
Admin có thể truy cập Store bất kỳ; endpoint `/api/stores/me` yêu cầu tài khoản
được gán Store.

| Method | URL | Mô tả |
|---|---|---|
| GET | `/api/stores/me` | Xem Store được gán |
| PATCH | `/api/stores/me` | Cập nhật thông tin Store được gán |
| GET | `/api/stores/{id}` | Xem Store theo ID |
| PATCH | `/api/stores/{id}` | Cập nhật Store theo ID |

Vendor được cập nhật tên, email, số điện thoại và địa chỉ; chỉ Admin được đổi
`status`. Backend tự kiểm tra Store ownership từ tài khoản đã đăng nhập.

## Inventory API

Các endpoint tồn kho nằm dưới `/api/inventory` và yêu cầu bearer token của
`ADMIN` hoặc `VENDOR`. Vendor chỉ quản lý sản phẩm thuộc Store gắn với tài khoản;
tồn kho dùng `variant_id` và mọi thay đổi đều tạo một bản ghi lịch sử.

| Method | URL | Mô tả |
|---|---|---|
| GET | `/api/inventory` | Danh sách tồn kho |
| GET | `/api/inventory/{variant_id}` | Kiểm tra tồn kho |
| POST | `/api/inventory/{variant_id}/receive` | Nhập thêm hàng (`quantity > 0`) |
| POST | `/api/inventory/{variant_id}/adjust` | Điều chỉnh tăng/giảm (`quantity != 0`) |
| PUT | `/api/inventory/{variant_id}` | Đặt tồn kho tuyệt đối (`stock >= 0`) |
| GET | `/api/inventory/{variant_id}/movements` | Lịch sử biến động |

## Khởi tạo database (quy trình chuẩn duy nhất)

Chạy các lệnh PowerShell trong thư mục `backend`:

```powershell
copy .env.example .env
docker compose up -d mysql
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.db.bootstrap
```

Database chuẩn là `t1shop_db`; Docker mở MySQL tại `127.0.0.1:3307`. Lệnh
bootstrap chạy toàn bộ Alembic migrations rồi seed danh mục, sản phẩm/biến thể
mẫu và tài khoản demo nếu chưa có. Seed có thể chạy lại mà không ghi đè dữ liệu
đã tồn tại. Tài khoản demo lấy email và mật khẩu từ `SEED_DEMO_USER_*` trong
`.env`; database chỉ lưu mật khẩu đã băm. Hãy đổi mật khẩu mẫu trước khi chia sẻ
môi trường. Nếu `.env` tạo từ phiên bản trước, hãy bổ sung `JWT_SECRET_KEY` và
`ACCESS_TOKEN_EXPIRE_MINUTES` như hướng dẫn đăng nhập ở trên.

Nếu kết nối tới MySQL cài sẵn trên máy thay vì Docker, hãy tạo database
`t1shop_db`, cấp quyền cho tài khoản trong `.env`, rồi vẫn chạy đúng lệnh
`python -m app.db.bootstrap`.

### Database đã có dữ liệu

Hãy sao lưu trước khi nâng cấp. Sau đó cấu hình `.env` trỏ tới database cần
nâng cấp và chạy bootstrap. Migration nhận diện bảng cũ, bổ sung bảng/cột còn
thiếu và không xóa các bảng đang có.

Với `cart_items` cũ, migration tự chuyển `product_id` thành `variant_id` khi sản
phẩm chỉ có một biến thể hoặc có đúng một biến thể mặc định (không màu/size).
Nếu sản phẩm có nhiều biến thể mà không thể xác định lựa chọn cũ, migration sẽ
dừng và liệt kê `cart_item_id`/`product_id`; hãy đặt `variant_id` đúng cho từng
dòng rồi chạy lại bootstrap. Cột `product_id` chỉ bị bỏ sau khi mọi dòng được
chuyển thành công. Sản phẩm cũ chưa có biến thể sẽ được tạo biến thể `LEGACY-P{id}`
với tồn kho hiện tại của sản phẩm.

Để xử lý dòng mơ hồ, xem các biến thể bằng
`SELECT id, sku, color, size FROM product_variants WHERE product_id = <product_id>;`,
sau đó cập nhật đúng dòng bằng
`UPDATE cart_items SET variant_id = <variant_id> WHERE id = <cart_item_id>;`.
Chỉ chọn biến thể có `product_id` trùng với sản phẩm được báo lỗi.

Nếu dữ liệu nằm trong database Docker cũ tên `app_db`, hãy sao lưu và chuyển dữ
liệu sang database `t1shop_db` trước khi bootstrap. Không đổi tên hoặc xóa Docker
volume để xử lý việc này vì volume có thể chứa dữ liệu duy nhất.

## Chạy backend

Sau khi bootstrap:

```powershell
uvicorn app.main:app --reload
```

- API: `http://127.0.0.1:8000`
- Health check: `http://127.0.0.1:8000/api/health`
- Swagger UI: `http://127.0.0.1:8000/docs`

## Quy tắc schema

- SQLAlchemy models trong `app/models/` mô tả schema hiện tại.
- `alembic/versions/` là lịch sử thay đổi schema có thứ tự.
- Chạy `python -m app.db.bootstrap` để nâng cấp database và seed dữ liệu.
- Không chạy schema bằng Workbench, không mount SQL init script vào Docker và
  không dùng migration thủ công riêng cho cart.

Khi thay đổi model, hãy tạo và rà soát một Alembic revision mới trước khi chia
sẻ thay đổi với nhóm. Không sửa revision đã được áp dụng trên database dùng chung.
