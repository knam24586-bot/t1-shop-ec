# Frontend base: HTML · CSS · JavaScript thuần + axios

Khung frontend chung cho các nhóm thực tập lớp **HN-KS25-CNTT1**. Không dùng framework, không cần cài đặt hay build gì. Đã có sẵn:

- Layout chung (header + menu + footer) cho mọi trang
- Module gọi API `js/api.js` dùng **axios**: cấu hình `baseURL` một lần, gom xử lý lỗi một chỗ bằng interceptor
- Trang chủ kiểm tra kết nối **Frontend → Backend → MySQL**
- Trang **Items**: ví dụ CRUD đầy đủ (thêm / sửa / xoá / tìm kiếm) gọi sang backend FastAPI

## 1. Cấu trúc thư mục

```
frontend/
├── index.html             # Trang chủ (kiểm tra kết nối)
├── pages/
│   └── items.html         # Trang CRUD mẫu
├── css/
│   └── style.css          # Style chung, đổi màu ở :root
├── js/
│   ├── config.js          # API_BASE_URL: địa chỉ backend
│   ├── api.js             # axios instance + api.get / post / put / delete
│   ├── utils.js           # escapeHtml, formatMoney, showToast...
│   ├── layout.js          # Chèn header/menu/footer vào mọi trang
│   └── pages/             # Mỗi trang 1 file JS riêng
│       ├── home.js
│       └── items.js
└── assets/images/         # Ảnh, logo, icon
```

## 2. Chạy frontend

**Bước 1: chạy backend trước.** Làm theo `backend/README.md` cho đến khi mở http://127.0.0.1:8000/api/health thấy `"database":"connected"`.

**Bước 2: mở frontend bằng Live Server.** Trong VS Code, cài extension *Live Server* (Ritwick Dey), chuột phải `frontend/index.html` → **Open with Live Server**. Trang mở ở `http://127.0.0.1:5500/index.html` và tự tải lại khi bạn lưu file.

Trang chủ hiện **✅ Backend OK · MySQL: connected** là FE đã nối được BE. Bấm menu **Items (CRUD mẫu)** để thử thêm / sửa / xoá, rồi mở MySQL Workbench xem bảng `items` thay đổi theo.

> Nhấp đúp mở thẳng file `index.html` (địa chỉ `file:///...`) thường vẫn chạy, nhưng hay gặp lỗi khó hiểu. Nên dùng Live Server.

## 3. Frontend nối với backend thế nào?

```
Trình duyệt (FE: 127.0.0.1:5500) --axios--> Backend FastAPI (127.0.0.1:8000/api) --> MySQL
```

- **axios** được nạp từ CDN bằng thẻ `<script>` ở cuối mỗi trang HTML (cần có mạng). Không cần `npm install`.
- Địa chỉ backend nằm ở **một chỗ duy nhất**: `js/config.js`
  ```js
  API_BASE_URL: "http://127.0.0.1:8000/api",
  ```
  Backend đổi cổng, hoặc deploy lên server, thì chỉ sửa dòng này.
- Mọi lời gọi API đều qua `js/api.js`. File này tạo sẵn 1 axios instance (`http`) có `baseURL`, và bọc thành các hàm trả về thẳng `response.data`:
  ```js
  try {
    const items = await api.get("/items");               // GET  /api/items
    const found = await api.get("/items", { q: "trà" }); // GET  /api/items?q=trà
    const item  = await api.post("/items", { name: "Trà đá", price: 5000 });
    await api.put(`/items/${item.id}`, { price: 6000 });
    await api.delete(`/items/${item.id}`);
  } catch (error) {
    showToast(error.message, "error");  // câu báo lỗi đã được dịch cho dễ đọc
    console.log(error.status);          // 404, 422, 500... hoặc 0 nếu không gọi được server
  }
  ```
- Cần gửi token đăng nhập kèm mọi request? Trong `js/api.js` đã có sẵn đoạn interceptor mẫu (đang comment), chỉ cần bỏ comment.
- Backend phải cho phép FE gọi (**CORS**). Base code backend đã bật sẵn (`CORS_ORIGINS=*` trong `backend/.env`).

## 4. Thêm trang mới (vd: trang Sản phẩm)

1. Copy `pages/items.html` thành `pages/products.html`, sửa `<title>` và nội dung HTML.
2. Copy `js/pages/items.js` thành `js/pages/products.js`, đổi `/items` thành `/products` (API của nhóm bạn).
3. Ở cuối `pages/products.html`, đổi `../js/pages/items.js` thành `../js/pages/products.js`.
4. Thêm link vào menu trong `js/layout.js`:
   ```js
   { href: "pages/products.html", label: "Sản phẩm" },
   ```

Lưu ý khi tạo trang:

- Trang trong `pages/` để `<body data-root="../">`; trang ở thư mục gốc để `data-root="./"`.
- Giữ thứ tự thẻ `<script>`: axios (CDN) → `config.js` → `api.js` → `utils.js` → `layout.js` → script riêng của trang.
- Khi chèn dữ liệu người dùng nhập vào `innerHTML`, luôn bọc bằng `escapeHtml(...)` để chống chèn mã độc (XSS).

## 5. Lỗi hay gặp

| Hiện tượng | Cách sửa |
|---|---|
| "Không kết nối được backend..." | Backend chưa chạy, hoặc `API_BASE_URL` trong `js/config.js` sai cổng |
| "Backend chạy nhưng MySQL lỗi" | Xem mục *Lỗi hay gặp* trong `backend/README.md` |
| Console báo `axios is not defined` | Máy không có mạng nên không tải được axios từ CDN, hoặc thẻ `<script>` axios bị đặt sau `api.js` |
| Console (F12) báo `blocked by CORS policy` | Kiểm tra `CORS_ORIGINS` trong `backend/.env`, sửa xong nhớ chạy lại backend |
| Menu/header không hiện | Sai `data-root` ở thẻ `<body>`, hoặc sai đường dẫn file JS. Mở F12 → Console để xem lỗi |
| Sửa code mà trang không đổi | Tải lại cứng: `Ctrl + F5` |
