/**
 * T1 Shop - Central Navigation, Auth & Cart Controller
 * Đồng bộ hóa toàn diện Routing, Trạng thái Đăng nhập, Giỏ hàng và Badge thông báo
 */
(function () {
  "use strict";

  const pages = {
    home: "./E-CommerceHomePage.html",
    homeWithAccount: "./AccountDropdownWithAccount.html",
    shop: "./Shop.html",
    wishlist: "./WishList.html",
    cart: "./Cart.html",
    checkout: "./Checkout.html",
    login: "./Login.html",
    signup: "./Sign-in.html",
    account: "./myAccount.html",
    about: "./About.html",
    contact: "./contact.html",
    details: "./ProductDetailsPage.html",
    error: "./error.html",
    management: "./Management.html"
  };

  // --- 1. AUTHENTICATION HELPERS ---
  function isLoggedIn() {
    try {
      return localStorage.getItem("t1shop-logged-in") === "true";
    } catch (_) {
      return false;
    }
  }

  function getLoggedInUser() {
    try {
      return JSON.parse(localStorage.getItem("t1shop-user") || "null");
    } catch (_) {
      return null;
    }
  }

  function setLogin(user) {
    try {
      localStorage.setItem("t1shop-logged-in", "true");
      if (user) {
        localStorage.setItem("t1shop-user", JSON.stringify(user));
      }
    } catch (_) {}
  }

  function logout() {
    try {
      localStorage.removeItem("t1shop-logged-in");
      localStorage.removeItem("t1shop-user");
    } catch (_) {}
    window.location.href = pages.login;
  }

  function requireLogin(onSuccess) {
    if (isLoggedIn()) {
      if (typeof onSuccess === "function") onSuccess();
      return true;
    }
    const isVi = document.documentElement.lang === "vi";
    alert(isVi ? "Vui lòng đăng nhập để thêm sản phẩm vào giỏ hàng!" : "Please log in to add products to your cart!");
    const currentUrl = window.location.href;
    try {
      sessionStorage.setItem("t1shop-return-url", currentUrl);
    } catch (_) {}
    window.location.href = pages.login;
    return false;
  }

  // --- 2. CART HELPERS ---
  function getCart() {
    try {
      return JSON.parse(localStorage.getItem("t1shop-cart") || "[]");
    } catch (_) {
      return [];
    }
  }

  function saveCart(cart) {
    try {
      localStorage.setItem("t1shop-cart", JSON.stringify(cart));
    } catch (_) {}
    updateCartBadges();
    window.dispatchEvent(new CustomEvent("t1shop:cart-updated", { detail: { cart: cart } }));
  }

  function addToCart(product) {
    if (!requireLogin()) return false;

    const cart = getCart();
    const prodId = String(product.id || product.name || Date.now());
    const existing = cart.find(function (item) {
      return (item.id && String(item.id) === prodId) || (item.name && item.name.trim() === product.name.trim());
    });

    const qtyToAdd = Math.max(1, Number(product.quantity) || 1);

    if (existing) {
      existing.quantity = (Number(existing.quantity) || 1) + qtyToAdd;
      if (product.price) existing.price = product.price;
      if (product.image) existing.image = product.image;
    } else {
      cart.push({
        id: prodId,
        name: (product.name || "T1 Shop Product").trim(),
        price: Number(product.price) || 120,
        image: product.image || "../assets/images/products/Frame 611.png",
        quantity: qtyToAdd,
        color: product.color || null,
        size: product.size || null
      });
    }

    saveCart(cart);
    showCartToast(product.name || "Sản phẩm");
    return true;
  }

  function showCartToast(name) {
    const isVi = document.documentElement.lang === "vi";
    let toast = document.getElementById("t1GlobalToast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "t1GlobalToast";
      toast.style.cssText =
        "position:fixed;bottom:24px;right:24px;background:#111;color:#fff;padding:12px 20px;border-radius:4px;box-shadow:0 4px 12px rgba(0,0,0,0.15);font-size:14px;z-index:99999;display:none;transition:all 0.3s ease;border-left:4px solid #db4444;";
      document.body.appendChild(toast);
    }
    toast.textContent = isVi ? `Đã thêm "${name}" vào giỏ hàng!` : `Added "${name}" to cart!`;
    toast.style.display = "block";
    toast.style.opacity = "1";
    setTimeout(function () {
      toast.style.opacity = "0";
      setTimeout(function () {
        toast.style.display = "none";
      }, 300);
    }, 2500);
  }

  // --- 3. BADGE SYNCHRONIZATION ---
  function updateCartBadges() {
    const cart = getCart();
    const count = cart.reduce(function (sum, item) {
      return sum + (Number(item.quantity) || 0);
    }, 0);

    // Tìm tất cả các link hoặc nút giỏ hàng trên trang
    const cartLinks = document.querySelectorAll('.cart-link, a[href*="Cart.html"], a[aria-label="Giỏ hàng"], a[aria-label="Cart"]');

    cartLinks.forEach(function (link) {
      let badge = link.querySelector(".cart-badge");
      if (count > 0) {
        if (!badge) {
          badge = document.createElement("span");
          badge.className = "cart-badge";
          link.appendChild(badge);
        }
        badge.textContent = count;
        badge.style.display = "inline-flex";
      } else {
        if (badge) {
          badge.style.display = "none";
          badge.textContent = "";
        }
      }
    });

    // Cập nhật cho mọi thẻ .cart-badge rời rạc (nếu có)
    document.querySelectorAll(".cart-badge").forEach(function (badge) {
      if (count > 0) {
        badge.textContent = count;
        badge.style.display = "inline-flex";
      } else {
        badge.style.display = "none";
        badge.textContent = "";
      }
    });
  }

  // --- 4. REPAIR ROUTING & LINKS ---
  function resolveRoute(href) {
    if (!href) return null;
    const value = href.trim();
    if (value === "#home") return pages.home;
    if (value === "#shop") return pages.shop;
    if (value === "#wishlist") return pages.wishlist;
    if (value === "#cart") return pages.cart;
    if (value === "#checkout" || value === "#buy-now") return pages.checkout;
    if (value === "#about") return pages.about;
    if (value === "#contact") return pages.contact;
    if (value === "#myAccount" || value === "#account") return pages.account;
    if (value === "#login") return pages.login;
    if (value === "#signup") return pages.signup;
    if (value.startsWith("/frontend/pages/")) {
      return "./" + value.split("/").pop();
    }
    return null;
  }

  function fixAllLinks() {
    document.querySelectorAll("a[href]").forEach(function (link) {
      const rawHref = link.getAttribute("href");
      const resolved = resolveRoute(rawHref);
      if (resolved) link.setAttribute("href", resolved);

      // Sửa các thẻ link trỏ tới "#" hoặc rỗng
      if (rawHref === "#" || rawHref === "" || rawHref === "#cart" || rawHref === "./WishList.html#cart") {
        const text = (link.textContent || "").trim().toLowerCase();
        const aria = (link.getAttribute("aria-label") || "").toLowerCase();

        if (text.includes("cart") || aria.includes("cart") || aria.includes("giỏ hàng") || rawHref === "#cart" || rawHref === "./WishList.html#cart") {
          link.setAttribute("href", pages.cart);
        } else if (text.includes("wishlist") || aria.includes("wishlist")) {
          link.setAttribute("href", pages.wishlist);
        } else if (text.includes("shop") || text.includes("cửa hàng")) {
          link.setAttribute("href", pages.shop);
        } else if (text.includes("account") || text.includes("tài khoản") || text.includes("my account")) {
          link.setAttribute("href", pages.account);
        } else if (text.includes("login") || text.includes("register") || text.includes("đăng nhập")) {
          link.setAttribute("href", pages.login);
        } else if (text === "contact" || text === "liên hệ") {
          link.setAttribute("href", pages.contact);
        } else if (text === "about" || text === "giới thiệu") {
          link.setAttribute("href", pages.about);
        }
      }

      // Xử lý nút Logout
      const linkText = (link.textContent || "").trim().toLowerCase();
      if (rawHref === "#logout" || linkText === "logout" || linkText === "đăng xuất") {
        link.addEventListener("click", function (e) {
          e.preventDefault();
          logout();
        });
      }
    });
  }

  // --- 5. GUEST VS LOGGED-IN DISPLAY ---
  function adjustUserAccountHeader() {
    const isUserLoggedIn = isLoggedIn();
    const currentPath = window.location.pathname.toLowerCase();
    const isGuestHome = currentPath.endsWith("e-commercehomepage.html") || currentPath.endsWith("/pages/") || currentPath.endsWith("index.html");

    // Trang E-CommerceHomePage.html: Nếu người dùng là khách vãng lai (chưa đăng nhập), ẩn avatar dropdown
    const userAccountDropdown = document.getElementById("userAccountDropdown");
    if (userAccountDropdown) {
      if (isGuestHome && !isUserLoggedIn) {
        userAccountDropdown.style.display = "none";
      } else {
        userAccountDropdown.style.display = "";
      }
    }
  }

  // --- 6. GLOBAL CLICK DISPATCHER ---
  document.addEventListener("click", function (event) {
    const target = event.target;
    if (!target.closest) return;

    // A. Nút Thêm vào giỏ hàng
    const addButton = target.closest(
      '[data-action="add-to-cart"], [data-action="add-cart"], .product-card__add-cart, .shop-card__add-cart, .card-add-cart-bar, .wishlist-add-cart-btn'
    );
    if (addButton) {
      event.preventDefault();
      event.stopPropagation();

      if (!requireLogin()) return;

      const card = addButton.closest(".wishlist-card, .shop-card, .product-card, .product-card-wrap");
      let name = "T1 Shop Product";
      let price = 120;
      let image = "../assets/images/products/Frame 611.png";
      let id = String(Date.now());

      if (card) {
        const titleEl = card.querySelector("h3, .product-card__name, .shop-card__name");
        if (titleEl) name = titleEl.textContent.trim();
        const priceEl = card.querySelector(".product-card__price, .shop-card__price, .price");
        if (priceEl) {
          const num = parseFloat(priceEl.textContent.replace(/[^0-9.]/g, ""));
          if (!isNaN(num) && num > 0) price = num;
        }
        const imgEl = card.querySelector("img");
        if (imgEl && imgEl.src) image = imgEl.src;
        if (card.getAttribute("data-id")) id = card.getAttribute("data-id");
      }

      addToCart({ id: id, name: name, price: price, image: image, quantity: 1 });
      return;
    }

    // B. Nút Mua ngay (Buy Now)
    const buyButton = target.closest("#btnBuyNow, [data-action='buy-now']");
    if (buyButton) {
      event.preventDefault();
      event.stopPropagation();

      if (!requireLogin()) return;

      // Đọc thông tin trên trang Product Details nếu có
      const titleEl = document.getElementById("productTitle") || document.querySelector(".details-info__title");
      const priceEl = document.getElementById("productPrice") || document.querySelector(".details-info__price");
      const qtyInput = document.getElementById("qtyInput") || document.querySelector(".details-qty__input");
      const imgEl = document.getElementById("mainProductImg") || document.querySelector(".details-gallery__main img");

      const name = titleEl ? titleEl.textContent.trim() : "Havic HV G-92 Gamepad";
      let price = 192;
      if (priceEl) {
        const num = parseFloat(priceEl.textContent.replace(/[^0-9.]/g, ""));
        if (!isNaN(num) && num > 0) price = num;
      }
      const qty = qtyInput ? Math.max(1, parseInt(qtyInput.value, 10) || 1) : 1;
      const image = imgEl ? imgEl.src : "../assets/images/products/Frame 611.png";

      addToCart({
        id: "gamepad-hv-g92",
        name: name,
        price: price,
        image: image,
        quantity: qty
      });

      // Chuyển hướng sang giỏ hàng / checkout
      window.location.href = pages.cart;
      return;
    }

    // C. Click Card Title / Thumbnail / Quickview -> Xem chi tiết sản phẩm
    const qvBtn = target.closest('[data-action="quickview"]');
    const cardTitle = target.closest(".product-card__name, .product-card h3");
    const cardThumb = target.closest(".product-card__thumb");

    if (qvBtn || cardTitle || (cardThumb && !target.closest("button"))) {
      const card = (qvBtn || cardTitle || cardThumb).closest(".product-card");
      if (card && !window.location.pathname.toLowerCase().endsWith("productdetailspage.html")) {
        event.preventDefault();
        const nameEl = card.querySelector("h3, .product-card__name");
        const priceEl = card.querySelector(".product-card__price, .price");
        const imgEl = card.querySelector("img");
        const name = nameEl ? nameEl.textContent.trim() : "T1 Shop Product";
        let price = "";
        if (priceEl) {
          const num = parseFloat(priceEl.textContent.replace(/[^0-9.]/g, ""));
          if (!isNaN(num)) price = num;
        }
        const img = imgEl ? (imgEl.getAttribute("src") || imgEl.src) : "";
        window.location.href = `${pages.details}?name=${encodeURIComponent(name)}&price=${price}&img=${encodeURIComponent(img)}`;
        return;
      }
    }
  });

  // Khởi chạy khi DOM sẵn sàng
  function init() {
    fixAllLinks();
    updateCartBadges();
    adjustUserAccountHeader();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Xuất API toàn cục để các trang có thể tương tác
  window.T1Shop = {
    pages: pages,
    isLoggedIn: isLoggedIn,
    getLoggedInUser: getLoggedInUser,
    setLogin: setLogin,
    logout: logout,
    requireLogin: requireLogin,
    getCart: getCart,
    saveCart: saveCart,
    addToCart: addToCart,
    updateCartBadges: updateCartBadges
  };
})();
