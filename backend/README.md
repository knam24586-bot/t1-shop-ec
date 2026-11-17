# Backend T1 Shop EC

Backend của dự án thương mại điện tử T1 Shop EC, xây dựng bằng FastAPI và SQLAlchemy, kết nối MySQL qua PyMySQL.

## Chức năng hiện có

- Kết nối MySQL bằng cấu hình trong `.env`
- Health check kiểm tra trạng thái API và database
- CRUD mẫu cho bảng `items`
- SQLAlchemy models cho:
  - `Category`
  - `Product`
  - `ProductVariant`
  - `Vendor`
  - `Store`
- CORS để frontend gọi API
- Swagger UI tự sinh tại `/docs`

Các model sản phẩm, biến thể, vendor và store đã được định nghĩa ở tầng dữ liệu. Router CRUD riêng cho các model này sẽ được bổ sung theo từng task.

## Category API

Các endpoint danh mục nằm dưới `/api/categories`. Endpoint đọc không yêu cầu quyền; endpoint tạo, cập nhật và vô hiệu hóa yêu cầu header quản trị:

```http
X-Admin-Role: admin
```

| Method | URL | Mô tả |
|---|---|---|
| GET | `/api/categories` | Danh sách danh mục |
| GET | `/api/categories/{id}` | Chi tiết danh mục |
| POST | `/api/categories` | Tạo danh mục |
| PUT | `/api/categories/{id}` | Cập nhật danh mục |
| PATCH | `/api/categories/{id}/disable` | Chuyển trạng thái sang `Inactive` |

Body tạo/cập nhật hỗ trợ `name`, `slug`, `status` và `parent_id`. `slug` phải ở dạng chữ thường, số và dấu gạch ngang; `parent_id` phải trỏ tới danh mục tồn tại và không được trỏ tới chính danh mục đó.

## Cấu trúc

```text
backend/
├── app/
│   ├── core/config.py       # Đọc cấu hình từ .env
│   ├── crud/                # Logic truy vấn dữ liệu
│   ├── db/session.py        # Base, engine và database session
│   ├── models/              # SQLAlchemy models
│   ├── routers/             # FastAPI routers
│   └── schemas/             # Pydantic schemas
├── sql/init.sql             # Tạo database, bảng và dữ liệu mẫu
├── requirements.txt
└── .env.example
```

## Yêu cầu

- Python 3.10 trở lên
- MySQL 8 trở lên

## Cài đặt và chạy

### 1. Tạo database

Chạy toàn bộ file `sql/init.sql` bằng MySQL Workbench.

### 2. Tạo cấu hình

```powershell
copy .env.example .env
```

Điền thông tin kết nối trong `.env`:

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=mat_khau_mysql
DB_NAME=t1shop_db
```

### 3. Cài dependency

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. Chạy server

```powershell
uvicorn app.main:app --reload
```

Truy cập:

- API: `http://127.0.0.1:8000`
- Health check: `http://127.0.0.1:8000/api/health`
- Swagger UI: `http://127.0.0.1:8000/docs`

## Kiểm tra

```powershell
python -m compileall -q app
```

Khi thêm hoặc sửa model:

1. Cập nhật file model tương ứng.
2. Đăng ký model trong `app/models/__init__.py`.
3. Cập nhật `sql/init.sql`.
4. Kiểm tra lại metadata và chạy compile.

## Docker MySQL (tùy chọn)

```powershell
docker compose up -d
```

Docker expose MySQL tại cổng `3307` trên host. Khi đó đặt `DB_PORT=3307` trong `.env`.
