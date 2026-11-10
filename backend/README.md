# Backend base: Python FastAPI + MySQL

Khung backend chung cho các nhóm thực tập lớp **HN-KS25-CNTT1**. Đã có sẵn:

- Kết nối **MySQL** bằng SQLAlchemy + PyMySQL, cấu hình đọc từ file `.env`
- **CRUD mẫu** cho bảng `items` (thêm / xem / sửa / xoá / tìm kiếm)
- Endpoint **health-check** `GET /api/health` kiểm tra kết nối DB
- **CORS** đã bật để frontend gọi được
- File `sql/init.sql` tạo database + bảng + dữ liệu mẫu, chạy bằng **MySQL Workbench**
- Trang tài liệu API tự sinh: http://127.0.0.1:8000/docs

## 1. Cần cài trước

| Phần mềm | Ghi chú |
|---|---|
| Python **3.10 trở lên** | https://www.python.org/downloads/ (Windows: tick **Add python.exe to PATH** khi cài) |
| MySQL Server 8 + MySQL Workbench | Bản các bạn đang dùng trên lớp là được |

Kiểm tra Python: mở terminal gõ `python --version` (Mac: `python3 --version`).

## 2. Cấu trúc thư mục

```
backend/
├── app/
│   ├── main.py            # Điểm khởi động: tạo app, bật CORS, gắn các router
│   ├── core/config.py     # Đọc cấu hình từ .env
│   ├── db/session.py      # Kết nối MySQL, hàm get_db()
│   ├── models/            # Model = bảng trong DB (item.py)
│   ├── schemas/           # Schema = dữ liệu vào/ra của API (item.py)
│   ├── crud/              # Hàm đọc/ghi DB (item.py)
│   └── routers/           # Khai báo các API (health.py, items.py)
├── sql/init.sql           # Tạo database + bảng + dữ liệu mẫu (chạy bằng Workbench)
├── requirements.txt       # Danh sách thư viện Python
├── .env.example           # Mẫu file cấu hình
└── docker-compose.yml     # KHÔNG bắt buộc, xem mục 8
```

Một request đi qua các lớp như sau:

```
Frontend --HTTP--> routers/items.py --> crud/item.py --> models/item.py --> MySQL
                   (kiểm tra dữ liệu bằng schemas/item.py)
```

## 3. Bước 1: tạo database bằng MySQL Workbench

1. Mở **MySQL Workbench**, bấm vào connection **Local instance MySQL80** (hoặc connection bạn hay dùng), nhập mật khẩu root.
2. Menu **File → Open SQL Script...**, chọn file `backend/sql/init.sql`.
3. Bấm nút **tia sét ⚡ (Execute)** để chạy cả file.
4. Ở khung **SCHEMAS** bên trái, bấm nút **Refresh ⟳**. Thấy `app_db` → `Tables` → `items` là xong.
5. Chuột phải bảng `items` → **Select Rows - Limit 1000** để xem 2 dòng dữ liệu mẫu.

> Nhớ lại thông tin connection (chuột phải connection ở màn hình Home → **Edit Connection**): **Hostname** (thường `127.0.0.1`), **Port** (thường `3306`), **Username** (thường `root`) và mật khẩu. Bước sau sẽ điền đúng các thông tin này.

## 4. Bước 2: tạo file `.env`

Mở terminal **trong thư mục `backend/`** (VS Code: chuột phải thư mục `backend` → *Open in Integrated Terminal*).

```bash
# Windows
copy .env.example .env
# Mac / Linux
cp .env.example .env
```

Mở file `.env`, điền **mật khẩu root MySQL** của bạn:

```
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=mat_khau_root_cua_ban
DB_NAME=app_db
```

## 5. Bước 3: cài thư viện Python

Tạo môi trường ảo (chỉ làm 1 lần):

```bash
python -m venv .venv
```

Kích hoạt môi trường ảo (làm lại **mỗi lần mở terminal mới**):

| Hệ điều hành | Lệnh |
|---|---|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows CMD | `.venv\Scripts\activate.bat` |
| Mac / Linux | `source .venv/bin/activate` |

> PowerShell báo lỗi "running scripts is disabled"? Chạy một lần:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Khi đầu dòng terminal hiện `(.venv)` là đã kích hoạt. Cài thư viện:

```bash
pip install -r requirements.txt
```

## 6. Bước 4: chạy server

```bash
uvicorn app.main:app --reload
```

Terminal in ra `[DB] Đã kết nối MySQL ...` là thành công. `--reload` giúp server tự khởi động lại mỗi khi bạn lưu code. Tắt server: `Ctrl + C`.

Kiểm tra:

- http://127.0.0.1:8000/api/health → `{"status":"ok","database":"connected"}`
- http://127.0.0.1:8000/docs → thử trực tiếp mọi API bằng nút **Try it out**
- Thêm 1 item ở `/docs` (hoặc từ frontend), rồi quay lại Workbench chạy `SELECT * FROM app_db.items;` sẽ thấy dòng mới.

## 7. Danh sách API mẫu

| Method | URL | Việc làm | Body (JSON) |
|---|---|---|---|
| GET | `/api/health` | Kiểm tra server + DB | |
| GET | `/api/items` | Danh sách, tìm theo tên `?q=com` | |
| GET | `/api/items/{id}` | Chi tiết | |
| POST | `/api/items` | Thêm mới | `{"name": "Trà đá", "description": "...", "price": 5000}` |
| PUT | `/api/items/{id}` | Sửa (gửi trường nào sửa trường đó) | `{"price": 6000}` |
| DELETE | `/api/items/{id}` | Xoá | |

Khi lỗi, API trả về JSON dạng `{"detail": "..."}`. Ví dụ: 404 khi không tìm thấy, 422 khi dữ liệu gửi lên sai.

## 8. Frontend nối với backend thế nào?

- Frontend gọi tới `http://127.0.0.1:8000/api/...` (cấu hình ở `frontend/js/config.js`).
- Trình duyệt chặn web ở địa chỉ khác gọi API nếu backend không cho phép. Đó là **CORS**. Backend đã cho phép bằng `CORS_ORIGINS` trong `.env`:
  - `CORS_ORIGINS=*` cho phép mọi nơi (mặc định, tiện khi học)
  - Khi deploy thật, ghi rõ domain: `CORS_ORIGINS=https://nhom1.example.com`
- Sửa `.env` xong phải **tắt (`Ctrl + C`) và chạy lại** uvicorn.

## 9. Thêm chức năng cho đề tài (vd: bảng `products`)

1. **Tạo bảng trong MySQL:** viết câu `CREATE TABLE products (...)` vào file mới `sql/products.sql`, chạy bằng Workbench như bước 1. Lưu file `.sql` lại để cả nhóm cùng chạy.
2. `app/models/product.py`: copy `item.py`, đổi tên class, `__tablename__ = "products"` và các cột cho **giống bảng vừa tạo**.
3. `app/models/__init__.py`: thêm `from app.models.product import Product`.
4. `app/schemas/product.py`: copy `schemas/item.py`, sửa các trường.
5. `app/crud/product.py`: copy `crud/item.py`, đổi `Item` thành `Product`.
6. `app/routers/products.py`: copy `routers/items.py`, đổi `prefix="/products"`.
7. `app/main.py`: thêm `app.include_router(products.router, prefix="/api")`.
8. Chạy lại server, mở `/docs` sẽ thấy nhóm API **Products**.

> Mẹo: nếu quên bước 1, server cũng tự tạo bảng còn thiếu theo model khi khởi động. Nhưng nó **không sửa** bảng đã có. Muốn thêm/sửa cột, hãy dùng `ALTER TABLE ...` trong Workbench rồi sửa model cho khớp.

## 10. Lỗi hay gặp

| Lỗi | Cách sửa |
|---|---|
| `Access denied for user 'root'@'localhost'` | Sai `DB_PASSWORD` trong `.env`. Dùng đúng mật khẩu đăng nhập Workbench |
| `Can't connect to MySQL server on '127.0.0.1'` | MySQL chưa bật. Windows: mở **Services**, tìm **MySQL80**, bấm **Start**. Hoặc kiểm tra lại `DB_PORT` |
| `Unknown database 'app_db'` | Chưa chạy `sql/init.sql` trong Workbench (bước 1) |
| `ModuleNotFoundError: No module named 'fastapi'` | Chưa kích hoạt `.venv` hoặc chưa `pip install -r requirements.txt` |
| `Error loading ASGI app. Could not import module "app.main"` | Đang đứng sai thư mục. Phải `cd` vào `backend/` rồi mới chạy uvicorn |
| `'python' is not recognized...` / mở ra Microsoft Store | Cài lại Python và tick **Add python.exe to PATH** |
| Cổng 8000 đã bị dùng | `uvicorn app.main:app --reload --port 8001`, nhớ sửa `frontend/js/config.js` theo |
| Tiếng Việt bị lỗi font trong DB | Database/bảng phải là `utf8mb4`. Tạo bằng `sql/init.sql` là đúng sẵn |

## 11. (Không bắt buộc) Chạy MySQL bằng Docker

Chỉ dành cho bạn nào đã biết Docker và không muốn cài MySQL. Trong `backend/` chạy `docker compose up -d`: MySQL chạy ở cổng **3307**, tự tạo bảng từ `sql/init.sql`. Khi đó sửa `.env` thành `DB_PORT=3307`, `DB_USER=app_user`, `DB_PASSWORD=app_password`.
