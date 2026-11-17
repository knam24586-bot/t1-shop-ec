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
     * 2. Language Switcher (English <-> Tiếng Việt)
     * ==================================================== */
    const langBtn = document.getElementById("languageBtn");
    const langDropdown = document.getElementById("languageDropdown");
    const langOptions = document.querySelectorAll(".language-item");
    const currentLangLabel = document.getElementById("currentLangLabel");

    function applyLanguage(lang) {
      const isVi = lang === "vi";

      // 1. Cập nhật nhãn nút ngôn ngữ
      if (currentLangLabel) {
        currentLangLabel.textContent = isVi ? "Tiếng Việt" : "English";
      }

      // 2. Active class trong dropdown
      langOptions.forEach((item) => {
        const itemLang = item.getAttribute("data-lang");
        item.classList.toggle("language-item--active", itemLang === lang);
      });

      // 3. Announcement bar
      const announceText = document.querySelector(".announcement__inner p");
      if (announceText) {
        const shopLink = announceText.querySelector("a");
        const linkHref = shopLink ? shopLink.getAttribute("href") : "#shop";
        if (isVi) {
          announceText.innerHTML = `Siêu Sale Mùa Hè Cho Tất Cả Đồ Bơi & Miễn Phí Giao Hàng Siêu Tốc – GIẢM 50%! <a href="${linkHref}">Mua Ngay</a>`;
        } else {
          announceText.innerHTML = `Summer Sale For All Swim Suits And Free Express Delivery – OFF 50%! <a href="${linkHref}">ShopNow</a>`;
        }
      }

      // 4. Primary navigation
      const navLinks = document.querySelectorAll(".navigation .navigation__link");
      if (navLinks.length >= 4) {
        navLinks[0].textContent = isVi ? "Trang Chủ" : "Home";
        navLinks[1].textContent = isVi ? "Liên Hệ" : "Contact";
        navLinks[2].textContent = isVi ? "Giới Thiệu" : "About";
        navLinks[3].textContent = isVi ? "Đăng Ký" : "Sign Up";
      }

      // 5. Search placeholder
      const searchInput = document.querySelector(".search input");
      if (searchInput) {
        searchInput.placeholder = isVi ? "Bạn đang tìm kiếm gì?" : "What are you looking for?";
      }

      // 6. Category sidebar
      const catNames = isVi
        ? [
            "Thời Trang Nữ",
            "Thời Trang Nam",
            "Đồ Điện Tử",
            "Nhà Cửa & Đời Sống",
            "Dược Phẩm",
            "Thể Thao & Dã Ngoại",
            "Đồ Chơi & Mẹ Bé",
            "Tạp Hóa & Thú Cưng",
            "Sức Khỏe & Sắc Đẹp"
          ]
        : [
            "Woman's Fashion",
            "Men's Fashion",
            "Electronics",
            "Home & Lifestyle",
            "Medicine",
            "Sports & Outdoor",
            "Baby's & Toys",
            "Groceries & Pets",
            "Health & Beauty"
          ];
      document.querySelectorAll(".hero-category-item").forEach((item, idx) => {
        const span = item.querySelector("span");
        if (span && catNames[idx]) {
          span.textContent = catNames[idx];
        }
      });

      // 7. Flash Sale Section
      const flashTodayTag = document.querySelector("#flashSaleSection .section-tag__text");
      if (flashTodayTag) flashTodayTag.textContent = isVi ? "Hôm nay" : "Today's";

      const flashTitle = document.querySelector("#flashSaleSection .section-title");
      if (flashTitle) flashTitle.textContent = isVi ? "Flash Sale" : "Flash Sales";

      const cdUnits = document.querySelectorAll("#flashSaleCountdown .countdown-label");
      if (cdUnits.length >= 4) {
        cdUnits[0].textContent = isVi ? "Ngày" : "Days";
        cdUnits[1].textContent = isVi ? "Giờ" : "Hours";
        cdUnits[2].textContent = isVi ? "Phút" : "Minutes";
        cdUnits[3].textContent = isVi ? "Giây" : "Seconds";
      }

      const cdBadge = document.getElementById("cdExpiredBadge");
      if (cdBadge) {
        cdBadge.textContent = isVi ? "⚡ Đã kết thúc" : "⚡ Ended";
      }

      document.querySelectorAll("#flashSaleSection .product-card__add-btn").forEach((btn) => {
        btn.textContent = isVi ? "Thêm Vào Giỏ Hàng" : "Add To Cart";
      });

      const viewAllFlash = document.querySelector("#flashSaleSection .section-center-action .btn-primary-red");
      if (viewAllFlash) viewAllFlash.textContent = isVi ? "Xem Tất Cả Sản Phẩm" : "View All Products";

      // 8. Browse by Category Section
      const catSecTag = document.querySelector(".category-section .section-tag__text");
      if (catSecTag) catSecTag.textContent = isVi ? "Danh mục" : "Categories";
      const catSecTitle = document.querySelector(".category-section .section-title");
      if (catSecTitle) catSecTitle.textContent = isVi ? "Duyệt Theo Danh Mục" : "Browse By Category";

      const catCardNames = isVi
        ? ["Điện Thoại", "Máy Tính", "SmartWatch", "Máy Ảnh", "Tai Nghe", "Gaming"]
        : ["Phones", "Computers", "SmartWatch", "Camera", "HeadPhones", "Gaming"];
      document.querySelectorAll(".category-card").forEach((card, idx) => {
        const span = card.querySelector("span");
        if (span && catCardNames[idx]) span.textContent = catCardNames[idx];
      });

      // 9. Best Selling Section
      const bsTag = document.querySelector(".best-selling-section .section-tag__text");
      if (bsTag) bsTag.textContent = isVi ? "Tháng này" : "This Month";
      const bsTitle = document.querySelector(".best-selling-section .section-title");
      if (bsTitle) bsTitle.textContent = isVi ? "Sản Phẩm Bán Chạy" : "Best Selling Products";
      const bsBtn = document.querySelector(".best-selling-section .section-view-all-btn");
      if (bsBtn) {
        const isExp = document.getElementById("bestSellingSection")?.classList.contains("is-expanded");
        const spanText = bsBtn.querySelector(".btn-text") || bsBtn;
        if (isExp) {
          spanText.textContent = isVi ? "Thu Gọn" : "View Less";
        } else {
          spanText.textContent = isVi ? "Xem Tất Cả" : "View All";
        }
      }
      const bsEmptyTitle = document.querySelector("#bestSellingEmptyState .empty-state__title");
      if (bsEmptyTitle) bsEmptyTitle.textContent = isVi ? "Chưa có sản phẩm bán chạy trong tháng này" : "No best-selling products this month";
      const bsEmptyDesc = document.querySelector("#bestSellingEmptyState .empty-state__desc");
      if (bsEmptyDesc) bsEmptyDesc.textContent = isVi ? "Danh sách các sản phẩm bán chạy nhất sẽ được cập nhật liên tục. Bạn có thể nhấn nút bên dưới để thử tải lại dữ liệu." : "Best-selling products will be updated soon. You can try reloading or explore other categories.";
      const bsRetry = document.getElementById("bestSellingRetryBtn");
      if (bsRetry) bsRetry.textContent = isVi ? "Tải lại dữ liệu" : "Reload Data";

      // 10. Promo Banner (Music Experience)
      const promoCat = document.querySelector(".promo-banner__category");
      if (promoCat) promoCat.textContent = isVi ? "Danh mục" : "Categories";
      const promoTitle = document.querySelector(".promo-banner__title");
      if (promoTitle) {
        promoTitle.innerHTML = isVi ? "Nâng Tầm Trải Nghiệm<br>Âm Nhạc" : "Enhance Your<br>Music Experience";
      }
      const promoUnits = document.querySelectorAll(".promo-countdown-unit");
      if (promoUnits.length >= 4) {
        promoUnits[0].textContent = isVi ? "Giờ" : "Hours";
        promoUnits[1].textContent = isVi ? "Ngày" : "Days";
        promoUnits[2].textContent = isVi ? "Phút" : "Minutes";
        promoUnits[3].textContent = isVi ? "Giây" : "Seconds";
      }
      const promoBtn = document.querySelector(".promo-btn");
      if (promoBtn) promoBtn.textContent = isVi ? "Mua Ngay!" : "Buy Now!";

      // 11. Explore Our Products Section
      const exploreTag = document.querySelector(".explore-section .section-tag__text");
      if (exploreTag) exploreTag.textContent = isVi ? "Sản phẩm" : "Our Products";
      const exploreTitle = document.querySelector(".explore-section .section-title");
      if (exploreTitle) exploreTitle.textContent = isVi ? "Khám Phá Sản Phẩm Của Chúng Tôi" : "Explore Our Products";
      const exploreViewAll = document.querySelector(".explore-section .section-center-action .btn-primary-red");
      if (exploreViewAll) exploreViewAll.textContent = isVi ? "Xem Tất Cả Sản Phẩm" : "View All Products";

      // 12. Featured / New Arrival Section
      const featTag = document.querySelector(".featured-section .section-tag__text");
      if (featTag) featTag.textContent = isVi ? "Nổi bật" : "Featured";
      const featTitle = document.querySelector(".featured-section .section-title");
      if (featTitle) featTitle.textContent = isVi ? "Hàng Mới Về" : "New Arrival";

      const bCard1Desc = document.querySelector(".featured-bento__card--large p");
      if (bCard1Desc) {
        bCard1Desc.textContent = isVi
          ? "Phiên bản PS5 đen trắng cực hot sắp mở bán."
          : "Black and White version of the PS5 coming out on sale.";
      }

      const bCard2Title = document.querySelector(".featured-bento__card--wide h3");
      if (bCard2Title) bCard2Title.textContent = isVi ? "Bộ Sưu Tập Nữ" : "Women's Collections";
      const bCard2Desc = document.querySelector(".featured-bento__card--wide p");
      if (bCard2Desc) {
        bCard2Desc.textContent = isVi
          ? "Bộ sưu tập thời trang nữ đem lại phong cách cuốn hút."
          : "Featured woman collections that give you another vibe.";
      }

      const bCardSmall = document.querySelectorAll(".featured-bento__card--small");
      if (bCardSmall.length >= 2) {
        const spkTitle = bCardSmall[0].querySelector("h3");
        if (spkTitle) spkTitle.textContent = isVi ? "Loa Không Dây" : "Speakers";
        const spkDesc = bCardSmall[0].querySelector("p");
        if (spkDesc) spkDesc.textContent = isVi ? "Loa Bluetooth Amazon cao cấp" : "Amazon wireless speakers";

        const pfTitle = bCardSmall[1].querySelector("h3");
        if (pfTitle) pfTitle.textContent = isVi ? "Nước Hoa" : "Perfume";
        const pfDesc = bCardSmall[1].querySelector("p");
        if (pfDesc) pfDesc.textContent = isVi ? "Nước hoa GUCCI INTENSE OUD EDP" : "GUCCI INTENSE OUD EDP";
      }

      document.querySelectorAll(".featured-link").forEach((link) => {
        link.textContent = isVi ? "Mua Ngay" : "Shop Now";
      });

      // 13. Services Section
      const srvItems = document.querySelectorAll(".service-item");
      if (srvItems.length >= 3) {
        const h3_1 = srvItems[0].querySelector("h3");
        if (h3_1) h3_1.textContent = isVi ? "GIAO HÀNG NHANH & MIỄN PHÍ" : "FREE AND FAST DELIVERY";
        const p_1 = srvItems[0].querySelector("p");
        if (p_1) p_1.textContent = isVi ? "Miễn phí giao hàng cho tất cả đơn trên $140" : "Free delivery for all orders over $140";

        const h3_2 = srvItems[1].querySelector("h3");
        if (h3_2) h3_2.textContent = isVi ? "HỖ TRỢ KHÁCH HÀNG 24/7" : "24/7 CUSTOMER SERVICE";
        const p_2 = srvItems[1].querySelector("p");
        if (p_2) p_2.textContent = isVi ? "Đội ngũ hỗ trợ thân thiện 24/7" : "Friendly 24/7 customer support";

        const h3_3 = srvItems[2].querySelector("h3");
        if (h3_3) h3_3.textContent = isVi ? "HOÀN TIỀN ĐẢM BẢO" : "MONEY BACK GUARANTEE";
        const p_3 = srvItems[2].querySelector("p");
        if (p_3) p_3.textContent = isVi ? "Hoàn tiền nhanh chóng trong vòng 30 ngày" : "We return money within 30 days";
      }

      // 14. Footer
      const fSub = document.querySelector(".footer-newsletter .column-subtitle");
      if (fSub) fSub.textContent = isVi ? "Đăng Ký" : "Subscribe";
      const fCopy = document.querySelector(".footer-newsletter .newsletter-copy");
      if (fCopy) fCopy.textContent = isVi ? "Giảm 10% cho đơn hàng đầu tiên của bạn" : "Get 10% off your first order";
      const fInput = document.getElementById("subscriber-email");
      if (fInput) fInput.placeholder = isVi ? "Nhập email của bạn" : "Enter your email";

      const fCols = document.querySelectorAll(".site-footer .footer-column");
      if (fCols.length >= 4) {
        // Cột 2: Support
        const h2_sup = fCols[1].querySelector("h2");
        if (h2_sup) h2_sup.textContent = isVi ? "Hỗ Trợ" : "Support";

        // Cột 3: Account
        const h2_acc = fCols[2].querySelector("h2");
        if (h2_acc) h2_acc.textContent = isVi ? "Tài Khoản" : "Account";
        const accLinks = fCols[2].querySelectorAll("ul li a");
        if (accLinks.length >= 5) {
          accLinks[0].textContent = isVi ? "Tài Khoản Của Tôi" : "My Account";
          accLinks[1].textContent = isVi ? "Đăng Nhập / Đăng Ký" : "Login / Register";
          accLinks[2].textContent = isVi ? "Giỏ Hàng" : "Cart";
          accLinks[3].textContent = isVi ? "Yêu Thích" : "Wishlist";
          accLinks[4].textContent = isVi ? "Cửa Hàng" : "Shop";
        }

        // Cột 4: Quick Link
        const h2_quick = fCols[3].querySelector("h2");
        if (h2_quick) h2_quick.textContent = isVi ? "Liên Kết Nhanh" : "Quick Link";
        const qLinks = fCols[3].querySelectorAll("ul li a");
        if (qLinks.length >= 4) {
          qLinks[0].textContent = isVi ? "Chính Sách Bảo Mật" : "Privacy Policy";
          qLinks[1].textContent = isVi ? "Điều Khoản Sử Dụng" : "Terms Of Use";
          qLinks[2].textContent = isVi ? "Câu Hỏi Thường Gặp" : "FAQ";
          qLinks[3].textContent = isVi ? "Liên Hệ" : "Contact";
        }
      }

      if (typeof categoryDisplayNames !== "undefined" && currentActiveCategory) {
        const activeCatInfo = categoryDisplayNames[currentActiveCategory] || { en: currentActiveCategory, vi: currentActiveCategory };
        const actBadge = document.getElementById("activeCategoryBadge");
        if (actBadge) actBadge.textContent = isVi ? activeCatInfo.vi : activeCatInfo.en;
        const curMatchCount = document.querySelectorAll("#exploreProductsGrid .product-card:not([style*='display: none'])").length;
        const actCount = document.getElementById("activeCategoryCount");
        if (actCount) actCount.textContent = isVi ? `(${curMatchCount} sản phẩm)` : `(${curMatchCount} products)`;
      }
      const filterLbl = document.getElementById("filterLabelText");
      if (filterLbl) filterLbl.textContent = isVi ? "Đang lọc theo danh mục:" : "Filtered by category:";
      const clearBtnTxt = document.getElementById("clearFilterBtnText");
      if (clearBtnTxt) clearBtnTxt.textContent = isVi ? "Xóa bộ lọc" : "Clear filter";
      const emptyTitle = document.getElementById("emptyCategoryTitle");
      if (emptyTitle) emptyTitle.textContent = isVi ? "Không tìm thấy sản phẩm" : "No products found";
      const emptyDesc = document.getElementById("emptyCategoryDesc");
      if (emptyDesc) emptyDesc.textContent = isVi ? "Hiện chưa có sản phẩm nào thuộc danh mục này." : "There are currently no products in this category.";
      const emptyReset = document.getElementById("emptyCategoryResetBtn");
      if (emptyReset) emptyReset.textContent = isVi ? "Xem tất cả sản phẩm" : "View all products";

      document.documentElement.lang = lang;
    }

    if (langBtn && langDropdown) {
      const toggleDropdown = (show) => {
        const isOpen = typeof show === "boolean" ? show : !langDropdown.classList.contains("language-dropdown--open");
        langDropdown.classList.toggle("language-dropdown--open", isOpen);
        langBtn.setAttribute("aria-expanded", String(isOpen));
      };

      langBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleDropdown();
      });

      langOptions.forEach((opt) => {
        opt.addEventListener("click", (e) => {
          e.stopPropagation();
          const selectedLang = opt.getAttribute("data-lang");
          if (selectedLang) {
            applyLanguage(selectedLang);
            try {
              localStorage.setItem("t1_selected_lang", selectedLang);
            } catch (err) {}
          }
          toggleDropdown(false);
        });
      });

      document.addEventListener("click", (e) => {
        if (!langBtn.contains(e.target) && !langDropdown.contains(e.target)) {
          toggleDropdown(false);
        }
      });

      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          toggleDropdown(false);
        }
      });

      let savedLang = "en";
      try {
        savedLang = localStorage.getItem("t1_selected_lang") || "en";
      } catch (err) {}
      applyLanguage(savedLang);
    }

    /* ====================================================
     * 3. Hero Banner Slider (Nút chuyển slide & Dot điều hướng)
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
     * 4. Flash Sale Countdown Timer & Dynamic Pricing
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
     * 4b. Best Selling Products: View All & Empty State
     * ==================================================== */
    const bestSellingSectionEl = document.getElementById("bestSellingSection");
    const bestSellingViewAllBtn = document.getElementById("bestSellingViewAllBtn");
    const bestSellingGridEl = document.getElementById("bestSellingGrid");
    const bestSellingRetryBtn = document.getElementById("bestSellingRetryBtn");

    function updateBestSellingEmptyState() {
      if (!bestSellingSectionEl || !bestSellingGridEl) return;
      const cards = bestSellingGridEl.querySelectorAll(".product-card");
      if (cards.length === 0) {
        bestSellingSectionEl.classList.add("is-empty");
        if (bestSellingViewAllBtn) bestSellingViewAllBtn.style.display = "none";
      } else {
        bestSellingSectionEl.classList.remove("is-empty");
        if (bestSellingViewAllBtn) bestSellingViewAllBtn.style.display = "inline-flex";
      }
    }

    if (bestSellingViewAllBtn) {
      bestSellingViewAllBtn.addEventListener("click", (e) => {
        e.preventDefault();
        if (!bestSellingSectionEl) return;
        const isExpanded = bestSellingSectionEl.classList.toggle("is-expanded");
        const isVi = document.documentElement.lang === "vi";
        const textSpan = bestSellingViewAllBtn.querySelector(".btn-text") || bestSellingViewAllBtn;

        if (isExpanded) {
          textSpan.textContent = isVi ? "Thu Gọn" : "View Less";
        } else {
          textSpan.textContent = isVi ? "Xem Tất Cả" : "View All";
          bestSellingSectionEl.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    }

    if (bestSellingRetryBtn && bestSellingSectionEl) {
      bestSellingRetryBtn.addEventListener("click", () => {
        bestSellingSectionEl.classList.add("is-loading");
        bestSellingSectionEl.classList.remove("is-empty");
        setTimeout(() => {
          bestSellingSectionEl.classList.remove("is-loading");
          updateBestSellingEmptyState();
        }, 600);
      });
    }

    updateBestSellingEmptyState();

    /* ====================================================
     * 5. Flash Sale Carousel Navigation Buttons
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
     * 6. Wishlist Heart Toggle
     * ==================================================== */
    document.querySelectorAll(".product-action-btn[data-action='wishlist']").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        btn.classList.toggle("product-action-btn--active");
      });
    });

    /* ====================================================
     * 7. Back to Top Button
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

    /* ====================================================
     * 8. Category Filter & Active State
     * ==================================================== */
    let currentActiveCategory = null;
    const categoryCards = document.querySelectorAll(".category-card");
    const heroCategoryLinks = document.querySelectorAll(".hero-categories a[data-category]");
    const filterStatusEl = document.getElementById("categoryFilterStatus");
    const activeBadgeEl = document.getElementById("activeCategoryBadge");
    const activeCountEl = document.getElementById("activeCategoryCount");
    const clearFilterBtn = document.getElementById("clearCategoryFilterBtn");
    const emptyResetBtn = document.getElementById("emptyCategoryResetBtn");
    const emptyFilterEl = document.getElementById("categoryFilterEmpty");
    const productCards = document.querySelectorAll("#exploreProductsGrid .product-card");
    const exploreSection = document.getElementById("exploreSection");

    const categoryDisplayNames = {
      phones: { en: "Phones", vi: "Điện Thoại" },
      computers: { en: "Computers", vi: "Máy Tính" },
      smartwatch: { en: "SmartWatch", vi: "SmartWatch" },
      camera: { en: "Camera", vi: "Máy Ảnh" },
      headphones: { en: "HeadPhones", vi: "Tai Nghe / Âm Thanh" },
      gaming: { en: "Gaming", vi: "Gaming" },
      "fashion-women": { en: "Woman's Fashion", vi: "Thời Trang Nữ" },
      "fashion-men": { en: "Men's Fashion", vi: "Thời Trang Nam" },
      electronics: { en: "Electronics", vi: "Đồ Điện Tử" },
      "home-lifestyle": { en: "Home & Lifestyle", vi: "Đời Sống & Nhà Cửa" },
      medicine: { en: "Medicine", vi: "Dược Phẩm" },
      sports: { en: "Sports & Outdoor", vi: "Thể Thao & Dã Ngoại" },
      "baby-toys": { en: "Baby's & Toys", vi: "Mẹ & Bé - Đồ Chơi" },
      groceries: { en: "Groceries & Pets", vi: "Bách Hóa & Thú Cưng" },
      "health-beauty": { en: "Health & Beauty", vi: "Sức Khỏe & Làm Đẹp" }
    };

    function filterProductsByCategory(categoryKey, scrollToResults = false) {
      const isVi = document.documentElement.lang === "vi";
      if (!categoryKey || categoryKey === "all") {
        currentActiveCategory = null;
        categoryCards.forEach((card) => {
          card.classList.remove("category-card--active");
          card.setAttribute("aria-selected", "false");
        });
        document.querySelectorAll(".hero-category-item").forEach((item) => {
          item.classList.remove("hero-category-item--active");
        });
        productCards.forEach((card) => {
          card.style.display = "";
        });
        if (filterStatusEl) filterStatusEl.classList.remove("category-filter-status--show");
        if (emptyFilterEl) emptyFilterEl.classList.remove("category-filter-empty--show");
        return;
      }

      currentActiveCategory = categoryKey;

      categoryCards.forEach((card) => {
        const cat = card.getAttribute("data-category");
        const isActive = cat === categoryKey;
        card.classList.toggle("category-card--active", isActive);
        card.setAttribute("aria-selected", String(isActive));
      });

      document.querySelectorAll(".hero-categories a[data-category]").forEach((link) => {
        const cat = link.getAttribute("data-category");
        const parentLi = link.closest(".hero-category-item");
        const isActive = cat && (cat === categoryKey || cat.split(" ").includes(categoryKey));
        if (parentLi) {
          parentLi.classList.toggle("hero-category-item--active", Boolean(isActive));
        }
      });

      let matchCount = 0;
      productCards.forEach((card) => {
        const prodCats = (card.getAttribute("data-category") || "").toLowerCase().split(" ");
        const targetTokens = categoryKey.toLowerCase().split(" ");
        const isMatch = targetTokens.some((t) => prodCats.includes(t));
        if (isMatch) {
          card.style.display = "";
          matchCount++;
        } else {
          card.style.display = "none";
        }
      });

      const catInfo = categoryDisplayNames[categoryKey] || { en: categoryKey, vi: categoryKey };
      const displayName = isVi ? catInfo.vi : catInfo.en;

      if (activeBadgeEl) activeBadgeEl.textContent = displayName;
      if (activeCountEl) {
        activeCountEl.textContent = isVi ? `(${matchCount} sản phẩm)` : `(${matchCount} products)`;
      }
      if (filterStatusEl) filterStatusEl.classList.add("category-filter-status--show");

      if (emptyFilterEl) {
        if (matchCount === 0) {
          emptyFilterEl.classList.add("category-filter-empty--show");
        } else {
          emptyFilterEl.classList.remove("category-filter-empty--show");
        }
      }

      if (scrollToResults && exploreSection) {
        exploreSection.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }

    categoryCards.forEach((card) => {
      card.addEventListener("click", (e) => {
        e.preventDefault();
        const cat = card.getAttribute("data-category");
        if (currentActiveCategory === cat) {
          filterProductsByCategory(null, false);
        } else {
          filterProductsByCategory(cat, true);
        }
      });
    });

    heroCategoryLinks.forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const cat = link.getAttribute("data-category");
        if (currentActiveCategory === cat) {
          filterProductsByCategory(null, false);
        } else {
          filterProductsByCategory(cat, true);
        }
      });
    });

    if (clearFilterBtn) {
      clearFilterBtn.addEventListener("click", (e) => {
        e.preventDefault();
        filterProductsByCategory(null, false);
      });
    }

    if (emptyResetBtn) {
      emptyResetBtn.addEventListener("click", (e) => {
        e.preventDefault();
        filterProductsByCategory(null, false);
      });
    }

    const categoryGrid = document.getElementById("categoryGrid");
    const categoryPrev = document.getElementById("categoryPrev");
    const categoryNext = document.getElementById("categoryNext");
    if (categoryGrid && categoryPrev && categoryNext) {
      categoryPrev.addEventListener("click", () => {
        categoryGrid.scrollBy({ left: -200, behavior: "smooth" });
      });
      categoryNext.addEventListener("click", () => {
        categoryGrid.scrollBy({ left: 200, behavior: "smooth" });
      });
    }

    /* ====================================================
     * 9. Image Fallback Handling (Tự động phục hồi ảnh lỗi)
     * ==================================================== */
    const FALLBACK_IMAGE = "data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22300%22%20height%3D%22300%22%20viewBox%3D%220%200%20300%20300%22%20fill%3D%22none%22%3E%3Crect%20width%3D%22300%22%20height%3D%22300%22%20fill%3D%22%23F5F5F5%22%2F%3E%3Cpath%20d%3D%22M150%20110c-16.57%200-30%2013.43-30%2030s13.43%2030%2030%2030%2030-13.43%2030-30-13.43-30-30-30zm0%2048c-9.94%200-18-8.06-18-18s8.06-18%2018-18%2018%208.06%2018%2018-8.06%2018-18%2018zm60-88H90c-11.05%200-20%208.95-20%2020v120c0%2011.05%208.95%2020%2020%2020h120c11.05%200%2020-8.95%2020-20V90c0-11.05-8.95-20-20-20zm8%20140c0%204.41-3.59%208-8%208H90c-4.41%200-8-3.59-8-8V90c0-4.41%203.59-8%208-8h120c4.41%200%208%203.59%208%208v120z%22%20fill%3D%22%23B0B0B0%22%2F%3E%3Ctext%20x%3D%22150%22%20y%3D%22225%22%20text-anchor%3D%22middle%22%20fill%3D%22%23888888%22%20font-family%3D%22sans-serif%22%20font-size%3D%2214%22%20font-weight%3D%22500%22%3EImage%20Not%20Available%3C%2Ftext%3E%3C%2Fsvg%3E";

    function setupImageFallback(img) {
      if (!img) return;
      img.addEventListener("error", function () {
        if (this.dataset.fallbackApplied === "final") return;
        if (this.dataset.fallbackApplied === "alt-path") {
          this.dataset.fallbackApplied = "final";
          this.src = FALLBACK_IMAGE;
          return;
        }
        this.dataset.fallbackApplied = "alt-path";
        if (this.src.includes("/frontend/assets/")) {
          this.src = this.src.replace(/.*\/frontend\/assets\//, "../assets/");
        } else if (this.src.includes("../assets/")) {
          this.src = this.src.replace(/.*\/assets\//, "/frontend/assets/");
        } else {
          this.src = FALLBACK_IMAGE;
        }
      });

      if (img.complete && img.naturalWidth === 0) {
        img.dataset.fallbackApplied = "final";
        img.src = FALLBACK_IMAGE;
      }
    }

    document.querySelectorAll("img").forEach(setupImageFallback);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHomePage);
  } else {
    initHomePage();
  }
})();
