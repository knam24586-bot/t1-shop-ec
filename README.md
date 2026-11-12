# T1 Shop EC

Hệ thống cửa hàng thương mại điện tử gồm backend FastAPI và frontend HTML/CSS/JavaScript thuần. Backend sử dụng MySQL làm cơ sở dữ liệu và SQLAlchemy để ánh xạ dữ liệu thành các model Python.

## Kiến trúc

```text
Frontend (Live Server)
        │ HTTP/JSON
        ▼
FastAPI backend (:8000)
        │ SQLAlchemy + PyMySQL
        ▼
MySQL (:3306)
```

## Công nghệ

- **Backend:** Python 3.10+, FastAPI, SQLAlchemy 2, PyMySQL
- **Database:** MySQL 8, UTF-8 (`utf8mb4`)
- **Frontend:** HTML, CSS, JavaScript thuần, Axios CDN
- **Tài liệu API:** Swagger UI tại `/docs`

## Cấu trúc dự án

```text
.
├── backend/
│   ├── app/
│   │   ├── core/              # Cấu hình môi trường
│   │   ├── crud/              # Truy vấn và thao tác dữ liệu
│   │   ├── db/                # SQLAlchemy engine và session
│   │   ├── models/            # Item, Category, Product, ProductVariant,
│   │   │                       # Vendor và Store
│   │   ├── routers/            # Các endpoint FastAPI
│   │   └── schemas/            # Pydantic request/response schemas
│   ├── sql/init.sql            # Khởi tạo database và các bảng
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
| `ProductVariant` | Biến thể sản phẩm với SKU duy nhất, màu, size và tồn kho |
| `Vendor` | Nhà cung cấp |
| `Store` | Cửa hàng thuộc một Vendor; không trùng tên trong cùng Vendor |
| `Item` | Bảng mẫu dùng để kiểm tra CRUD |

Chi tiết quan hệ và ràng buộc được định nghĩa trong `backend/app/models/` và đồng bộ trong `backend/sql/init.sql`.

## Chạy backend

### 1. Khởi tạo cơ sở dữ liệu

Mở MySQL Workbench và chạy toàn bộ file [`backend/sql/init.sql`](backend/sql/init.sql).

### 2. Cấu hình môi trường

```powershell
cd backend
copy .env.example .env
```

Mở `.env` và điền thông tin MySQL:

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=mat_khau_mysql
DB_NAME=t1shop_db
```

### 3. Cài dependency và chạy server

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend mặc định chạy tại `http://127.0.0.1:8000`.

- Health check: `http://127.0.0.1:8000/api/health`
- Swagger UI: `http://127.0.0.1:8000/docs`

## Chạy frontend

Mở thư mục dự án bằng VS Code, cài extension **Live Server**, sau đó mở `frontend/index.html` bằng **Open with Live Server**. Frontend mặc định gọi backend tại `http://127.0.0.1:8000/api`.

## Quy tắc phát triển

1. Khi thêm model, đăng ký model trong `backend/app/models/__init__.py`.
2. Khi thay đổi schema database, cập nhật `backend/sql/init.sql`.
3. Không commit file `.env`, mật khẩu hoặc thông tin kết nối thật.
4. Chạy kiểm tra Python trước khi commit:

   ```powershell
   cd backend
   python -m compileall -q app
   ```

5. Tạo branch theo task, ví dụ `feature/cn-04-store`.

## Docker MySQL (tùy chọn)

Nếu dùng Docker, chạy trong thư mục `backend`:

```powershell
docker compose up -d
```

Thiết lập `DB_PORT=3307` nếu MySQL container được expose qua cổng 3307 trên máy host.
