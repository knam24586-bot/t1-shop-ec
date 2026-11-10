# Base code dự án thực tập: HN-KS25-CNTT1

Khung dự án chung cho các nhóm (04/11 – 25/11/2026). Gồm 2 phần đã nối sẵn với nhau:

| Thư mục | Công nghệ | Hướng dẫn |
|---|---|---|
| [`backend/`](backend/README.md) | Python FastAPI + MySQL (SQLAlchemy) | `backend/README.md` |
| [`frontend/`](frontend/README.md) | HTML · CSS · JavaScript thuần + axios | `frontend/README.md` |

```
Trình duyệt (frontend) --axios JSON--> FastAPI (backend :8000/api) --SQLAlchemy--> MySQL (:3306)
```

## Chạy nhanh

1. **MySQL Workbench:** File → Open SQL Script → chọn `backend/sql/init.sql` → bấm ⚡ Execute.
2. **Backend** (terminal trong thư mục `backend/`):
   ```bash
   copy .env.example .env               # Mac/Linux: cp .env.example .env
   # mở .env, điền DB_PASSWORD = mật khẩu root MySQL của bạn
   python -m venv .venv
   .venv\Scripts\activate               # Mac/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload        # http://127.0.0.1:8000/docs
   ```
3. **Frontend:** VS Code → chuột phải `frontend/index.html` → *Open with Live Server*.

Trang chủ frontend hiện **✅ Backend OK · MySQL: connected** là đã thông cả 3 tầng. Sau đó mỗi nhóm đổi ví dụ `items` thành các chức năng của đề tài mình (xem mục *Thêm chức năng* / *Thêm trang mới* trong từng README).
