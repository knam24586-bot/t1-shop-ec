/**
 * T1 Shop - Header Search Bar & Global Autocomplete Component
 * Hỗ trợ tìm kiếm theo từ khóa, gợi ý danh mục và khoảng giá trên tất cả các trang
 * Tiêu chí chấp nhận:
 * 1. Tìm theo từ khóa và lọc danh mục / khoảng giá
 * 2. Tiêu chí lọc được phản ánh trên danh sách và URL parameters (?q=, ?category=, ?min=, ?max=)
 * 3. Không có kết quả hiển thị empty state
 * 4. Đồng bộ trên toàn bộ các file: Shop.html, E-CommerceHomePage.html, WishList.html, AccountDropdownWithAccount.html
 */

(() => {
  // SVG Data URI fallback khi ảnh không tải được
  const FALLBACK_IMAGE = "data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2280%22%20height%3D%2280%22%20viewBox%3D%220%200%2080%2080%22%20fill%3D%22none%22%3E%3Crect%20width%3D%2280%22%20height%3D%2280%22%20fill%3D%22%23F5F5F5%22%2F%3E%3Ccircle%20cx%3D%2240%22%20cy%3D%2240%22%20r%3D%2218%22%20fill%3D%22%23E0E0E0%22%2F%3E%3Ctext%20x%3D%2240%22%20y%3D%2244%22%20text-anchor%3D%22middle%22%20fill%3D%22%23888%22%20font-size%3D%2210%22%3ET1%3C%2Ftext%3E%3C%2Fsvg%3E";

  // Danh mục sản phẩm chuẩn hóa
  const CATEGORIES = [
    { key: "gaming", en: "Gaming", vi: "Gaming & Phụ Kiện", keywords: ["gaming", "game", "tay cam", "gamepad", "ban phim", "keyboard", "chuot", "mouse"] },
    { key: "computers", en: "Computers", vi: "Máy Tính & Laptop", keywords: ["computer", "computers", "laptop", "pc", "man hinh", "monitor", "asus", "fhd"] },
    { key: "electronics", en: "Electronics", vi: "Đồ Điện Tử", keywords: ["electronics", "dien tu", "camera", "may anh", "eos", "loa", "speaker", "jbl", "cooler", "tan nhiet", "cpu"] },
    { key: "fashion", en: "Fashion", vi: "Thời Trang", keywords: ["fashion", "thoi trang", "tui", "bag", "duffle", "gucci", "jacket", "ao khoac", "coat", "satin"] },
    { key: "home-lifestyle", en: "Home & Lifestyle", vi: "Nhà Cửa & Đời Sống", keywords: ["home", "lifestyle", "nha cua", "chair", "ghe", "bookshelf", "ke sach", "gia sach"] },
    { key: "sports", en: "Sports", vi: "Thể Thao", keywords: ["sports", "sport", "the thao", "cleats", "giay da bong", "soccer", "zoom"] },
    { key: "health-beauty", en: "Health & Beauty", vi: "Sức Khỏe & Làm Đẹp", keywords: ["health", "beauty", "lam dep", "curology", "my pham", "skincare"] },
    { key: "baby-toys", en: "Baby & Toys", vi: "Đồ Chơi & Mẹ Bé", keywords: ["baby", "toys", "do choi", "toy", "electric car", "o to dien", "mercedes"] },
    { key: "groceries", en: "Groceries", vi: "Bách Hóa & Thú Cưng", keywords: ["groceries", "dog food", "thuc an cho", "pet", "thu cung"] }
  ];

  // Khoảng giá gợi ý
  const PRICE_PRESETS = [
    { labelEn: "Under $100", labelVi: "Dưới $100", min: 0, max: 100, keywords: ["duoi 100", "under 100", "<100", "< 100", "gia re", "re"] },
    { labelEn: "$100 – $500", labelVi: "Từ $100 đến $500", min: 100, max: 500, keywords: ["100-500", "100 500", "tam trung"] },
    { labelEn: "$500 – $1,000", labelVi: "Từ $500 đến $1,000", min: 500, max: 1000, keywords: ["500-1000", "500 1000", "500-1.000"] },
    { labelEn: "Over $1,000", labelVi: "Trên $1,000", min: 1000, max: null, keywords: ["tren 1000", "over 1000", ">1000", "> 1000", "cao cap"] }
  ];

  // Catalogue sản phẩm hoàn chỉnh của T1 Shop
  const CATALOG_PRODUCTS = [
    {
      id: 1,
      name: "Gucci duffle bag",
      category: "fashion",
      price: 960,
      oldPrice: 1160,
      image: "../assets/images/products/Frame 606.png",
      description: "Túi du lịch Gucci Duffle Bag phong cách thanh lịch, chất liệu da cao cấp chống thấm nước."
    },
    {
      id: 2,
      name: "RGB liquid CPU Cooler",
      category: "electronics",
      price: 1960,
      oldPrice: null,
      image: "../assets/images/products/Frame 610.png",
      description: "Bộ tản nhiệt nước AIO hiệu năng cao kèm đèn LED ARGB tùy biến, quạt tản nhiệt êm ái."
    },
    {
      id: 3,
      name: "GP11 Shooter USB Gamepad",
      category: "gaming",
      price: 550,
      oldPrice: null,
      image: "../assets/images/products/GP11_PRD3 1.png",
      description: "Tay cầm chơi game USB cổng đôi với bộ rung phản hồi lực chân thực, tối ưu cho PC."
    },
    {
      id: 4,
      name: "Quilted Satin Jacket",
      category: "fashion",
      price: 750,
      oldPrice: null,
      image: "../assets/images/products/698717_Z8A1X_3475_001_100_0000_Light-Reversible-quilted-satin-jacket 1.png",
      description: "Áo khoác satin trần bông siêu nhẹ, thiết kế hai mặt tiện dụng, kiểu dáng bomber trẻ trung."
    },
    {
      id: 5,
      name: "ASUS FHD Gaming Laptop",
      category: "computers",
      price: 960,
      oldPrice: 1160,
      image: "../assets/images/products/ideapad-gaming-3i-01-500x500 1.png",
      description: "Laptop gaming ASUS màn hình 144Hz FHD sắc nét, vi xử lý Core i7 mạnh mẽ, card RTX."
    },
    {
      id: 6,
      name: "IPS LCD Gaming Monitor",
      category: "computers",
      price: 1160,
      oldPrice: null,
      image: "../assets/images/products/Frame 613.png",
      description: "Màn hình cong chuyên game tấm nền IPS chân thực, tần số quét 165Hz tốc độ phản hồi 1ms."
    },
    {
      id: 7,
      name: "HAVIT HV-G92 Gamepad",
      category: "gaming",
      price: 560,
      oldPrice: null,
      image: "../assets/images/products/Frame 611.png",
      description: "Tay cầm gamepad Havit phong cách Pro gaming, tích hợp cần analog 360 độ chính xác."
    },
    {
      id: 8,
      name: "AK-900 Wired Keyboard",
      category: "gaming",
      price: 200,
      oldPrice: null,
      image: "../assets/images/products/Frame 612 (1).png",
      description: "Bàn phím cơ có dây AK-900 đèn nền LED Rainbow nhiều chế độ, phím bấm nhạy nảy."
    },
    {
      id: 9,
      name: "CANON EOS DSLR Camera",
      category: "electronics",
      price: 360,
      oldPrice: null,
      image: "../assets/images/products/eos-250d-03-500x500 1.png",
      description: "Máy ảnh kỹ thuật số Canon EOS cảm biến CMOS 24.1MP, hỗ trợ quay video 4K sắc nét."
    },
    {
      id: 10,
      name: "Jr. Zoom Soccer Cleats",
      category: "sports",
      price: 1160,
      oldPrice: null,
      image: "../assets/images/products/Copa_Sense 1.png",
      description: "Giày đá bóng sân cỏ tự nhiên cao cấp, đệm khí Zoom Air trợ lực êm chân."
    },
    {
      id: 11,
      name: "Kids Electric Toy Car",
      category: "baby-toys",
      price: 960,
      oldPrice: null,
      image: "../assets/images/products/New-Mercedes-Benz-Gtr-Licensed-Ride-on-Car-Kids-Electric-Toy-Car 1.png",
      description: "Ô tô điện trẻ em Mercedes-Benz GTR bản quyền, 2 động cơ mạnh mẽ, điều khiển từ xa an toàn."
    },
    {
      id: 12,
      name: "Curology Product Set",
      category: "health-beauty",
      price: 500,
      oldPrice: null,
      image: "../assets/images/products/curology-j7pKVQrTUsM-unsplash 1.png",
      description: "Bộ mỹ phẩm chăm sóc da chuyên sâu Curology, thành phần thiên nhiên dưỡng ẩm phục hồi."
    },
    {
      id: 13,
      name: "The North Coat",
      category: "fashion",
      price: 260,
      oldPrice: null,
      image: "../assets/images/products/672462_ZAH9D_5626_002_100_0000_Light-The-North-Face-x-Gucci-coat 1.png",
      description: "Áo măng tô The North Coat vải dạ dày dặn dệt chéo, giữ ấm tối đa khi trời trở lạnh."
    },
    {
      id: 14,
      name: "S-Series Comfort Chair",
      category: "home-lifestyle",
      price: 375,
      oldPrice: 400,
      image: "../assets/images/products/sam-moghadam-khamseh-kvmdsTrGOBM-unsplash 1.png",
      description: "Ghế bành công thái học thư giãn đệm mút nguyên khối đàn hồi cao, tựa lưng nâng đỡ cột sống."
    },
    {
      id: 15,
      name: "Small BookShelf",
      category: "home-lifestyle",
      price: 360,
      oldPrice: null,
      image: "../assets/images/products/sam-moghadam-khamseh-L_7AcioNKTg-unsplash 1.png",
      description: "Kệ sách gỗ công nghiệp kháng ẩm 4 tầng phong cách Bắc Âu tối giản, đa năng."
    },
    {
      id: 16,
      name: "Breed Dry Dog Food",
      category: "groceries",
      price: 100,
      oldPrice: null,
      image: "../assets/images/products/71RdoeXxtrL 1.png",
      description: "Thức ăn hạt cao cấp cho chó giống trung và lớn, bổ sung đầy đủ đạm, canxi và omega-3."
    },
    {
      id: 17,
      name: "JBL Wireless Speaker",
      category: "electronics",
      price: 450,
      oldPrice: null,
      image: "../assets/images/products/Frame 610.png",
      description: "Loa Bluetooth di động chống nước chuẩn IPX7, âm bass sâu trầm uy lực, pin 12 giờ."
    }
  ];

  // Hàm chuyển đổi đường dẫn Shop.html chuẩn xác theo ngữ cảnh thư mục
  function resolveShopUrl() {
    const path = window.location.pathname;
    if (path.includes("/pages/") || path.endsWith("/pages")) {
      return "./Shop.html";
    }
    return "/frontend/pages/Shop.html";
  }

  // Khử dấu tiếng Việt để tìm kiếm không phân biệt dấu
  function removeAccents(str) {
    if (!str) return "";
    return str
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D")
      .toLowerCase();
  }

  // Escape HTML an toàn
  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Highlight từ khóa tìm kiếm
  function highlightMatch(text, query) {
    if (!query) return escapeHtml(text);
    const escapedText = escapeHtml(text);
    const cleanQ = escapeHtml(query.trim());
    if (!cleanQ) return escapedText;

    try {
      const regex = new RegExp(`(${cleanQ.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
      return escapedText.replace(regex, "<mark class='search-highlight'>$1</mark>");
    } catch {
      return escapedText;
    }
  }

  // Khởi tạo thanh tìm kiếm trên trang hiện tại
  function initHeaderSearchBar() {
    const searchForm = document.querySelector('.search[role="search"]') || document.querySelector("form.search");
    if (!searchForm) return;

    const searchInput = searchForm.querySelector('input[type="search"]') || searchForm.querySelector('input[name="q"]');
    if (!searchInput) return;

    // 1. Cấu hình form đích đến trang Shop.html
    const shopUrl = resolveShopUrl();
    searchForm.setAttribute("action", shopUrl);
    searchForm.setAttribute("method", "get");
    searchForm.setAttribute("role", "search");
    searchForm.classList.add("header-search-enhanced");

    searchInput.setAttribute("name", "q");
    searchInput.setAttribute("autocomplete", "off");
    searchInput.setAttribute("spellcheck", "false");

    // 2. Thêm hoặc chuẩn hóa nút Xóa nhanh (✕) duy nhất
    const CLEAR_ICON_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';
    let clearBtn = searchForm.querySelector(".search-clear-btn");
    if (!clearBtn) {
      clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "search-clear-btn";
      clearBtn.setAttribute("aria-label", "Xóa từ khóa");
      clearBtn.innerHTML = CLEAR_ICON_SVG;
      clearBtn.style.display = "none";

      const submitBtn = searchForm.querySelector('button[type="submit"]') || searchForm.querySelector("button");
      if (submitBtn) {
        searchForm.insertBefore(clearBtn, submitBtn);
      } else {
        searchForm.appendChild(clearBtn);
      }
    } else {
      clearBtn.innerHTML = CLEAR_ICON_SVG;
    }

    // 3. Tạo Dropdown hiển thị kết quả Live Search
    let dropdown = searchForm.querySelector(".search-autocomplete-dropdown");
    if (!dropdown) {
      dropdown = document.createElement("div");
      dropdown.className = "search-autocomplete-dropdown";
      dropdown.id = "headerSearchDropdown";
      dropdown.style.display = "none";
      searchForm.appendChild(dropdown);
    }

    let activeIndex = -1;
    let debounceTimer = null;

    // Đọc query sẵn có từ URL nếu đang ở trang Shop
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const initialQ = urlParams.get("q");
      if (initialQ && initialQ.trim()) {
        searchInput.value = initialQ.trim();
        clearBtn.style.display = "flex";
      }
    } catch {
      // Ignore
    }

    // Hàm cập nhật trạng thái hiển thị của nút clear
    function updateClearButton() {
      const hasVal = Boolean(searchInput.value.trim());
      clearBtn.style.display = hasVal ? "flex" : "none";
    }

    // Lấy ngôn ngữ hiện tại
    function getIsVi() {
      return document.documentElement.lang === "vi";
    }

    // Đóng dropdown
    function closeDropdown() {
      dropdown.style.display = "none";
      dropdown.innerHTML = "";
      activeIndex = -1;
    }

    // Tìm kiếm và hiển thị gợi ý
    function renderSuggestions(query) {
      const q = query.trim();
      if (!q) {
        closeDropdown();
        return;
      }

      const isVi = getIsVi();
      const normQ = removeAccents(q);

      // A. Kiểm tra danh mục khớp từ khóa
      const matchedCategories = CATEGORIES.filter((c) => {
        const normKey = removeAccents(c.key);
        const normEn = removeAccents(c.en);
        const normVi = removeAccents(c.vi);
        const inKeywords = c.keywords.some((kw) => removeAccents(kw).includes(normQ) || normQ.includes(removeAccents(kw)));
        return normKey.includes(normQ) || normEn.includes(normQ) || normVi.includes(normQ) || inKeywords;
      });

      // B. Kiểm tra khoảng giá khớp từ khóa
      const matchedPrice = PRICE_PRESETS.find((p) => {
        return p.keywords.some((kw) => normQ.includes(removeAccents(kw)));
      });

      // C. Lọc sản phẩm khớp từ khóa (theo tên, danh mục, mô tả)
      const matchedProducts = CATALOG_PRODUCTS.filter((p) => {
        const normName = removeAccents(p.name);
        const normCat = removeAccents(p.category);
        const normDesc = removeAccents(p.description || "");
        return normName.includes(normQ) || normCat.includes(normQ) || normDesc.includes(normQ);
      });

      // Kiểm tra sản phẩm có trong Wishlist của trang WishList.html
      const wishlistCardIds = new Set();
      document.querySelectorAll(".wishlist-card[data-product-name]").forEach((el) => {
        const pName = el.getAttribute("data-product-name");
        if (pName) wishlistCardIds.add(removeAccents(pName));
      });

      let html = "";

      // Khối 1: Gợi ý Lọc theo Danh Mục nếu có
      if (matchedCategories.length > 0) {
        const cat = matchedCategories[0];
        const catName = isVi ? cat.vi : cat.en;
        html += `
          <div class="search-dropdown__section">
            <div class="search-dropdown__section-title">
              <span>🏷️ ${isVi ? "Gợi ý danh mục" : "Category Match"}</span>
            </div>
            <a href="${shopUrl}?category=${encodeURIComponent(cat.key)}" class="search-category-chip-link" data-index="0">
              <span class="search-chip-badge">${isVi ? "Danh mục" : "Category"}</span>
              <span class="search-chip-name">${escapeHtml(catName)}</span>
              <span class="search-chip-action">${isVi ? "Lọc ngay →" : "Filter now →"}</span>
            </a>
          </div>
        `;
      }

      // Khối 2: Gợi ý Lọc theo Khoảng Giá nếu người dùng gõ từ khóa liên quan đến giá
      if (matchedPrice) {
        const priceLabel = isVi ? matchedPrice.labelVi : matchedPrice.labelEn;
        const priceQuery = matchedPrice.max !== null
          ? `min=${matchedPrice.min}&max=${matchedPrice.max}`
          : `min=${matchedPrice.min}`;
        html += `
          <div class="search-dropdown__section">
            <div class="search-dropdown__section-title">
              <span>💰 ${isVi ? "Gợi ý khoảng giá" : "Price Range Match"}</span>
            </div>
            <a href="${shopUrl}?${priceQuery}" class="search-price-chip-link" data-index="0">
              <span class="search-chip-badge">${isVi ? "Khoảng giá" : "Price Range"}</span>
              <span class="search-chip-name">${escapeHtml(priceLabel)}</span>
              <span class="search-chip-action">${isVi ? "Áp dụng giá →" : "Apply price →"}</span>
            </a>
          </div>
        `;
      }

      // Khối 3: Danh sách sản phẩm gợi ý
      if (matchedProducts.length > 0) {
        const displayList = matchedProducts.slice(0, 5);
        html += `
          <div class="search-dropdown__section">
            <div class="search-dropdown__section-title">
              <span>📦 ${isVi ? "Sản phẩm tìm thấy" : "Products Found"} (${matchedProducts.length})</span>
            </div>
            <div class="search-dropdown__list">
        `;

        displayList.forEach((prod) => {
          const highlightedName = highlightMatch(prod.name, q);
          const isWishlisted = wishlistCardIds.has(removeAccents(prod.name));
          const catObj = CATEGORIES.find((c) => c.key === prod.category);
          const catLabel = catObj ? (isVi ? catObj.vi : catObj.en) : prod.category;
          const oldPriceHtml = prod.oldPrice ? `<span class="search-item__old-price">$${prod.oldPrice}</span>` : "";
          const wlBadge = isWishlisted
            ? `<span class="search-item__wl-badge">❤️ ${isVi ? "Trong Wishlist" : "In Wishlist"}</span>`
            : "";

          html += `
            <a href="${shopUrl}?q=${encodeURIComponent(prod.name)}" class="search-dropdown__item" data-id="${prod.id}">
              <img src="${prod.image}" alt="${escapeHtml(prod.name)}" class="search-item__thumb" onerror="this.src='${FALLBACK_IMAGE}'">
              <div class="search-item__info">
                <div class="search-item__name">${highlightedName}</div>
                <div class="search-item__meta">
                  <span class="search-item__category">${escapeHtml(catLabel)}</span>
                  ${wlBadge}
                </div>
              </div>
              <div class="search-item__price-box">
                <span class="search-item__price">$${prod.price}</span>
                ${oldPriceHtml}
              </div>
            </a>
          `;
        });

        html += `</div></div>`;

        // Footer xem toàn bộ kết quả trong Shop
        html += `
          <div class="search-dropdown__footer">
            <a href="${shopUrl}?q=${encodeURIComponent(q)}" class="search-dropdown__footer-link">
              <span>🔍 ${isVi ? `Xem tất cả ${matchedProducts.length} sản phẩm cho "${escapeHtml(q)}"` : `View all ${matchedProducts.length} products for "${escapeHtml(q)}"`}</span>
              <svg viewBox="0 0 24 24" class="search-arrow-icon"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </a>
          </div>
        `;
      } else {
        // Khối 4: Empty State khi không tìm thấy kết quả nào
        html += `
          <div class="search-dropdown__empty">
            <div class="search-dropdown__empty-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <circle cx="11" cy="11" r="7"></circle>
                <path d="m16 16 5 5"></path>
                <line x1="8" y1="11" x2="14" y2="11"></line>
              </svg>
            </div>
            <div class="search-dropdown__empty-title">
              ${isVi ? `Không tìm thấy kết quả cho "${escapeHtml(q)}"` : `No results found for "${escapeHtml(q)}"`}
            </div>
            <div class="search-dropdown__empty-desc">
              ${isVi ? "Hãy thử tìm bằng từ khóa chung hơn (ví dụ: Gamepad, Keyboard, Laptop, Gucci...) hoặc duyệt theo danh mục." : "Try searching with broader terms (e.g., Gamepad, Keyboard, Laptop...) or explore all products."}
            </div>
            <a href="${shopUrl}" class="search-dropdown__empty-btn">
              ${isVi ? "Khám phá tất cả sản phẩm trong Shop" : "Explore All Products in Shop"} →
            </a>
          </div>
        `;
      }

      dropdown.innerHTML = html;
      dropdown.style.display = "block";
      activeIndex = -1;
    }

    // Lắng nghe sự kiện gõ từ khóa (Debounce 150ms)
    searchInput.addEventListener("input", (e) => {
      const val = e.target.value;
      updateClearButton();

      // Nếu đang ở trang WishList.html, hỗ trợ lọc danh sách Wishlist trực tiếp trên trang
      if (document.querySelector(".wishlist-page")) {
        filterWishlistPage(val);
      }

      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        renderSuggestions(val);
      }, 150);
    });

    // Lắng nghe sự kiện focus
    searchInput.addEventListener("focus", () => {
      if (searchInput.value.trim()) {
        renderSuggestions(searchInput.value);
      }
    });

    // Phím điều hướng Up, Down, Enter, Escape
    searchInput.addEventListener("keydown", (e) => {
      const items = dropdown.querySelectorAll(".search-category-chip-link, .search-price-chip-link, .search-dropdown__item, .search-dropdown__footer-link");
      if (e.key === "ArrowDown") {
        if (dropdown.style.display === "block" && items.length > 0) {
          e.preventDefault();
          activeIndex = (activeIndex + 1) % items.length;
          items.forEach((item, idx) => item.classList.toggle("is-focused", idx === activeIndex));
          items[activeIndex].scrollIntoView({ block: "nearest" });
        }
      } else if (e.key === "ArrowUp") {
        if (dropdown.style.display === "block" && items.length > 0) {
          e.preventDefault();
          activeIndex = (activeIndex - 1 + items.length) % items.length;
          items.forEach((item, idx) => item.classList.toggle("is-focused", idx === activeIndex));
          items[activeIndex].scrollIntoView({ block: "nearest" });
        }
      } else if (e.key === "Enter") {
        if (dropdown.style.display === "block" && activeIndex >= 0 && items[activeIndex]) {
          e.preventDefault();
          items[activeIndex].click();
        } else {
          // Cho phép submit bình thường đến Shop.html?q=...
          closeDropdown();
        }
      } else if (e.key === "Escape") {
        closeDropdown();
      }
    });

    // Nút Clear ✕
    clearBtn.addEventListener("click", () => {
      searchInput.value = "";
      updateClearButton();
      closeDropdown();
      searchInput.focus();

      // Nếu ở trang WishList, khôi phục lại tất cả sản phẩm
      if (document.querySelector(".wishlist-page")) {
        filterWishlistPage("");
      }

      // Nếu ở trang Shop.html, đồng bộ với input trong trang và kích hoạt filter
      const shopInput = document.getElementById("shopSearchInput");
      if (shopInput) {
        shopInput.value = "";
        const shopClearBtn = document.getElementById("shopSearchClear");
        if (shopClearBtn) shopClearBtn.style.display = "none";
        shopInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });

    // Đóng dropdown khi click bên ngoài
    document.addEventListener("click", (e) => {
      if (!searchForm.contains(e.target)) {
        closeDropdown();
      }
    });

    // Lọc Wishlist trực tiếp trên trang WishList.html
    function filterWishlistPage(keyword) {
      const q = keyword.trim().toLowerCase();
      const normQ = removeAccents(q);
      const cards = document.querySelectorAll("#wishlistGrid .wishlist-card");
      const emptyState = document.getElementById("wishlistEmptyState");
      const grid = document.getElementById("wishlistGrid");
      if (!cards.length) return;

      let visibleCount = 0;
      cards.forEach((card) => {
        const name = card.getAttribute("data-product-name") || card.querySelector(".wishlist-card__title")?.textContent || "";
        const normName = removeAccents(name);
        const isMatch = !normQ || normName.includes(normQ);
        card.style.display = isMatch ? "" : "none";
        if (isMatch) visibleCount++;
      });

      const countBadge = document.getElementById("wishlistCount");
      if (countBadge) {
        countBadge.textContent = visibleCount;
      }

      if (emptyState && grid) {
        if (visibleCount === 0 && q) {
          grid.style.display = "none";
          emptyState.classList.add("is-visible");
          const titleEl = emptyState.querySelector(".empty-title");
          const descEl = emptyState.querySelector(".empty-desc");
          const isVi = getIsVi();
          if (titleEl) titleEl.textContent = isVi ? `Không có sản phẩm nào khớp với "${keyword}"` : `No wishlist items match "${keyword}"`;
          if (descEl) descEl.textContent = isVi ? "Hãy thử tìm bằng từ khóa khác hoặc xóa ô tìm kiếm để xem toàn bộ danh sách yêu thích." : "Try adjusting your search query or clear the search to view all items.";
        } else if (visibleCount > 0) {
          grid.style.display = "grid";
          emptyState.classList.remove("is-visible");
        }
      }
    }
  }

  // Khởi động khi DOM sẵn sàng
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHeaderSearchBar);
  } else {
    initHeaderSearchBar();
  }
})();
