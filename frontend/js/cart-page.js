(() => {
  const api = window.T1Api;
  const content = document.getElementById("cartContent");
  const message = document.getElementById("cartMessage");
  const money = (value) => new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(Number(value || 0));

  function showMessage(text) {
    message.textContent = text;
    message.hidden = !text;
  }

  function requireLogin() {
    window.location.href = "./Login.html?next=Cart.html";
  }

  function render(cart) {
    content.replaceChildren();
    if (!cart.items.length) {
      const empty = document.createElement("div");
      empty.className = "commerce-empty";
      const title = document.createElement("h2");
      title.textContent = "Giỏ hàng đang trống";
      const shop = document.createElement("a");
      shop.className = "commerce-button";
      shop.href = "./Shop.html";
      shop.textContent = "Tiếp tục mua sắm";
      empty.append(title, shop);
      content.append(empty);
      return;
    }

    for (const item of cart.items) {
      const row = document.createElement("article");
      row.className = "commerce-row";
      const info = document.createElement("div");
      const name = document.createElement("div");
      name.className = "commerce-product-name";
      name.textContent = item.product_name || "Sản phẩm";
      const meta = document.createElement("div");
      meta.className = "commerce-product-meta";
      meta.textContent = [item.sku, item.color, item.size].filter(Boolean).join(" · ");
      info.append(name, meta);

      const price = document.createElement("div");
      price.className = "commerce-price";
      price.textContent = money(item.price);
      const quantity = document.createElement("input");
      quantity.className = "commerce-qty";
      quantity.type = "number";
      quantity.min = "1";
      quantity.max = String(Math.max(1, item.stock));
      quantity.value = String(item.quantity);
      quantity.setAttribute("aria-label", `Số lượng ${item.product_name || "sản phẩm"}`);

      const actions = document.createElement("div");
      actions.className = "commerce-actions";
      const update = document.createElement("button");
      update.className = "commerce-button secondary";
      update.type = "button";
      update.textContent = "Cập nhật";
      update.addEventListener("click", async () => {
        try {
          const result = await api.put(`/cart/items/${item.id}`, { quantity: Number(quantity.value) });
          render(result.cart);
          showMessage("");
        } catch (error) {
          if (error.status === 401) return requireLogin();
          showMessage(error.message);
        }
      });
      const remove = document.createElement("button");
      remove.className = "commerce-button link-button";
      remove.type = "button";
      remove.textContent = "Xóa";
      remove.addEventListener("click", async () => {
        try {
          const result = await api.delete(`/cart/items/${item.id}`);
          render(result.cart);
          showMessage("");
        } catch (error) {
          if (error.status === 401) return requireLogin();
          showMessage(error.message);
        }
      });
      actions.append(update, remove);
      row.append(info, price, quantity, actions);
      content.append(row);
    }

    const total = document.createElement("div");
    total.className = "commerce-total";
    const label = document.createElement("span");
    label.textContent = `Tạm tính (${cart.total_items} sản phẩm)`;
    const amount = document.createElement("span");
    amount.textContent = money(cart.total_amount);
    total.append(label, amount);

    const checkout = document.createElement("a");
    checkout.className = "commerce-button";
    checkout.href = "./Checkout.html";
    checkout.textContent = "Tiến hành thanh toán";
    const footer = document.createElement("div");
    footer.className = "commerce-actions";
    footer.style.justifyContent = "space-between";
    footer.append(total, checkout);
    content.append(footer);
  }

  async function loadCart() {
    if (!api.getToken()) return requireLogin();
    try {
      const cart = await api.get("/cart");
      render(cart);
    } catch (error) {
      if (error.status === 401) {
        api.clearToken();
        return requireLogin();
      }
      showMessage(error.message || "Không tải được giỏ hàng.");
    }
  }

  loadCart();
})();
