# T1 Shop EC

Hệ thống cửa hàng thương mại điện tử gồm backend FastAPI và frontend
HTML/CSS/JavaScript thuần. Backend sử dụng MySQL và SQLAlchemy để ánh xạ dữ
liệu thành các model Python.

## Kiến trúc

```text
Frontend (Live Server)
        │ HTTP/JSON
        ▼
FastAPI backend (:8000)
        │ SQLAlchemy + PyMySQL
        ▼
MySQL (:3307 trên máy khi chạy Docker)
```

## Công nghệ

- **Backend:** Python 3.10+, FastAPI, SQLAlchemy 2, Alembic, PyMySQL
- **Database:** MySQL 8, UTF-8 (`utf8mb4`)
- **Frontend:** HTML, CSS, JavaScript thuần, Axios CDN
- **Tài liệu API:** Swagger UI tại `/docs`

## Cấu trúc dự án

```text
.
├── backend/
│   ├── alembic/versions/       # Lịch sử schema chuẩn
│   ├── app/
│   │   ├── core/               # Cấu hình môi trường
│   │   ├── crud/               # Truy vấn và thao tác dữ liệu
│   │   ├── db/                 # Kết nối, bootstrap và seed database
│   │   ├── models/             # SQLAlchemy models
│   │   ├── routers/            # Các endpoint
│   │   └── schemas/            # Request/response schemas
│   ├── docker-compose.yml      # MySQL local
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── pages/
│   ├── css/
│   └── assets/
└── README.md
```

## Các model chính

| Model | Mô tả |
|---|---|
| `Category` | Danh mục sản phẩm, hỗ trợ danh mục cha/con |
| `Product` | Sản phẩm thuộc một danh mục |
| `ProductVariant` | Biến thể sản phẩm với SKU, màu, size và tồn kho |
| `Vendor` | Nhà cung cấp |
| `Store` | Cửa hàng thuộc một Vendor |
| `Cart` / `CartItem` | Giỏ hàng theo người dùng và biến thể sản phẩm |
| `Order` / `OrderItem` | Đơn hàng và dòng sản phẩm đã mua |
| `Payment` | Thông tin giao dịch thanh toán |
| `Item` | Bảng mẫu dùng để kiểm tra CRUD |

Quan hệ và ràng buộc schema nằm trong `backend/app/models/`; Alembic migrations
là nguồn duy nhất để tạo và nâng cấp database.

## Khởi tạo và chạy backend

Chạy trong PowerShell tại thư mục dự án:

```powershell
cd backend
copy .env.example .env
docker compose up -d mysql
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.db.bootstrap
uvicorn app.main:app --reload
```

Database chuẩn là `t1shop_db`, Docker mở MySQL tại cổng host `3307`.
`python -m app.db.bootstrap` chạy migrations và seed dữ liệu demo; có thể chạy
lại mà không ghi đè dữ liệu đã có. Hướng dẫn nâng cấp database cũ và chuyển
`cart_items.product_id` sang `variant_id` nằm trong
[backend/README.md](backend/README.md).

Trước khi đăng nhập, tạo `JWT_SECRET_KEY` riêng trong `backend/.env` bằng
`python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Backend mặc định chạy tại `http://127.0.0.1:8000`.

- Health check: `http://127.0.0.1:8000/api/health`
- Swagger UI: `http://127.0.0.1:8000/docs`

## Chạy frontend

Mở thư mục dự án bằng VS Code, cài extension **Live Server**, sau đó mở
`frontend/index.html` bằng **Open with Live Server**. Frontend mặc định gọi
backend tại `http://127.0.0.1:8000/api`.

## Quy tắc phát triển

1. Khi thêm model, đăng ký model trong `backend/app/models/__init__.py`.
2. Khi thay đổi schema, tạo Alembic revision mới; không cập nhật SQL init riêng.
3. Không commit file `.env`, mật khẩu hoặc thông tin kết nối thật.
4. Tạo branch theo task, ví dụ `feature/cn-04-store`.
