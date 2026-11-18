(() => {
  const api = window.T1Api;
  if (!api) return;

  function showMessage(message, isError = true) {
    const target = document.getElementById("authError");
    if (!target) return;
    target.textContent = message;
    target.hidden = false;
    target.dataset.kind = isError ? "error" : "success";
  }

  function redirectAfterAuth(fallback) {
    const requested = new URLSearchParams(window.location.search).get("next");
    const allowed = new Set([
      "Shop.html", "Cart.html", "Checkout.html", "WishList.html", "E-CommerceHomePage.html",
    ]);
    window.location.href = allowed.has(requested) ? requested : fallback;
  }

  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = loginForm.querySelector('button[type="submit"]');
      if (button) button.disabled = true;
      try {
        const result = await api.post("/auth/login", {
          email: document.getElementById("loginEmail").value,
          password: document.getElementById("loginPassword").value,
        });
        api.setToken(result.access_token);
        redirectAfterAuth("Shop.html");
      } catch (error) {
        showMessage(error.message || "Không thể đăng nhập. Hãy thử lại.");
      } finally {
        if (button) button.disabled = false;
      }
    });
  }

  const signupForm = document.getElementById("signupForm");
  if (signupForm) {
    signupForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const password = document.getElementById("signupPassword").value;
      const confirmPassword = document.getElementById("confirmPassword").value;
      if (password !== confirmPassword) {
        showMessage("Mật khẩu xác nhận không khớp.");
        return;
      }
      const button = signupForm.querySelector('button[type="submit"]');
      if (button) button.disabled = true;
      try {
        const result = await api.post("/auth/register", {
          full_name: document.getElementById("signupName").value,
          email: document.getElementById("signupEmail").value,
          phone: document.getElementById("signupPhone").value,
          password,
        });
        api.setToken(result.access_token);
        redirectAfterAuth("Shop.html");
      } catch (error) {
        showMessage(error.message || "Không thể tạo tài khoản. Hãy thử lại.");
      } finally {
        if (button) button.disabled = false;
      }
    });
  }
})();
