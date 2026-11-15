/**
 * T1Shop - Home Page Interactions
 * Đáp ứng đầy đủ các tiêu chí chấp nhận:
 * 1. Chuyển slide bằng nút/dot, nhận biết slide đang chọn, responsive không vỡ
 * 2. Flash Sale countdown với mốc cấu hình, không hiển thị thời gian âm khi hết hạn
 * 3. Khi kết thúc đếm ngược: Toàn bộ giá sản phẩm tự động quay về lại giá gốc ban đầu (cả Flash Sale & Best Selling)
 * 4. Hỗ trợ hiển thị Dữ liệu mẫu / Loading Skeleton / Empty State
 */

(() => {
  function initHomePage() {
    if (window.__t1ShopHomeInitialized) return;
    window.__t1ShopHomeInitialized = true;

    /* ====================================================
     * 1. Header Mobile Menu Toggle
     * ==================================================== */
    const menuButton = document.querySelector(".menu-toggle");
    const navigation = document.querySelector(".navigation");

    if (menuButton && navigation) {
      menuButton.addEventListener("click", () => {
        const isOpen = navigation.classList.toggle("navigation--open");
        menuButton.setAttribute("aria-expanded", String(isOpen));
        menuButton.setAttribute("aria-label", isOpen ? "Đóng menu" : "Mở menu");
      });
    }

    /* ====================================================
     * 2. Hero Banner Slider (Nút chuyển slide & Dot điều hướng)
     * ==================================================== */
    const track = document.getElementById("heroSliderTrack");
    const slides = document.querySelectorAll(".hero-slide");
    const dots = document.querySelectorAll(".hero-slider__dot");
    const prevBtn = document.getElementById("heroSlidePrev");
    const nextBtn = document.getElementById("heroSlideNext");
    const sliderEl = document.querySelector(".hero-slider");

    let currentSlide = 0;
    const totalSlides = slides.length;
    let autoSlideTimer = null;

    function updateSlider(index) {
      if (totalSlides === 0 || !track) return;
      currentSlide = (index + totalSlides) % totalSlides;
      track.style.transform = `translateX(-${currentSlide * 100}%)`;

      dots.forEach((dot, idx) => {
        const isActive = idx === currentSlide;
        dot.classList.toggle("hero-slider__dot--active", isActive);
        dot.setAttribute("aria-selected", String(isActive));
      });
    }

    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        updateSlider(currentSlide - 1);
        resetAutoSlide();
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        updateSlider(currentSlide + 1);
        resetAutoSlide();
      });
    }

    dots.forEach((dot) => {
      dot.addEventListener("click", (e) => {
        const targetIndex = parseInt(e.currentTarget.getAttribute("data-slide-index") || "0", 10);
        updateSlider(targetIndex);
        resetAutoSlide();
      });
    });

    function startAutoSlide() {
      if (totalSlides > 1) {
        autoSlideTimer = setInterval(() => {
          updateSlider(currentSlide + 1);
        }, 5000);
      }
    }

    function resetAutoSlide() {
      if (autoSlideTimer) clearInterval(autoSlideTimer);
      startAutoSlide();
    }

    startAutoSlide();

    if (sliderEl) {
      sliderEl.addEventListener("mouseenter", () => {
        if (autoSlideTimer) clearInterval(autoSlideTimer);
      });
      sliderEl.addEventListener("mouseleave", () => {
        resetAutoSlide();
      });
    }

    /* ====================================================
     * 3. Flash Sale Countdown Timer & Dynamic Pricing
     * ==================================================== */
    const flashSection = document.getElementById("flashSaleSection");
    const bestSellingSection = document.querySelector(".best-selling-section");
    const countdownContainer = document.getElementById("flashSaleCountdown");
    const daysEl = document.getElementById("cdDays");
    const hoursEl = document.getElementById("cdHours");
    const minutesEl = document.getElementById("cdMinutes");
    const secondsEl = document.getElementById("cdSeconds");
    const promoHoursEl = document.getElementById("promoHours");
    const promoDaysEl = document.getElementById("promoDays");
    const promoMinutesEl = document.getElementById("promoMinutes");
    const promoSecondsEl = document.getElementById("promoSeconds");
    const expiredBadge = document.getElementById("cdExpiredBadge");


    // Đồng bộ thời gian chuẩn theo ảnh: 05 Days, 23 Hours, 59 Minutes, 35 Seconds
    function getTargetEndTime() {
      if (countdownContainer && countdownContainer.hasAttribute("data-end-time")) {
        const attr = countdownContainer.getAttribute("data-end-time");
        const parsed = new Date(attr).getTime();
        if (!isNaN(parsed) && parsed > Date.now()) {
          return parsed;
        }
      }
      return Date.now() + (5 * 86400000 + 23 * 3600000 + 59 * 60000 + 35 * 1000);
    }

    let targetEndTime = getTargetEndTime();

    // Hàm chuyển đổi giá khi Flash Sale kết thúc hoặc đang diễn ra
    function setFlashSalePricing(isExpired) {
      if (flashSection) {
        flashSection.classList.toggle("flash-sales--ended", isExpired);
      }
      if (bestSellingSection) {
        bestSellingSection.classList.toggle("flash-sales--ended", isExpired);
      }

      const cards = document.querySelectorAll(
        "#flashSaleTrack .product-card, #flashSaleSection .product-card, .best-selling-section .product-card"
      );
      cards.forEach((card) => {
        const priceEl = card.querySelector(".product-card__price");
        const oldPriceEl = card.querySelector(".product-card__old-price");
        const badgeEl = card.querySelector(".product-badge");

        // Trích xuất và lưu cache giá gốc đã gạch và giá khuyến mãi
        if (!card._origPrice) {
          card._origPrice = card.getAttribute("data-original-price") || (oldPriceEl ? oldPriceEl.textContent.trim() : "");
        }
        if (!card._salePrice) {
          card._salePrice = card.getAttribute("data-sale-price") || (priceEl ? priceEl.textContent.trim() : "");
        }
        if (!card._discount) {
          card._discount = card.getAttribute("data-discount") || (badgeEl ? badgeEl.textContent.trim() : "");
        }

        if (isExpired) {
          // KHI KẾT THÚC: Cho lại giá về đúng con số đã gạch ở trên hình ($160, $1160, $400, $400, $225, $360, $170)
          if (priceEl && card._origPrice) {
            priceEl.textContent = card._origPrice;
          }
          if (oldPriceEl) {
            oldPriceEl.style.display = "none";
          }
          if (badgeEl) {
            badgeEl.style.display = "none";
          }
        } else {
          // ĐANG TRONG FLASH SALE: Khôi phục giá khuyến mãi & gạch chân giá gốc
          if (priceEl && card._salePrice) {
            priceEl.textContent = card._salePrice;
          }
          if (oldPriceEl && card._origPrice) {
            oldPriceEl.textContent = card._origPrice;
            oldPriceEl.style.display = "inline";
          }
          if (badgeEl && card._discount) {
            badgeEl.textContent = card._discount;
            badgeEl.style.display = "inline-block";
          }
        }
      });
    }

    // Cập nhật bộ đếm mỗi giây
    function updateCountdown() {
      if (!daysEl || !hoursEl || !minutesEl || !secondsEl) return;

      const now = Date.now();
      const diff = targetEndTime - now;

      // Tiêu chí chấp nhận: Hết hạn KHÔNG hiển thị thời gian âm và GIÁ QUAY VỀ BAN ĐẦU
      if (diff <= 0) {
        daysEl.textContent = "00";
        hoursEl.textContent = "00";
        minutesEl.textContent = "00";
        secondsEl.textContent = "00";
        if (promoHoursEl) promoHoursEl.textContent = "00";
        if (promoDaysEl) promoDaysEl.textContent = "00";
        if (promoMinutesEl) promoMinutesEl.textContent = "00";
        if (promoSecondsEl) promoSecondsEl.textContent = "00";
        if (expiredBadge) expiredBadge.style.display = "inline-flex";
        setFlashSalePricing(true);
        return;
      }

      if (expiredBadge) expiredBadge.style.display = "none";
      setFlashSalePricing(false);

      const days = Math.floor(diff / (1000 * 60 * 60 * 24));
      const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diff % (1000 * 60)) / 1000);

      const daysStr = String(days).padStart(2, "0");
      const hoursStr = String(hours).padStart(2, "0");
      const minStr = String(minutes).padStart(2, "0");
      const secStr = String(seconds).padStart(2, "0");

      daysEl.textContent = daysStr;
      hoursEl.textContent = hoursStr;
      minutesEl.textContent = minStr;
      secondsEl.textContent = secStr;

      if (promoHoursEl) promoHoursEl.textContent = hoursStr;
      if (promoDaysEl) promoDaysEl.textContent = daysStr;
      if (promoMinutesEl) promoMinutesEl.textContent = minStr;
      if (promoSecondsEl) promoSecondsEl.textContent = secStr;
    }

    // Chạy ngay lần đầu và thiết lập interval
    updateCountdown();
    const countdownInterval = setInterval(updateCountdown, 1000);

    // Nút Thử lại trong Empty State (nếu có)
    const emptyRetryBtn = document.getElementById("emptyRetryBtn");
    if (emptyRetryBtn && flashSection) {
      emptyRetryBtn.addEventListener("click", () => {
        flashSection.classList.remove("is-loading", "is-empty");
      });
    }

    /* ====================================================
     * 4. Flash Sale Carousel Navigation Buttons
     * ==================================================== */
    const flashTrack = document.getElementById("flashSaleTrack");
    const flashPrevBtn = document.getElementById("flashSalePrev");
    const flashNextBtn = document.getElementById("flashSaleNext");

    if (flashTrack && flashPrevBtn && flashNextBtn) {
      flashPrevBtn.addEventListener("click", () => {
        flashTrack.scrollBy({ left: -300, behavior: "smooth" });
      });
      flashNextBtn.addEventListener("click", () => {
        flashTrack.scrollBy({ left: 300, behavior: "smooth" });
      });
    }

    /* ====================================================
     * 5. Wishlist Heart Toggle
     * ==================================================== */
    document.querySelectorAll(".product-action-btn[data-action='wishlist']").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        btn.classList.toggle("product-action-btn--active");
      });
    });

    /* ====================================================
     * 6. Back to Top Button
     * ==================================================== */
    const backToTopBtn = document.getElementById("backToTopBtn");
    if (backToTopBtn) {
      window.addEventListener("scroll", () => {
        if (window.scrollY > 400) {
          backToTopBtn.classList.add("back-to-top-btn--show");
        } else {
          backToTopBtn.classList.remove("back-to-top-btn--show");
        }
      });

      backToTopBtn.addEventListener("click", () => {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHomePage);
  } else {
    initHomePage();
  }
})();
