# Frontend T1 Shop

Frontend dùng HTML/CSS/JavaScript thuần, gọi backend qua `js/api.js` và Fetch API.

## Chạy

1. Khởi động MySQL và backend theo `../backend/README.md`.
2. Mở thư mục `frontend` bằng VS Code Live Server.
3. Mở `index.html`; trang sẽ điều hướng tới homepage. Vào `pages/Shop.html` để xem danh sách sản phẩm từ API.

## Luồng mua hàng

- Đăng ký tại `pages/Sign-in.html` hoặc đăng nhập tại `pages/Login.html`.
- Access token được dùng trong các request dưới header `Authorization: Bearer ...`.
- Nút thêm vào giỏ gọi `POST /api/cart/items`; trang `Cart.html` đọc và sửa giỏ từ API.
- `Checkout.html` gửi địa chỉ giao hàng và phương thức COD đến `POST /api/orders/checkout`.
- Giá, quyền sở hữu và tồn kho được xác nhận ở backend.

Địa chỉ API mặc định là `http://127.0.0.1:8000/api`; có thể đặt `window.T1_API_BASE_URL` trước khi nạp `js/api.js` nếu cần đổi host.
