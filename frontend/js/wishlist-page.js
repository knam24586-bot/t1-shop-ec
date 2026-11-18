(() => {
  const api = window.T1Api;
  const content = document.getElementById("wishlistContent");
  const message = document.getElementById("wishlistMessage");
  const money = (value) => new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(Number(value || 0));

  function showMessage(text) {
    message.textContent = text;
    message.hidden = !text;
  }

  function login() {
    window.location.href = "./Login.html?next=WishList.html";
  }

  function render(items) {
    content.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "commerce-empty";
      const title = document.createElement("h2");
      title.textContent = "Chưa có sản phẩm yêu thích";
      const shop = document.createElement("a");
      shop.className = "commerce-button";
      shop.href = "./Shop.html";
      shop.textContent = "Khám phá sản phẩm";
      empty.append(title, shop);
      content.append(empty);
      return;
    }

    for (const entry of items) {
      const row = document.createElement("article");
      row.className = "commerce-row";
      const info = document.createElement("div");
      const name = document.createElement("div");
      name.className = "commerce-product-name";
      name.textContent = entry.product_name || "Sản phẩm";
      const stock = document.createElement("div");
      stock.className = "commerce-product-meta";
      stock.textContent = entry.product_stock > 0 ? `Còn hàng: ${entry.product_stock}` : "Hết hàng";
      info.append(name, stock);
      const price = document.createElement("div");
      price.className = "commerce-price";
      price.textContent = money(entry.product_price);
      const actions = document.createElement("div");
      actions.className = "commerce-actions";
      const add = document.createElement("button");
      add.type = "button";
      add.className = "commerce-button";
      add.textContent = "Thêm vào giỏ";
      add.disabled = !(entry.product_stock > 0);
      add.addEventListener("click", async () => {
        try {
          await api.post("/cart/items", { product_id: entry.product_id, quantity: 1 });
          showMessage("Đã thêm sản phẩm vào giỏ hàng.");
        } catch (error) {
          if (error.status === 401) return login();
          showMessage(error.message);
        }
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "commerce-button link-button";
      remove.textContent = "Xóa";
      remove.addEventListener("click", async () => {
        try {
          await api.delete(`/wishlist/items/${entry.id}`);
          showMessage("");
          await load();
        } catch (error) {
          if (error.status === 401) return login();
          showMessage(error.message);
        }
      });
      actions.append(add, remove);
      row.append(info, price, actions);
      content.append(row);
    }
  }

  async function load() {
    if (!api.getToken()) return login();
    try {
      render(await api.get("/wishlist"));
    } catch (error) {
      if (error.status === 401) {
        api.clearToken();
        return login();
      }
      showMessage(error.message || "Không tải được danh sách yêu thích.");
    }
  }

  load();
})();
