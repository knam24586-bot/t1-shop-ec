(function () {
  "use strict";

  const pages = {
    home: "./E-CommerceHomePage.html",
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

  function resolveRoute(href) {
    if (!href) return null;
    const value = href.trim();
    if (value === "#home") return pages.home;
    if (value === "#shop" || value === "#buy-now") return value === "#buy-now" ? pages.checkout : pages.shop;
    if (value === "#wishlist") return pages.wishlist;
    if (value === "#cart" || value === "#checkout") return value === "#checkout" ? pages.checkout : pages.cart;
    if (value === "#about") return pages.about;
    if (value === "#contact") return pages.contact;
    return null;
  }

  document.querySelectorAll("a[href]").forEach(function (link) {
    const route = resolveRoute(link.getAttribute("href"));
    if (route) link.setAttribute("href", route);

    if (link.getAttribute("href") === "#" || link.getAttribute("href") === "") {
      const text = (link.textContent || "").trim().toLowerCase();
      if (text.includes("cart")) link.setAttribute("href", pages.cart);
      else if (text.includes("wishlist")) link.setAttribute("href", pages.wishlist);
      else if (text.includes("shop")) link.setAttribute("href", pages.shop);
      else if (text.includes("account") || text.includes("profile")) link.setAttribute("href", pages.account);
      else if (text.includes("login") || text.includes("register")) link.setAttribute("href", pages.login);
      else if (text === "contact") link.setAttribute("href", pages.contact);
      else if (text === "about") link.setAttribute("href", pages.about);
    }
  });

  function getCart() {
    try {
      return JSON.parse(localStorage.getItem("t1shop-cart") || "[]");
    } catch (_) {
      return [];
    }
  }

  function saveCart(cart) {
    localStorage.setItem("t1shop-cart", JSON.stringify(cart));
  }

  function updateCartBadges() {
    const count = getCart().reduce(function (sum, item) { return sum + (Number(item.quantity) || 0); }, 0);
    document.querySelectorAll(".cart-badge").forEach(function (badge) {
      badge.textContent = count;
      badge.style.display = count > 0 ? "inline-flex" : "none";
    });
  }

  document.addEventListener("click", function (event) {
    const target = event.target;
    if (!target.closest) return;

    const addButton = target.closest('[data-action="add-to-cart"], [data-action="add-cart"], .wishlist-add-cart-btn, .card-add-cart-bar');
    if (addButton) {
      const card = addButton.closest(".wishlist-card, .shop-card, .product-card");
      const name = card
        ? (card.getAttribute("data-product-name") || card.querySelector("h3")?.textContent || "T1 Shop Product")
        : "T1 Shop Product";
      const cart = getCart();
      const existing = cart.find(function (item) { return item.name === name.trim(); });
      if (existing) existing.quantity += 1;
      else cart.push({ id: String(Date.now()), name: name.trim(), price: 960, quantity: 1 });
      saveCart(cart);
      updateCartBadges();
    }

    const buyButton = target.closest("#btnBuyNow, .promo-btn, [data-action='buy-now']");
    if (buyButton) {
      window.location.href = pages.checkout;
    }
  });

  updateCartBadges();
})();
