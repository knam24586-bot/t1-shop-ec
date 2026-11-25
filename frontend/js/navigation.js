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

  const apiBase = window.T1_API_BASE || "http://127.0.0.1:8000/api";
  const tokenKey = "t1shop-access-token";
  const userKey = "t1shop-auth-user";

  function clearSession() {
    try {
      sessionStorage.removeItem(tokenKey);
      sessionStorage.removeItem(userKey);
    } catch (_) { }
  }

  function getStoredUser() {
    try { return JSON.parse(sessionStorage.getItem(userKey) || "null"); }
    catch (_) { return null; }
  }

  function getAccessToken() {
    try {
      const token = sessionStorage.getItem(tokenKey);
      if (!token) return null;
      const payload = token.split(".")[1];
      if (!payload) {
        clearSession();
        return null;
      }
      const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
      const claims = JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "=")));
      if (!claims.exp || Date.now() >= Number(claims.exp) * 1000) {
        clearSession();
        return null;
      }
      return token;
    } catch (_) {
      clearSession();
      return null;
    }
  }

  async function apiFetch(path, options) {
    const requestOptions = Object.assign({}, options || {});
    const headers = new Headers(requestOptions.headers || {});
    const token = getAccessToken();
    if (token) headers.set("Authorization", "Bearer " + token);
    requestOptions.headers = headers;
    const url = /^https?:\/\//i.test(path) ? path : apiBase + (path.startsWith("/") ? path : "/" + path);
    const response = await fetch(url, requestOptions);
    if (response.status === 401 && !/\/auth\/(login|register)$/.test(path)) {
      clearSession();
      window.dispatchEvent(new CustomEvent("t1shop:session-expired"));
    }
    return response;
  }

  async function requireAuth(options) {
    const opts = options || {};
    const hadSession = Boolean(sessionStorage.getItem(tokenKey) || sessionStorage.getItem(userKey));
    const token = getAccessToken();
    if (!token) {
      clearSession();
      window.location.assign(pages.login + (hadSession ? "?expired=1" : "?auth=required"));
      return null;
    }

    try {
      const response = await apiFetch("/auth/me");
      if (!response.ok) {
        clearSession();
        window.location.assign(pages.login + "?expired=1");
        return null;
      }
      const user = await response.json();
      sessionStorage.setItem(userKey, JSON.stringify(user));

      if (Array.isArray(opts.allowedRoles) && opts.allowedRoles.length) {
        const userRole = String(user.role || "").trim().toUpperCase();
        const allowed = opts.allowedRoles.map(function (r) { return String(r).trim().toUpperCase(); });
        if (!allowed.includes(userRole)) {
          return { authorized: false, user: user };
        }
      }
      return { authorized: true, user: user };
    } catch (_) {
      const cached = getStoredUser();
      if (cached) return { authorized: true, user: cached, offline: true };
      return null;
    }
  }

  window.T1ShopAuth = {
    apiBase: apiBase,
    getAccessToken: getAccessToken,
    getUser: getStoredUser,
    saveSession: function (token, user) {
      sessionStorage.setItem(tokenKey, token);
      sessionStorage.setItem(userKey, JSON.stringify(user));
    },
    clearSession: clearSession,
    fetch: apiFetch,
    requireAuth: requireAuth
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

  document.querySelectorAll("a").forEach(function (link) {
    const label = (link.textContent || "").trim().toLowerCase();
    if (label !== "logout" && label !== "log out" && label !== "đăng xuất") return;
    link.addEventListener("click", async function (event) {
      event.preventDefault();
      const token = getAccessToken();
      if (token) {
        try {
          await apiFetch("/auth/logout", { method: "POST" });
        } catch (_) { }
      }
      clearSession();
      window.location.assign(pages.login + "?logged_out=1");
    });
  });

  function setCartBadges(count) {
    document.querySelectorAll(".cart-badge").forEach(function (badge) {
      badge.textContent = count;
      badge.style.display = count > 0 ? "inline-flex" : "none";
    });
  }

  window.T1ShopAuth.refreshCartBadge = async function () {
    if (!getAccessToken()) { setCartBadges(0); return; }
    try {
      const response = await apiFetch("/cart");
      if (!response.ok) { setCartBadges(0); return; }
      const cart = await response.json();
      setCartBadges(Number(cart.total_items) || 0);
    } catch (_) { setCartBadges(0); }
  };
  window.T1ShopAuth.refreshCartBadge();
})();
