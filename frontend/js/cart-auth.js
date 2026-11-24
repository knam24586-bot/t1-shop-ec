/**
 * T1 Shop - Global Cart & Authentication Manager
 *
 * Chức năng:
 * 1. Quản lý trạng thái Đăng nhập (Authentication State).
 * 2. Ngăn chặn người dùng chưa đăng nhập thêm hàng vào giỏ (Yêu cầu đăng nhập).
 * 3. Quản lý số lượng Giỏ hàng và tự động cập nhật Huy hiệu (Cart Badge):
 *    - Khi giỏ hàng = 0: Không hiển thị số (ẩn hoàn toàn badge).
 *    - Khi có sản phẩm (> 0): Hiển thị số lượng chính xác trên giỏ hàng.
 * 4. Đồng bộ giỏ hàng theo thời gian thực giữa các trang và các tab trình duyệt.
 */

(function (window, document) {
  "use strict";

  // Các khóa lưu trữ trong LocalStorage
  var STORAGE_KEYS = {
    AUTH: "t1_user_logged_in",
    USER: "t1_current_user",
    CART: "t1_cart_items",
    LANG: "t1shop_lang",
    LANG_FALLBACK: "t1_selected_lang"
  };

  /**
   * Xác định đường dẫn tương đối đến trang Login tùy theo vị trí file hiện tại
   */
  function getLoginPath() {
    var path = window.location.pathname.replace(/\\/g, "/");
    if (path.indexOf("/pages/") !== -1 || path.indexOf("/frontend/pages/") !== -1) {
      return "./Login.html";
    }
    return "./frontend/pages/Login.html";
  }

  /**
   * Xác định đường dẫn tương đối đến trang Cart tùy theo vị trí file hiện tại
   */
  function getCartPath() {
    var path = window.location.pathname.replace(/\\/g, "/");
    if (path.indexOf("/pages/") !== -1 || path.indexOf("/frontend/pages/") !== -1) {
      return "./cart.html";
    }
    return "./frontend/pages/cart.html";
  }

  /**
   * Xác định đường dẫn tương đối đến trang Error 404 tùy theo vị trí file hiện tại
   */
  function getErrorPath() {
    var path = window.location.pathname.replace(/\\/g, "/");
    if (path.indexOf("/pages/") !== -1 || path.indexOf("/frontend/pages/") !== -1) {
      return "./error.html";
    }
    return "./frontend/pages/error.html";
  }

  /**
   * Lấy ngôn ngữ hiện tại của website ('vi' hoặc 'en')
   */
  function getCurrentLang() {
    return document.documentElement.lang ||
      localStorage.getItem(STORAGE_KEYS.LANG) ||
      localStorage.getItem(STORAGE_KEYS.LANG_FALLBACK) ||
      "en";
  }

  /**
   * Hiển thị thông báo Toast nổi trên màn hình
   */
  function showToast(message, type) {
    var existingToast = document.getElementById("t1GlobalToast");
    if (existingToast) {
      existingToast.remove();
    }

    var toast = document.createElement("div");
    toast.id = "t1GlobalToast";
    var isWarning = type === "warning" || type === "error";
    var bgColor = isWarning ? "#db4444" : "#000000";
    var icon = isWarning ? "⚠️" : "🛒";

    toast.style.cssText =
      "position: fixed; bottom: 30px; right: 30px; z-index: 99999; " +
      "background: " + bgColor + "; color: #ffffff; padding: 14px 22px; " +
      "border-radius: 6px; box-shadow: 0 8px 24px rgba(0,0,0,0.25); " +
      "font-family: 'Poppins', sans-serif; font-size: 14px; font-weight: 500; " +
      "display: flex; align-items: center; gap: 10px; opacity: 0; " +
      "transform: translateY(20px); transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); cursor: default;";

    if (type === "success") {
      var isVi = getCurrentLang() === "vi";
      toast.style.cursor = "pointer";
      toast.title = isVi ? "Bấm để xem giỏ hàng" : "Click to view cart";
      var viewCartText = isVi ? "Xem giỏ hàng →" : "View Cart →";
      toast.innerHTML =
        "<span>" + icon + "</span>" +
        "<span>" + message + "</span>" +
        "<span style='text-decoration: underline; margin-left: 8px; font-weight: 600; font-size: 13px; color: #db4444;'>" + viewCartText + "</span>";
      toast.onclick = function () {
        window.location.href = getCartPath();
      };
    } else {
      toast.innerHTML = "<span>" + icon + "</span><span>" + message + "</span>";
    }

    document.body.appendChild(toast);

    // Kích hoạt animation hiện ra
    setTimeout(function () {
      toast.style.opacity = "1";
      toast.style.transform = "translateY(0)";
    }, 20);

    // Tự động ẩn sau 3.2 giây
    setTimeout(function () {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(20px)";
      setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 350);
    }, 3200);
  }

  /* ========================================================
     1. MODULE XÁC THỰC (AUTHENTICATION)
     ======================================================== */
  var T1Auth = {
    /**
     * Kiểm tra người dùng đã đăng nhập chưa
     * @returns {boolean}
     */
    isLoggedIn: function () {
      return localStorage.getItem(STORAGE_KEYS.AUTH) === "true";
    },

    /**
     * Lấy thông tin tài khoản hiện tại
     */
    getUser: function () {
      try {
        var data = localStorage.getItem(STORAGE_KEYS.USER);
        return data ? JSON.parse(data) : null;
      } catch (e) {
        return null;
      }
    },

    /**
     * Đăng nhập người dùng
     */
    login: function (userData) {
      localStorage.setItem(STORAGE_KEYS.AUTH, "true");
      if (userData) {
        localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(userData));
      }
      this.dispatchChange();
    },

    /**
     * Đăng xuất người dùng
     */
    logout: function () {
      localStorage.removeItem(STORAGE_KEYS.AUTH);
      localStorage.removeItem(STORAGE_KEYS.USER);
      this.dispatchChange();
    },

    /**
     * Kiểm tra quyền thêm vào giỏ hàng:
     * Nếu CHƯA đăng nhập -> chặn và thông báo / chuyển hướng sang Login.html
     * @returns {boolean}
     */
    requireLogin: function () {
      if (this.isLoggedIn()) {
        return true;
      }

      var isVi = getCurrentLang() === "vi";
      var msg = isVi
        ? "Bạn cần đăng nhập để thêm sản phẩm vào giỏ hàng!"
        : "Please log in to add products to your cart!";

      showToast(msg, "warning");

      // Hỏi chuyển hướng hoặc tự động chuyển hướng sau 1.2 giây
      setTimeout(function () {
        if (confirm(isVi ? msg + "\nBạn có muốn chuyển đến trang Đăng nhập ngay bây giờ không?" : msg + "\nDo you want to go to the Login page now?")) {
          window.location.href = getLoginPath();
        }
      }, 300);

      return false;
    },

    dispatchChange: function () {
      var evt;
      try {
        evt = new CustomEvent("t1:auth-change", { detail: { loggedIn: this.isLoggedIn() } });
      } catch (e) {
        evt = document.createEvent("CustomEvent");
        evt.initCustomEvent("t1:auth-change", true, true, { loggedIn: this.isLoggedIn() });
      }
      window.dispatchEvent(evt);
    }
  };

  /* ========================================================
     2. MODULE GIỎ HÀNG (SHOPPING CART)
     ======================================================== */
  var T1Cart = {
    /**
     * Lấy danh sách sản phẩm trong giỏ hàng từ localStorage
     * @returns {Array}
     */
    getItems: function () {
      try {
        var raw = localStorage.getItem(STORAGE_KEYS.CART);
        return raw ? JSON.parse(raw) : [];
      } catch (e) {
        return [];
      }
    },

    /**
     * Tính tổng số lượng sản phẩm trong giỏ hàng
     * @returns {number}
     */
    getCount: function () {
      var items = this.getItems();
      var total = 0;
      for (var i = 0; i < items.length; i++) {
        total += (parseInt(items[i].qty, 10) || 1);
      }
      return total;
    },

    /**
     * Thêm sản phẩm vào giỏ hàng (Chỉ thực hiện khi ĐÃ ĐĂNG NHẬP)
     * @param {Object} product { id, name, price, qty, image }
     * @returns {boolean}
     */
    addItem: function (product) {
      // 1. Kiểm tra đăng nhập
      if (!T1Auth.requireLogin()) {
        return false;
      }

      if (!product || !product.name) {
        product = { name: "Product", qty: 1 };
      }

      var items = this.getItems();
      var qtyToAdd = parseInt(product.qty, 10) || 1;
      var found = false;

      for (var i = 0; i < items.length; i++) {
        if (items[i].id && product.id && items[i].id === product.id) {
          items[i].qty = (parseInt(items[i].qty, 10) || 1) + qtyToAdd;
          found = true;
          break;
        } else if (items[i].name && product.name && items[i].name.toLowerCase() === product.name.toLowerCase()) {
          items[i].qty = (parseInt(items[i].qty, 10) || 1) + qtyToAdd;
          found = true;
          break;
        }
      }

      if (!found) {
        items.push({
          id: product.id || ("prod-" + Date.now()),
          name: product.name,
          price: product.price || "$0",
          qty: qtyToAdd,
          image: product.image || ""
        });
      }

      try {
        localStorage.setItem(STORAGE_KEYS.CART, JSON.stringify(items));
      } catch (e) { }

      // Cập nhật số hiển thị trên biểu tượng giỏ hàng ngay lập tức
      this.updateBadge();

      // Thông báo thành công
      var isVi = getCurrentLang() === "vi";
      var successMsg = isVi
        ? 'Đã thêm "' + product.name + '" vào giỏ hàng!'
        : 'Added "' + product.name + '" to cart!';
      showToast(successMsg, "success");

      // Bắn sự kiện
      this.dispatchChange();
      return true;
    },

    /**
     * Xóa toàn bộ giỏ hàng
     */
    clearCart: function () {
      localStorage.removeItem(STORAGE_KEYS.CART);
      this.updateBadge();
      this.dispatchChange();
    },

    /**
     * Cập nhật Huy hiệu Giỏ hàng (Cart Badge) trên Header:
     * - Khi count === 0: Ẩn hoàn toàn, KHÔNG hiển thị số.
     * - Khi count > 0: Hiển thị chấm tròn đỏ với số lượng chính xác.
     */
    updateBadge: function () {
      var count = this.getCount();

      // Tìm tất cả các link hoặc biểu tượng giỏ hàng
      var cartLinks = document.querySelectorAll(".cart-link, a[href*='cart'], a.icon-link[aria-label*='Giỏ hàng'], a.icon-link[aria-label*='Cart']");
      var existingBadges = document.querySelectorAll(".cart-badge");

      if (count <= 0) {
        // GIỎ HÀNG TRỐNG: ẨN TOÀN BỘ SỐ VÀ HUY HIỆU
        existingBadges.forEach(function (badge) {
          badge.style.display = "none";
          badge.textContent = "";
          badge.classList.add("cart-badge--hidden");
          badge.setAttribute("data-count", "0");
        });
      } else {
        // CÓ SẢN PHẨM TRONG GIỎ: HIỂN THỊ SỐ CHÍNH XÁC
        var displayCount = count > 99 ? "99+" : String(count);

        if (existingBadges.length > 0) {
          existingBadges.forEach(function (badge) {
            badge.style.display = "flex";
            badge.textContent = displayCount;
            badge.classList.remove("cart-badge--hidden");
            badge.setAttribute("data-count", String(count));
          });
        }

        // Đảm bảo mỗi cart link đều có badge hiển thị
        cartLinks.forEach(function (link) {
          // Bỏ qua các link trong footer
          if (link.closest(".site-footer") || link.closest(".auth-footer")) return;

          link.style.position = "relative";
          var badge = link.querySelector(".cart-badge");
          if (!badge) {
            badge = document.createElement("span");
            badge.className = "cart-badge";
            link.appendChild(badge);
          }
          badge.style.display = "flex";
          badge.textContent = displayCount;
          badge.classList.remove("cart-badge--hidden");
          badge.setAttribute("data-count", String(count));
        });
      }
    },

    dispatchChange: function () {
      var evt;
      try {
        evt = new CustomEvent("t1:cart-change", { detail: { count: this.getCount() } });
      } catch (e) {
        evt = document.createEvent("CustomEvent");
        evt.initCustomEvent("t1:cart-change", true, true, { count: this.getCount() });
      }
      window.dispatchEvent(evt);
    }
  };

  /* ========================================================
     3. TỰ ĐỘNG BẮT SỰ KIỆN CLICK TOÀN CỤC (EVENT DELEGATION)
     ======================================================== */
  function initGlobalCartListeners() {
    // 1. Cập nhật Badge ngay khi tải trang
    T1Cart.updateBadge();

    // 2. Lắng nghe thay đổi từ các tab khác
    window.addEventListener("storage", function (e) {
      if (e.key === STORAGE_KEYS.CART) {
        T1Cart.updateBadge();
      }
    });

    // 3. Bắt sự kiện bấm nút Logout để cập nhật trạng thái
    document.addEventListener("click", function (e) {
      var logoutLink = e.target.closest("a[href*='Login.html'], a[data-action='logout']");
      if (logoutLink) {
        var text = (logoutLink.textContent || "").toLowerCase();
        if (text.indexOf("logout") !== -1 || text.indexOf("đăng xuất") !== -1) {
          T1Auth.logout();
        }
      }
    });

    // 4. Bắt sự kiện trên các nút Thêm vào giỏ hàng
    document.addEventListener("click", function (e) {
      // Nhận diện các loại nút thêm vào giỏ hàng trên khắp hệ thống
      var addBtn = e.target.closest(
        ".product-card__add-cart, .shop-card__add-cart, .wishlist-add-cart-btn, " +
        ".card-add-cart-bar, #btnBuyNow, #modalAddCartBtn, " +
        "[data-action='add-cart'], [data-action='add-to-cart'], #moveAllBtn"
      );

      if (!addBtn) return;

      // KIỂM TRA ĐĂNG NHẬP TRƯỚC TIÊN
      if (!T1Auth.requireLogin()) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        return false;
      }

      // NẾU ĐÃ ĐĂNG NHẬP: Lấy thông tin sản phẩm và thêm vào giỏ
      e.preventDefault();
      e.stopPropagation();

      // Trường hợp nút Move All To Bag trên Wishlist
      if (addBtn.id === "moveAllBtn") {
        var countMoved = document.querySelectorAll(".wishlist-card").length || 4;
        for (var k = 0; k < countMoved; k++) {
          T1Cart.addItem({ name: "Wishlist Item " + (k + 1), qty: 1 });
        }
        var isVi = getCurrentLang() === "vi";
        showToast(isVi ? "Đã chuyển tất cả sản phẩm vào giỏ hàng!" : "Moved all items to bag!", "success");
        return;
      }

      // Trường hợp nút Buy Now trên trang Chi tiết sản phẩm
      if (addBtn.id === "btnBuyNow") {
        var prodTitle = document.getElementById("productHeading");
        var qtyEl = document.getElementById("qtyValue");
        var pName = prodTitle ? prodTitle.textContent.trim() : "Havic HV G-92 Gamepad";
        var pQty = qtyEl ? (parseInt(qtyEl.textContent, 10) || 1) : 1;
        var pPrice = "$192.00";
        var priceEl = document.querySelector(".product-price");
        if (priceEl) pPrice = priceEl.textContent.trim();

        T1Cart.addItem({ name: pName, price: pPrice, qty: pQty });
        return;
      }

      // Trường hợp nút trong Modal Quick-view
      if (addBtn.id === "modalAddCartBtn") {
        var modalTitle = document.getElementById("modalTitle") || document.querySelector(".product-modal__title");
        var modalQty = document.getElementById("modalQtyInput") || document.querySelector(".product-modal__qty-input");
        var mName = modalTitle ? modalTitle.textContent.trim() : "Sản phẩm";
        var mQty = modalQty ? (parseInt(modalQty.value, 10) || 1) : 1;
        T1Cart.addItem({ name: mName, qty: mQty });
        return;
      }

      // Trường hợp các Product Card thông thường
      var card = addBtn.closest(".product-card, .shop-card, .wishlist-card, article");
      var name = "Product";
      var price = "$0";
      var img = "";

      if (card) {
        var nameEl = card.querySelector(".product-card__name, .shop-card__title, .wishlist-card__name, .wishlist-card__title, h3, h2");
        if (nameEl && nameEl.textContent.trim()) {
          name = nameEl.textContent.trim();
        } else if (card.getAttribute("data-product-name")) {
          name = card.getAttribute("data-product-name");
        }

        var priceEl = card.querySelector(".product-card__current-price, .product-card__price, .shop-card__price, .wishlist-card__price, .price");
        if (priceEl) price = priceEl.textContent.trim();

        var imgEl = card.querySelector("img");
        if (imgEl) img = imgEl.src;
      }

      T1Cart.addItem({ name: name, price: price, qty: 1, image: img });
    }, true); // Use capture to intercept before any other inline listeners

    // 5. Bắt sự kiện click vào icon Giỏ hàng ở Header -> Chuyển đến trang cart.html
    document.addEventListener("click", function (e) {
      var cartLink = e.target.closest(".cart-link, a.icon-link[aria-label*='Giỏ hàng'], a.icon-link[aria-label*='Cart']");
      if (cartLink && !cartLink.closest(".site-footer") && !cartLink.closest(".auth-footer")) {
        var path = window.location.pathname.replace(/\\/g, "/");
        if (path.indexOf("cart.html") === -1) {
          e.preventDefault();
          window.location.href = getCartPath();
        }
      }
    });

    // 6. Bắt sự kiện click vào các liên kết placeholder (#, #privacy, #terms, #faq, #my-order, v.v.)
    // -> Tự động chuyển đến trang 404 error.html
    document.addEventListener("click", function (e) {
      var link = e.target.closest("a");
      if (!link) return;
      var href = (link.getAttribute("href") || "").trim();

      // Bỏ qua các liên kết chức năng hợp lệ
      if (!href || href === "#cart" || href.startsWith("javascript:") || href.startsWith("mailto:") || href.startsWith("tel:")) {
        return;
      }

      // Nếu bấm vào các liên kết chưa phát triển hoặc placeholder
      var isPlaceholder = (
        href === "#" ||
        href === "#privacy" ||
        href === "#terms" ||
        href === "#faq" ||
        href === "#my-order" ||
        href === "#my-cancellations" ||
        href === "#my-reviews" ||
        href === "#subscribe" ||
        href === "#wishlist" ||
        href === "#account"
      );

      if (isPlaceholder) {
        var currentPath = window.location.pathname.replace(/\\/g, "/");
        if (currentPath.indexOf("error.html") === -1) {
          e.preventDefault();
          window.location.href = getErrorPath();
        }
      }
    });

    // 7. Hỗ trợ toàn cục mở/đóng Menu điều hướng trên Tablet & Mobile (Menu Toggle)
    document.addEventListener("click", function (e) {
      var toggleBtn = e.target.closest(".menu-toggle");
      var nav = document.getElementById("primary-navigation") || document.querySelector(".navigation");

      if (toggleBtn) {
        e.preventDefault();
        e.stopPropagation();
        if (nav) {
          var isOpen = nav.classList.toggle("navigation--open");
          toggleBtn.setAttribute("aria-expanded", String(isOpen));
          toggleBtn.setAttribute("aria-label", isOpen ? "Đóng menu" : "Mở menu");
        }
        return;
      }

      // Đóng menu khi bấm ra ngoài
      if (nav && nav.classList.contains("navigation--open")) {
        if (!nav.contains(e.target)) {
          nav.classList.remove("navigation--open");
          var allToggles = document.querySelectorAll(".menu-toggle");
          allToggles.forEach(function (btn) {
            btn.setAttribute("aria-expanded", "false");
            btn.setAttribute("aria-label", "Mở menu");
          });
        }
      }
    });
  }

  // Khởi động khi DOM sẵn sàng
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initGlobalCartListeners);
  } else {
    initGlobalCartListeners();
  }

  // Export ra window để các file script khác có thể gọi trực tiếp
  window.T1Auth = T1Auth;
  window.T1Cart = T1Cart;

})(window, document);
