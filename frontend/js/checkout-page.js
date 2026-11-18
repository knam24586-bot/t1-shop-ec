(() => {
  const api = window.T1Api;
  const form = document.getElementById("checkoutForm");
  const summary = document.getElementById("checkoutSummary");
  const message = document.getElementById("checkoutMessage");
  const completed = document.getElementById("checkoutComplete");
  const button = document.getElementById("placeOrderButton");
  const money = (value) => new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(Number(value || 0));

  function showMessage(text) {
    message.textContent = text;
    message.hidden = !text;
  }

  function requireLogin() {
    window.location.href = "./Login.html?next=Checkout.html";
  }

  async function loadSummary() {
    if (!api.getToken()) return requireLogin();
    try {
      const cart = await api.get("/cart");
      if (!cart.items.length) {
        showMessage("Giỏ hàng đang trống. Hãy thêm sản phẩm trước khi thanh toán.");
        button.disabled = true;
      }
      summary.lastElementChild.textContent = money(cart.total_amount);
    } catch (error) {
      if (error.status === 401) {
        api.clearToken();
        return requireLogin();
      }
      showMessage(error.message || "Không tải được thông tin giỏ hàng.");
      button.disabled = true;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    showMessage("");
    button.disabled = true;
    try {
      const order = await api.post("/orders/checkout", {
        shipping_address: document.getElementById("shippingAddress").value,
        payment_method: "COD",
      });
      form.hidden = true;
      completed.hidden = false;
      completed.replaceChildren();
      const title = document.createElement("h2");
      title.textContent = "Đặt hàng thành công";
      const code = document.createElement("p");
      code.textContent = `Mã đơn hàng: ${order.order_code}`;
      const total = document.createElement("p");
      total.textContent = `Tổng tiền: ${money(order.total_price)} · Thanh toán COD`;
      const link = document.createElement("a");
      link.className = "commerce-button";
      link.href = "./Shop.html";
      link.textContent = "Tiếp tục mua sắm";
      completed.append(title, code, total, link);
    } catch (error) {
      if (error.status === 401) {
        api.clearToken();
        return requireLogin();
      }
      showMessage(error.message || "Không thể đặt hàng. Hãy thử lại.");
      button.disabled = false;
    }
  });

  loadSummary();
})();
