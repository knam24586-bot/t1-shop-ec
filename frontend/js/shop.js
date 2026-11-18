/**
 * T1 Shop - Shop & Product Listing Page Interactions
 * Đáp ứng đầy đủ các tiêu chí chấp nhận:
 * 1. Hiển thị danh sách sản phẩm và trạng thái Rỗng (Empty State) / Loading (Skeleton)
 * 2. Phân trang (Pagination) và Tải thêm (Load More) hoạt động mượt mà
 * 3. Mở đúng Product Details Modal cho từng sản phẩm được click
 * 4. Fallback ảnh tự động khi ảnh lỗi
 * 5. Hỗ trợ song ngữ Anh - Việt đồng bộ với Header
 */

(() => {
  // SVG Data URI dự phòng chất lượng cao (không bao giờ lỗi)
  const FALLBACK_IMAGE = "data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22300%22%20height%3D%22300%22%20viewBox%3D%220%200%20300%20300%22%20fill%3D%22none%22%3E%3Crect%20width%3D%22300%22%20height%3D%22300%22%20fill%3D%22%23F5F5F5%22%2F%3E%3Cpath%20d%3D%22M150%20110c-16.57%200-30%2013.43-30%2030s13.43%2030%2030%2030%2030-13.43%2030-30-13.43-30-30-30zm0%2048c-9.94%200-18-8.06-18-18s8.06-18%2018-18%2018%208.06%2018%2018-8.06%2018-18%2018zm60-88H90c-11.05%200-20%208.95-20%2020v120c0%2011.05%208.95%2020%2020%2020h120c11.05%200%2020-8.95%2020-20V90c0-11.05-8.95-20-20-20zm8%20140c0%204.41-3.59%208-8%208H90c-4.41%200-8-3.59-8-8V90c0-4.41%203.59-8%208-8h120c4.41%200%208%203.59%208%208v120z%22%20fill%3D%22%23B0B0B0%22%2F%3E%3Ctext%20x%3D%22150%22%20y%3D%22225%22%20text-anchor%3D%22middle%22%20fill%3D%22%23888888%22%20font-family%3D%22sans-serif%22%20font-size%3D%2214%22%20font-weight%3D%22500%22%3EImage%20Not%20Available%3C%2Ftext%3E%3C%2Fsvg%3E";

  // Bộ dữ liệu sản phẩm mẫu phong phú từ tài nguyên ảnh của dự án
  const MOCK_PRODUCTS = [
    {
      id: 1,
      name: "Gucci duffle bag",
      category: "fashion",
      price: 960,
      oldPrice: 1160,
      discount: "-35%",
      badge: "-35%",
      badgeType: "sale",
      rating: 5.0,
      reviewsCount: 65,
      image: "../assets/images/products/Frame 606.png",
      stock: "In Stock",
      description: "Túi du lịch Gucci Duffle Bag phong cách thanh lịch, chất liệu da cao cấp chống thấm nước, khóa mạ vàng tinh tế, phù hợp cho mọi chuyến đi."
    },
    {
      id: 2,
      name: "RGB liquid CPU Cooler",
      category: "electronics",
      price: 1960,
      oldPrice: null,
      discount: null,
      badge: null,
      badgeType: null,
      rating: 4.8,
      reviewsCount: 42,
      image: "../assets/images/products/Frame 610.png",
      stock: "In Stock",
      description: "Bộ tản nhiệt nước AIO hiệu năng cao kèm đèn LED ARGB tùy biến, quạt tản nhiệt êm ái, tương thích hoàn hảo socket Intel & AMD mới nhất."
    },
    {
      id: 3,
      name: "GP11 Shooter USB Gamepad",
      category: "gaming",
      price: 550,
      oldPrice: null,
      discount: null,
      badge: null,
      badgeType: null,
      rating: 4.9,
      reviewsCount: 55,
      image: "../assets/images/products/GP11_PRD3 1.png",
      stock: "In Stock",
      description: "Tay cầm chơi game USB cổng đôi với bộ rung phản hồi lực chân thực, phím bấm êm tay, tối ưu cho game đua xe và bóng đá trên PC."
    },
    {
      id: 4,
      name: "Quilted Satin Jacket",
      category: "fashion",
      price: 750,
      oldPrice: null,
      discount: null,
      badge: null,
      badgeType: null,
      rating: 4.7,
      reviewsCount: 38,
      image: "../assets/images/products/698717_Z8A1X_3475_001_100_0000_Light-Reversible-quilted-satin-jacket 1.png",
      stock: "In Stock",
      description: "Áo khoác satin trần bông siêu nhẹ, thiết kế hai mặt tiện dụng, kiểu dáng bomber trẻ trung giữ ấm tuyệt vời trong mùa đông."
    },
    {
      id: 5,
      name: "ASUS FHD Gaming Laptop",
      category: "computers",
      price: 960,
      oldPrice: 1160,
      discount: "-35%",
      badge: "-35%",
      badgeType: "sale",
      rating: 5.0,
      reviewsCount: 65,
      image: "../assets/images/products/ideapad-gaming-3i-01-500x500 1.png",
      stock: "In Stock",
      description: "Laptop gaming ASUS màn hình 144Hz FHD sắc nét, vi xử lý Core i7 mạnh mẽ, card đồ họa RTX cân mọi tựa game AAA mượt mà."
    },
    {
      id: 6,
      name: "IPS LCD Gaming Monitor",
      category: "computers",
      price: 1160,
      oldPrice: null,
      discount: null,
      badge: null,
      badgeType: null,
      rating: 5.0,
      reviewsCount: 65,
      image: "../assets/images/products/Frame 613.png",
      stock: "In Stock",
      description: "Màn hình cong chuyên game tấm nền IPS chân thực, tần số quét 165Hz tốc độ phản hồi 1ms, hỗ trợ công nghệ chống xé hình G-Sync."
    },
    {
      id: 7,
      name: "HAVIT HV-G92 Gamepad",
      category: "gaming",
      price: 560,
      oldPrice: null,
      discount: null,
      badge: "NEW",
      badgeType: "new",
      rating: 5.0,
      reviewsCount: 65,
      image: "../assets/images/products/Frame 611.png",
      stock: "In Stock",
      description: "Tay cầm gamepad Havit phong cách Pro gaming, tích hợp cần analog 360 độ chính xác, phím bấm phản xạ tức thì, bảo hành 12 tháng."
    },
    {
      id: 8,
      name: "AK-900 Wired Keyboard",
      category: "gaming",
      price: 200,
      oldPrice: null,
      discount: null,
      badge: null,
      badgeType: null,
      rating: 5.0,
      reviewsCount: 65,
      image: "../assets/images/products/Frame 612 (1).png",
      stock: "In Stock",
      description: "Bàn phím cơ có dây AK-900 đèn nền LED Rainbow nhiều chế độ, keycap chống bám vân tay, độ bền lên tới 50 triệu lượt bấm."
    },
    {
      id: 9,
      name: "CANON EOS DSLR Camera",
      category: "electronics",
      price: 360,
      oldPrice: null,
      discount: null,
      badge: null,
      badgeType: null,
      rating: 4.8,
      reviewsCount: 95,
      image: "../assets/images/products/eos-250d-03-500x500 1.png",
      stock: "In Stock",
      description: "Máy ảnh kỹ thuật số Canon EOS cảm biến CMOS 24.1MP, hỗ trợ quay video 4K sắc nét, chống rung quang học, chụp lấy nét siêu tốc."
    },
    {
      id: 10,
      name: "Jr. Zoom Soccer Cleats",
      category: "sports",
      price: 1160,
      oldPrice: null,
      discount: null,
      badge: null,
      badgeType: null,
      rating: 5.0,
      reviewsCount: 35,
      image: "../assets/images/products/Copa_Sense 1.png",
      stock: "In Stock",
      description: "Giày đá bóng sân cỏ tự nhiên cao cấp, đệm khí Zoom Air trợ lực êm chân, đinh tán bám sân cực tốt cho các pha bứt tốc."
    },
    {
      id: 11,
      name: "Kids Electric Toy Car",
      category: "baby-toys",
      price: 960,
      oldPrice: null,
      discount: null,
      badge: "NEW",
      badgeType: "new",
      rating: 5.0,
      reviewsCount: 65,
      image: "../assets/images/products/New-Mercedes-Benz-Gtr-Licensed-Ride-on-Car-Kids-Electric-Toy-Car 1.png",
      stock: "In Stock",
      description: "Ô tô điện trẻ em Mercedes-Benz GTR bản quyền, 2 động cơ mạnh mẽ, điều khiển từ xa an toàn cho bé, đèn còi âm nhạc vui nhộn."
    },
    {
      id: 12,
      name: "Curology Product Set",
      category: "health-beauty",
      price: 500,
      oldPrice: null,
      discount: null,
      badge: null,
      badgeType: null,
      rating: 4.6,
      reviewsCount: 145,
      image: "../assets/images/products/curology-j7pKVQrTUsM-unsplash 1.png",
      stock: "In Stock",
      description: "Bộ mỹ phẩm chăm sóc da chuyên sâu Curology, thành phần thiên nhiên lành tính giúp dưỡng ẩm và ngăn ngừa lão hóa da hiệu quả."
    },
    {
      id: 13,
      name: "The North Coat",
      category: "fashion",
      price: 260,
      oldPrice: 360,
      discount: "-28%",
      badge: "-28%",
      badgeType: "sale",
      rating: 4.9,
      reviewsCount: 72,
      image: "../assets/images/products/Frame 605.png",
      stock: "In Stock",
      description: "Áo khoác gió thể thao The North công nghệ Gore-Tex chống mưa bão tuyệt đối, mũ trùm điều chỉnh thông minh, giữ nhiệt tối đa."
    },
    {
      id: 14,
      name: "S-Series Comfort Chair",
      category: "home-lifestyle",
      price: 375,
      oldPrice: 400,
      discount: "-10%",
      badge: "-10%",
      badgeType: "sale",
      rating: 4.7,
      reviewsCount: 99,
      image: "../assets/images/products/Frame 614.png",
      stock: "In Stock",
      description: "Ghế công thái học S-Series đệm lưới thoáng khí, ngả lưng 135 độ thư giãn, bảo vệ cột sống tuyệt đối cho người ngồi làm việc lâu."
    },
    {
      id: 15,
      name: "Small BookShelf",
      category: "home-lifestyle",
      price: 360,
      oldPrice: null,
      discount: null,
      badge: null,
      badgeType: null,
      rating: 4.9,
      reviewsCount: 80,
      image: "../assets/images/products/Frame 612.png",
      stock: "In Stock",
      description: "Kệ sách gỗ công nghiệp cao cấp chống ẩm mốc, thiết kế 4 tầng thông minh tối ưu không gian sống cho phòng khách và phòng làm việc."
    },
    {
      id: 16,
      name: "Breed Dry Dog Food",
      category: "groceries",
      price: 100,
      oldPrice: null,
      discount: null,
      badge: null,
      badgeType: null,
      rating: 4.8,
      reviewsCount: 35,
      image: "../assets/images/products/71RdoeXxtrL 1.png",
      stock: "In Stock",
      description: "Thức ăn hạt dinh dưỡng cao cấp cho chó lớn, bổ sung đầy đủ vitamin và khoáng chất giúp xương chắc khỏe và lông mượt mà."
    },
    {
      id: 17,
      name: "JBL Wireless Speaker",
      category: "electronics",
      price: 450,
      oldPrice: 520,
      discount: "-15%",
      badge: "-15%",
      badgeType: "sale",
      rating: 5.0,
      reviewsCount: 110,
      image: "../assets/images/products/Frame 694.png",
      stock: "In Stock",
      description: "Loa Bluetooth không dây JBL âm trầm sống động, pin nghe nhạc liên tục 12 tiếng, chuẩn kháng nước IPX7 thoải mái tiệc tùng bãi biển."
    }
  ];

  // Khởi tạo trang Shop
  function initShopPage() {
    // State quản lý trang Shop
    let allProducts = [...MOCK_PRODUCTS];
    let filteredProducts = [...MOCK_PRODUCTS];
    let currentPage = 1;
    const pageSize = 8; // 8 sản phẩm / trang -> Tạo ra 3 trang để demo phân trang rõ ràng
    let currentCategory = "all";
    let searchQuery = "";
    let sortBy = "featured";
    let isLoading = false;
    let isForcedEmpty = false;

    // DOM Elements
    const gridContainer = document.getElementById("shopGrid");
    const gridItemsContainer = document.getElementById("shopGridItems");
    const skeletonContainer = document.getElementById("shopSkeleton");
    const emptyStateEl = document.getElementById("shopEmptyState");
    const emptyResetBtn = document.getElementById("shopEmptyResetBtn");
    const productCountEl = document.getElementById("shopProductCount");
    const paginationContainer = document.getElementById("shopPagination");
    const loadMoreContainer = document.getElementById("shopLoadMore");
    const loadMoreBtn = document.getElementById("loadMoreBtn");
    const categoryBtns = document.querySelectorAll(".shop-cat-btn");
    const searchInput = document.getElementById("shopSearchInput");
    const sortSelect = document.getElementById("shopSortSelect");

    // Demo control buttons
    const demoLoadingBtn = document.getElementById("demoToggleLoading");
    const demoEmptyBtn = document.getElementById("demoToggleEmpty");

    // Modal elements
    const detailModal = document.getElementById("shopProductDetailModal");
    const modalImg = document.getElementById("modalProductImg");
    const modalTitle = document.getElementById("modalProductTitle");
    const modalBadge = document.getElementById("modalBadge");
    const modalStars = document.getElementById("modalProductStars");
    const modalReviews = document.getElementById("modalProductReviews");
    const modalStock = document.getElementById("modalProductStock");
    const modalPrice = document.getElementById("modalProductPrice");
    const modalOldPrice = document.getElementById("modalProductOldPrice");
    const modalDesc = document.getElementById("modalProductDesc");
    const modalQtyInput = document.getElementById("modalQtyInput");
    const modalQtyMinus = document.getElementById("modalQtyMinus");
    const modalQtyPlus = document.getElementById("modalQtyPlus");
    const modalAddCartBtn = document.getElementById("modalAddCartBtn");
    const modalFavBtn = document.getElementById("modalFavBtn");

    // Toast element
    const toastEl = document.getElementById("shopToast");
    const toastMsgEl = toastEl ? toastEl.querySelector(".shop-toast-msg") : null;
    let toastTimer = null;
    let currentModalProduct = null;

    function formatPrice(product) {
      if (product?.isBackendProduct) {
        return new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(Number(product.price));
      }
      return `$${product?.price ?? 0}`;
    }

    function showToast(message) {
      if (!toastEl || !toastMsgEl) return;
      toastMsgEl.textContent = message;
      toastEl.classList.add("is-show");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => {
        toastEl.classList.remove("is-show");
      }, 2500);
    }

    // Xử lý fallback cho ảnh lỗi
    function setupImageFallback(img) {
      if (!img) return;
      img.addEventListener("error", function () {
        if (this.dataset.fallbackApplied === "final") return;
        if (this.dataset.fallbackApplied === "alt-path") {
          this.dataset.fallbackApplied = "final";
          this.src = FALLBACK_IMAGE;
          this.classList.add("is-fallback");
          return;
        }
        this.dataset.fallbackApplied = "alt-path";
        if (this.src.includes("/frontend/assets/")) {
          this.src = this.src.replace(/.*\/frontend\/assets\//, "../assets/");
        } else if (this.src.includes("../assets/")) {
          this.src = this.src.replace(/.*\/assets\//, "/frontend/assets/");
        } else {
          this.src = FALLBACK_IMAGE;
          this.classList.add("is-fallback");
        }
      });

      if (img.complete && img.naturalWidth === 0) {
        img.dataset.fallbackApplied = "final";
        img.src = FALLBACK_IMAGE;
        img.classList.add("is-fallback");
      }
    }

    // Thử kết nối API backend nếu server đang chạy (không chặn UI nếu offline)
    async function tryFetchBackendProducts() {
      try {
        const data = await window.T1Api.get("/products");
        if (Array.isArray(data)) {
          allProducts = data.map((item, idx) => ({
              id: item.id || idx + 1,
              name: item.name || "Sản phẩm",
              category: "electronics",
              price: Number(item.price) || 100,
              oldPrice: null,
              discount: null,
              badge: null,
              badgeType: null,
              rating: item.rating ? Number(item.rating) : 5.0,
              reviewsCount: 0,
              image: item.image_url || `../assets/images/products/Frame 60${(idx % 6) + 5}.png`,
              stock: Number(item.stock) || 0,
              description: item.description || "Sản phẩm chất lượng cao chính hãng từ T1 Shop.",
              isBackendProduct: true,
            }));
          applyFilterAndSort();
        }
      } catch (e) {
        // Backend không mở -> tự động dùng MOCK_PRODUCTS mượt mà
      }
    }

    // Lọc và sắp xếp sản phẩm
    function applyFilterAndSort() {
      if (isForcedEmpty) {
        filteredProducts = [];
        render();
        return;
      }

      let list = [...allProducts];

      // Lọc danh mục
      if (currentCategory && currentCategory !== "all") {
        list = list.filter((p) => p.category === currentCategory);
      }

      // Lọc tìm kiếm
      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        list = list.filter((p) => p.name.toLowerCase().includes(q) || (p.description && p.description.toLowerCase().includes(q)));
      }

      // Sắp xếp
      if (sortBy === "price-low") {
        list.sort((a, b) => a.price - b.price);
      } else if (sortBy === "price-high") {
        list.sort((a, b) => b.price - a.price);
      } else if (sortBy === "rating") {
        list.sort((a, b) => b.rating - a.rating);
      } else if (sortBy === "name-asc") {
        list.sort((a, b) => a.name.localeCompare(b.name));
      }

      filteredProducts = list;
      currentPage = 1; // Reset về trang 1 khi lọc
      render();
    }

    // Tạo HTML cho 1 Product Card
    function renderCard(product) {
      const isVi = document.documentElement.lang === "vi";
      const badgeHtml = product.badge
        ? `<span class="shop-card__badge ${product.badgeType === 'new' ? 'shop-card__badge--new' : 'shop-card__badge--sale'}">${product.badge}</span>`
        : "";
      const oldPriceHtml = product.oldPrice
        ? `<span class="shop-card__old-price">${formatPrice({ ...product, price: product.oldPrice })}</span>`
        : "";

      return `
        <article class="shop-card" data-id="${product.id}">
          <div class="shop-card__thumb" data-action="open-detail">
            ${badgeHtml}
            <div class="shop-card__actions">
              <button class="shop-action-btn" type="button" aria-label="Yêu thích" data-action="toggle-wishlist">
                <svg viewBox="0 0 24 24"><path d="M20.8 8.8c0 5.1-8.8 11-8.8 11s-8.8-5.9-8.8-11A4.8 4.8 0 0 1 12 6.1a4.8 4.8 0 0 1 8.8 2.7Z"/></svg>
              </button>
              <button class="shop-action-btn" type="button" aria-label="Xem chi tiết" data-action="quick-view">
                <svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
            </div>
            <img src="${product.image}" alt="${product.name}" loading="lazy">
            <button class="shop-card__add-cart" type="button" data-action="add-cart">
              <svg viewBox="0 0 24 24"><path d="M2.5 3h2.3l2.1 12.1a2 2 0 0 0 2 1.7h9.8a2 2 0 0 0 1.9-1.5L22 7H5.1"/><circle cx="9" cy="20" r="1.2"/><circle cx="18" cy="20" r="1.2"/></svg>
              <span class="btn-cart-text">${isVi ? "Thêm Vào Giỏ Hàng" : "Add To Cart"}</span>
            </button>
          </div>
          <div class="shop-card__details">
            <h3 class="shop-card__name" data-action="open-detail">${product.name}</h3>
            <div class="shop-card__pricing">
              <span class="shop-card__price">${formatPrice(product)}</span>
              ${oldPriceHtml}
            </div>
            <div class="shop-card__rating">
              <span class="shop-stars">
                ${'<svg viewBox="0 0 24 24"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>'.repeat(5)}
              </span>
              <span class="shop-reviews-count">(${product.reviewsCount})</span>
            </div>
          </div>
        </article>
      `;
    }

    // Hiển thị giao diện danh sách và thanh phân trang (Tiêu chí 1 & 2)
    function render(isAppend = false) {
      const isVi = document.documentElement.lang === "vi";
      const totalItems = filteredProducts.length;
      const totalPages = Math.ceil(totalItems / pageSize) || 1;

      // Cập nhật đếm số sản phẩm
      if (productCountEl) {
        if (totalItems === 0) {
          productCountEl.textContent = isVi ? "(0 sản phẩm)" : "(0 products)";
        } else {
          const start = (currentPage - 1) * pageSize + 1;
          const end = Math.min(currentPage * pageSize, totalItems);
          productCountEl.textContent = isVi
            ? `(Hiển thị ${start}–${end} trong ${totalItems} sản phẩm)`
            : `(Showing ${start}–${end} of ${totalItems} products)`;
        }
      }

      // 1. Kiểm tra trạng thái rỗng (Empty State)
      if (totalItems === 0) {
        if (gridItemsContainer) gridItemsContainer.innerHTML = "";
        if (emptyStateEl) emptyStateEl.classList.add("is-visible");
        if (paginationContainer) paginationContainer.style.display = "none";
        if (loadMoreContainer) loadMoreContainer.style.display = "none";
        return;
      }

      if (emptyStateEl) emptyStateEl.classList.remove("is-visible");

      // 2. Cắt dữ liệu theo trang
      const startIndex = isAppend ? 0 : (currentPage - 1) * pageSize;
      const endIndex = currentPage * pageSize;
      const pageItems = filteredProducts.slice(startIndex, endIndex);

      // Render cards
      if (gridItemsContainer) {
        gridItemsContainer.innerHTML = pageItems.map(renderCard).join("");
        gridItemsContainer.querySelectorAll("img").forEach(setupImageFallback);
      }

      // 3. Render thanh phân trang số (Pagination: 1, 2, 3...)
      if (paginationContainer) {
        if (totalPages <= 1) {
          paginationContainer.style.display = "none";
        } else {
          paginationContainer.style.display = "flex";
          let pagHtml = `
            <button class="page-btn page-btn--prev" type="button" aria-label="Trang trước" ${currentPage === 1 ? 'disabled' : ''} data-page="${currentPage - 1}">
              <svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg>
            </button>
          `;

          for (let p = 1; p <= totalPages; p++) {
            pagHtml += `
              <button class="page-btn ${p === currentPage ? 'is-active' : ''}" type="button" data-page="${p}">${p}</button>
            `;
          }

          pagHtml += `
            <button class="page-btn page-btn--next" type="button" aria-label="Trang sau" ${currentPage === totalPages ? 'disabled' : ''} data-page="${currentPage + 1}">
              <svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>
            </button>
          `;
          paginationContainer.innerHTML = pagHtml;
        }
      }

      // 4. Render nút Tải thêm (Load More)
      if (loadMoreContainer && loadMoreBtn) {
        if (currentPage >= totalPages || totalPages <= 1) {
          loadMoreContainer.style.display = "none";
        } else {
          loadMoreContainer.style.display = "flex";
          const remaining = totalItems - currentPage * pageSize;
          const loadMoreText = loadMoreBtn.querySelector(".load-more-text");
          if (loadMoreText) {
            loadMoreText.textContent = isVi
              ? `Tải Thêm Sản Phẩm (Còn ${remaining})`
              : `Load More Products (${remaining} remaining)`;
          }
        }
      }
    }

    // Chuyển trang có hiệu ứng Loading Skeleton mượt mà
    function goToPage(page) {
      const totalPages = Math.ceil(filteredProducts.length / pageSize) || 1;
      if (page < 1 || page > totalPages || page === currentPage) return;

      setLoading(true);
      currentPage = page;

      setTimeout(() => {
        setLoading(false);
        render();
        // Cuộn mượt về đầu danh sách sản phẩm
        const shopHeader = document.querySelector(".shop-header");
        if (shopHeader) {
          shopHeader.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }, 350);
    }

    // Bật/tắt trạng thái Loading (Skeleton)
    function setLoading(loading) {
      isLoading = loading;
      if (gridContainer) {
        gridContainer.classList.toggle("is-loading", loading);
      }
    }

    // Mở Product Details Modal (Tiêu chí 3)
    function openProductDetails(product) {
      if (!detailModal || !product) return;
      const isVi = document.documentElement.lang === "vi";
      currentModalProduct = product;

      modalTitle.textContent = product.name;
      modalPrice.textContent = formatPrice(product);

      if (product.oldPrice) {
        modalOldPrice.textContent = formatPrice({ ...product, price: product.oldPrice });
        modalOldPrice.style.display = "inline";
      } else {
        modalOldPrice.style.display = "none";
      }

      if (product.badge) {
        modalBadge.textContent = product.badge;
        modalBadge.className = `shop-card__badge product-modal__badge ${product.badgeType === 'new' ? 'shop-card__badge--new' : 'shop-card__badge--sale'}`;
        modalBadge.style.display = "inline-block";
      } else {
        modalBadge.style.display = "none";
      }

      const hasStock = !product.isBackendProduct || Number(product.stock) > 0;
      modalStock.textContent = hasStock
        ? (isVi ? `Còn hàng (${product.stock})` : `In Stock (${product.stock})`)
        : (isVi ? "Hết hàng" : "Out of stock");
      modalDesc.textContent = isVi
        ? `Sản phẩm ${product.name} chính hãng chất lượng cao, thiết kế đón đầu xu hướng với độ bền vượt trội. Được bảo hành chính hãng 12 tháng tại hệ thống T1 Shop.`
        : `Authentic ${product.name} designed with premium quality and performance. Backed by 100% genuine warranty from T1 Shop.`;

      modalImg.src = product.image;
      modalImg.alt = product.name;
      delete modalImg.dataset.fallbackApplied;
      modalImg.classList.remove("is-fallback");

      if (modalQtyInput) modalQtyInput.value = 1;

      detailModal.classList.add("is-open");
      detailModal.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    }

    function closeProductDetails() {
      if (!detailModal) return;
      detailModal.classList.remove("is-open");
      detailModal.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
    }

    async function addToCart(product, quantity = 1) {
      const isVi = document.documentElement.lang === "vi";
      if (!product?.isBackendProduct) {
        showToast(isVi ? "Sản phẩm mẫu chưa có trong cơ sở dữ liệu." : "This demo product is not in the database.");
        return false;
      }
      if (!window.T1Api.getToken()) {
        window.location.href = "./Login.html?next=Shop.html";
        return false;
      }
      try {
        const result = await window.T1Api.post("/cart/items", {
          product_id: product.id,
          quantity: Number(quantity),
        });
        const cartLink = document.querySelector('.icon-link[aria-label="Giỏ hàng"]');
        if (cartLink) cartLink.title = `${result.cart.total_items} sản phẩm trong giỏ`;
        showToast(isVi ? `Đã thêm "${product.name}" vào giỏ hàng.` : `Added "${product.name}" to cart.`);
        return true;
      } catch (error) {
        if (error.status === 401) {
          window.T1Api.clearToken();
          window.location.href = "./Login.html?next=Shop.html";
          return false;
        }
        showToast(error.message || (isVi ? "Không thể thêm sản phẩm vào giỏ." : "Could not add this item."));
        return false;
      }
    }

    // ========================================================
    // SỰ KIỆN TƯƠNG TÁC
    // ========================================================

    // Click nút phân trang
    if (paginationContainer) {
      paginationContainer.addEventListener("click", (e) => {
        const btn = e.target.closest(".page-btn");
        if (btn && !btn.disabled) {
          const targetPage = parseInt(btn.getAttribute("data-page"), 10);
          if (targetPage) goToPage(targetPage);
        }
      });
    }

    // Click nút Tải thêm (Load More)
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener("click", () => {
        loadMoreBtn.classList.add("is-loading");
        loadMoreBtn.disabled = true;

        setTimeout(() => {
          currentPage += 1;
          render(true); // Hiển thị tiếp các sản phẩm
          loadMoreBtn.classList.remove("is-loading");
          loadMoreBtn.disabled = false;
          const isVi = document.documentElement.lang === "vi";
          showToast(isVi ? "Đã tải thêm sản phẩm mới!" : "Loaded more products!");
        }, 400);
      });
    }

    // Bấm xem chi tiết hoặc tương tác trên card sản phẩm
    if (gridItemsContainer) {
      gridItemsContainer.addEventListener("click", (e) => {
        const card = e.target.closest(".shop-card");
        if (!card) return;

        const productId = parseInt(card.getAttribute("data-id"), 10);
        const product = allProducts.find((p) => p.id === productId);
        if (!product) return;

        // Bấm nút yêu thích
        const wishBtn = e.target.closest('[data-action="toggle-wishlist"]');
        if (wishBtn) {
          e.preventDefault();
          e.stopPropagation();
          if (!window.T1Api.getToken()) {
            window.location.href = "./Login.html?next=Shop.html";
            return;
          }
          const active = wishBtn.classList.contains("is-active");
          const action = active
            ? window.T1Api.delete(`/wishlist/products/${product.id}`)
            : window.T1Api.post("/wishlist", { product_id: product.id });
          action.then(() => {
            wishBtn.classList.toggle("is-active", !active);
            showToast(active ? "Đã xóa khỏi danh sách yêu thích." : "Đã thêm vào danh sách yêu thích.");
          }).catch((error) => showToast(error.message || "Không thể cập nhật danh sách yêu thích."));
          return;
        }

        // Bấm nút thêm vào giỏ hàng
        const addCartBtn = e.target.closest('[data-action="add-cart"]');
        if (addCartBtn) {
          e.preventDefault();
          e.stopPropagation();
          void addToCart(product, 1);
          return;
        }

        // Bấm Quick View, Ảnh hoặc Tên sản phẩm -> Mở Product Details Modal (Tiêu chí 3)
        const openDetailTrigger = e.target.closest('[data-action="open-detail"]') || e.target.closest('[data-action="quick-view"]');
        if (openDetailTrigger) {
          e.preventDefault();
          openProductDetails(product);
        }
      });
    }

    // Bộ lọc danh mục (Pills)
    categoryBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        categoryBtns.forEach((b) => b.classList.remove("is-active"));
        btn.classList.add("is-active");
        currentCategory = btn.getAttribute("data-category") || "all";
        isForcedEmpty = false;
        if (demoEmptyBtn) demoEmptyBtn.classList.remove("is-active");

        setLoading(true);
        setTimeout(() => {
          setLoading(false);
          applyFilterAndSort();
        }, 250);
      });
    });

    // Tìm kiếm sản phẩm
    if (searchInput) {
      let searchDebounce = null;
      searchInput.addEventListener("input", (e) => {
        clearTimeout(searchDebounce);
        searchDebounce = setTimeout(() => {
          searchQuery = e.target.value;
          isForcedEmpty = false;
          if (demoEmptyBtn) demoEmptyBtn.classList.remove("is-active");
          applyFilterAndSort();
        }, 200);
      });
    }

    // Sắp xếp
    if (sortSelect) {
      sortSelect.addEventListener("change", (e) => {
        sortBy = e.target.value;
        setLoading(true);
        setTimeout(() => {
          setLoading(false);
          applyFilterAndSort();
        }, 200);
      });
    }

    // Nút Reset ở Empty State
    if (emptyResetBtn) {
      emptyResetBtn.addEventListener("click", () => {
        isForcedEmpty = false;
        if (demoEmptyBtn) demoEmptyBtn.classList.remove("is-active");
        currentCategory = "all";
        searchQuery = "";
        if (searchInput) searchInput.value = "";
        categoryBtns.forEach((b) => b.classList.toggle("is-active", b.getAttribute("data-category") === "all"));
        applyFilterAndSort();
      });
    }

    // Demo Button: Thử nghiệm bật/tắt Loading Skeleton
    if (demoLoadingBtn) {
      demoLoadingBtn.addEventListener("click", () => {
        const nextState = !isLoading;
        setLoading(nextState);
        demoLoadingBtn.classList.toggle("is-active", nextState);
        if (nextState) {
          // Tự tắt sau 3 giây để tiện quan sát
          setTimeout(() => {
            setLoading(false);
            demoLoadingBtn.classList.remove("is-active");
          }, 3000);
        }
      });
    }

    // Demo Button: Thử nghiệm bật/tắt Trạng thái Rỗng (Empty State)
    if (demoEmptyBtn) {
      demoEmptyBtn.addEventListener("click", () => {
        isForcedEmpty = !isForcedEmpty;
        demoEmptyBtn.classList.toggle("is-active", isForcedEmpty);
        applyFilterAndSort();
      });
    }

    // Điều khiển trong Product Details Modal
    if (modalQtyMinus && modalQtyInput) {
      modalQtyMinus.addEventListener("click", () => {
        let v = parseInt(modalQtyInput.value, 10) || 1;
        if (v > 1) modalQtyInput.value = v - 1;
      });
    }

    if (modalQtyPlus && modalQtyInput) {
      modalQtyPlus.addEventListener("click", () => {
        let v = parseInt(modalQtyInput.value, 10) || 1;
        if (v < 99) modalQtyInput.value = v + 1;
      });
    }

    if (modalFavBtn) {
      modalFavBtn.addEventListener("click", function () {
        const active = this.classList.toggle("is-active");
        const isVi = document.documentElement.lang === "vi";
        showToast(active
          ? (isVi ? "Đã lưu vào mục yêu thích!" : "Added to wishlist favorites!")
          : (isVi ? "Đã bỏ lưu khỏi mục yêu thích!" : "Removed from wishlist favorites!"));
      });
    }

    if (modalAddCartBtn) {
      modalAddCartBtn.addEventListener("click", async () => {
        const qty = modalQtyInput ? modalQtyInput.value : 1;
        const added = await addToCart(currentModalProduct, qty);
        if (added) closeProductDetails();
      });
    }

    // Đóng Modal (Nút X hoặc click overlay)
    document.addEventListener("click", (e) => {
      if (e.target.closest('[data-action="close-modal"]')) {
        e.preventDefault();
        closeProductDetails();
      }
    });

    // Đóng Modal bằng phím ESC
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && detailModal && detailModal.classList.contains("is-open")) {
        closeProductDetails();
      }
    });

    // Đồng bộ đa ngôn ngữ (EN <-> VI)
    function applyShopLanguage(lang) {
      const isVi = lang === "vi";

      // Tiêu đề
      const titleEl = document.getElementById("shopPageTitle");
      if (titleEl) titleEl.textContent = isVi ? "Danh Sách Sản Phẩm" : "Explore Our Products";

      const bcShop = document.getElementById("breadcrumbShop");
      if (bcShop) bcShop.textContent = isVi ? "Cửa Hàng" : "Shop";

      const bcCur = document.getElementById("breadcrumbCurrent");
      if (bcCur) bcCur.textContent = isVi ? "Tất Cả Sản Phẩm" : "All Products";

      // Placeholder tìm kiếm
      if (searchInput) {
        searchInput.placeholder = isVi ? "Tìm kiếm sản phẩm..." : "Search products...";
      }

      // Dropdown sort
      if (sortSelect) {
        sortSelect.options[0].text = isVi ? "Nổi bật" : "Featured";
        sortSelect.options[1].text = isVi ? "Giá: Thấp đến Cao" : "Price: Low to High";
        sortSelect.options[2].text = isVi ? "Giá: Cao đến Thấp" : "Price: High to Low";
        sortSelect.options[3].text = isVi ? "Đánh giá cao nhất" : "Highest Rated";
      }

      // Empty state
      const emptyTitle = document.getElementById("shopEmptyTitle");
      if (emptyTitle) emptyTitle.textContent = isVi ? "Không tìm thấy sản phẩm nào" : "No products found";

      const emptyDesc = document.getElementById("shopEmptyDesc");
      if (emptyDesc) emptyDesc.textContent = isVi ? "Hãy thử điều chỉnh bộ lọc hoặc từ khóa tìm kiếm của bạn để khám phá thêm." : "Try adjusting your search or filter to find what you are looking for.";

      const emptyBtn = document.getElementById("shopEmptyResetBtn");
      if (emptyBtn) emptyBtn.textContent = isVi ? "Xem Tất Cả Sản Phẩm" : "View All Products";

      // Modal add to cart
      const modalCartSpan = document.getElementById("modalAddCartText");
      if (modalCartSpan) modalCartSpan.textContent = isVi ? "Thêm vào giỏ" : "Add To Cart";

      render();
    }

    // Quan sát thay đổi ngôn ngữ trên thẻ <html>
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((m) => {
        if (m.type === "attributes" && m.attributeName === "lang") {
          applyShopLanguage(document.documentElement.lang);
        }
      });
    });
    observer.observe(document.documentElement, { attributes: true });

    // Khởi tạo ban đầu
    const initialLang = document.documentElement.lang || localStorage.getItem("t1_selected_lang") || "en";
    applyShopLanguage(initialLang);
    tryFetchBackendProducts();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initShopPage);
  } else {
    initShopPage();
  }
})();
