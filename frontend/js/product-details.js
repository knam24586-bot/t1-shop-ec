(function () {
  "use strict";

  const auth = window.T1ShopAuth;
  const productId = Number(new URLSearchParams(window.location.search).get("id"));
  const title = document.getElementById("productHeading");
  const price = document.querySelector(".product-price");
  const description = document.querySelector(".product-desc");
  const stockLabel = document.querySelector(".stock-status");
  const image = document.getElementById("mainProductImg");
  const buyButton = document.getElementById("btnBuyNow");
  const quantityLabel = document.getElementById("qtyValue");
  const money = (amount) => new Intl.NumberFormat("vi-VN", {style:"currency",currency:"VND"}).format(Number(amount)||0);
  let product = null;
  let variant = null;

  if (buyButton && !productId) {
    buyButton.disabled = true;
    buyButton.title = "Mở sản phẩm từ trang cửa hàng để chọn đúng sản phẩm cần mua.";
  }

  async function loadProduct() {
    if (!productId || !auth) return;
    try {
      const response = await auth.fetch("/products/" + productId);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || data.detail || "Không tìm thấy sản phẩm.");
      product = data;
      variant = (data.variants || []).find((item) => Number(item.stock) > 0) || null;
      if (title) title.textContent = data.name;
      if (price) price.textContent = money(data.price);
      if (description) description.textContent = data.description || "Sản phẩm chính hãng từ T1 Shop.";
      if (stockLabel) stockLabel.textContent = variant ? `Còn ${variant.stock} sản phẩm` : "Hết hàng";
      if (image && data.image_url) image.src = data.image_url;
      if (buyButton) buyButton.disabled = !variant;
    } catch (error) {
      if (stockLabel) stockLabel.textContent = error.message;
      if (buyButton) buyButton.disabled = true;
    }
  }

  window.addCurrentDetailsProductToCart = async function (quantity) {
    if (!product || !variant) return;
    if (!auth.getAccessToken()) {
      window.location.assign("./Login.html?auth=required");
      return;
    }
    try {
      const response = await auth.fetch("/cart/items", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({variant_id: variant.id, quantity: Math.max(1, Number(quantity) || 1)})
      });
      const result=await response.json();
      if(!response.ok) throw new Error(result.error?.message || result.detail || "Không thể thêm vào giỏ hàng.");
      window.location.assign("./Cart.html");
    } catch(error) {
      window.alert(error.message || "Không kết nối được với giỏ hàng.");
    }
  };

  loadProduct();
})();
