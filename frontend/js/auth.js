(function () {
  "use strict";

  const api = window.T1ShopAuth;
  const message = document.getElementById("authMessage");
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("signupForm");

  function showMessage(text, kind) {
    if (!message) return;
    message.textContent = text;
    message.classList.toggle("auth-message--error", kind === "error");
    message.classList.toggle("auth-message--success", kind === "success");
  }

  async function getErrorMessage(response) {
    let body;
    try { body = await response.json(); }
    catch (_) { return "Không thể kết nối tới máy chủ. Hãy thử lại."; }

    const error = body && body.error;
    if (error && Array.isArray(error.details) && error.details.length) {
      return error.details.map(function (item) { return item.message; }).join(" ");
    }
    if (error && error.message) return error.message;
    if (body && typeof body.detail === "string") return body.detail;
    return "Yêu cầu không thành công. Hãy kiểm tra thông tin và thử lại.";
  }

  function setBusy(form, busy) {
    const button = form.querySelector('button[type="submit"]');
    if (!button) return;
    button.disabled = busy;
    button.setAttribute("aria-busy", String(busy));
  }

  if (loginForm) {
    const params = new URLSearchParams(window.location.search);
    if (params.get("registered") === "1") {
      showMessage("Tạo tài khoản thành công. Hãy đăng nhập để tiếp tục.", "success");
    } else if (params.get("expired") === "1") {
      showMessage("Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.", "error");
    } else if (params.get("auth") === "required") {
      showMessage("Vui lòng đăng nhập để tiếp tục.", "error");
    } else if (params.get("logged_out") === "1") {
      showMessage("Bạn đã đăng xuất thành công.", "success");
    }

    loginForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      const identifier = document.getElementById("loginEmail").value.trim();
      const password = document.getElementById("loginPassword").value;
      if (!identifier || !password) {
        showMessage("Vui lòng nhập đầy đủ email/số điện thoại và mật khẩu.", "error");
        return;
      }
      showMessage("Đang đăng nhập…", "");
      setBusy(loginForm, true);
      try {
        const response = await fetch(api.apiBase + "/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ identifier: identifier, password: password })
        });
        if (!response.ok) throw new Error(await getErrorMessage(response));
        const result = await response.json();
        api.saveSession(result.access_token, result.user);
        showMessage("Đăng nhập thành công. Đang chuyển trang…", "success");
        window.setTimeout(function () { window.location.assign("./myAccount.html"); }, 350);
      } catch (error) {
        showMessage(error.message || "Không thể đăng nhập. Hãy thử lại.", "error");
      } finally {
        setBusy(loginForm, false);
      }
    });
  }

  if (registerForm) {
    registerForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      const fullName = document.getElementById("signupName").value.trim();
      const email = document.getElementById("signupEmail").value.trim();
      const phone = document.getElementById("signupPhone").value.trim();
      const password = document.getElementById("signupPassword").value;
      const confirmPassword = document.getElementById("confirmPassword").value;

      if (fullName.length < 2) {
        showMessage("Họ tên phải có ít nhất 2 ký tự.", "error");
        return;
      }
      if (!email || !email.includes("@")) {
        showMessage("Email không đúng định dạng.", "error");
        return;
      }
      if (!phone) {
        showMessage("Số điện thoại không được để trống.", "error");
        return;
      }
      if (password.length < 8) {
        showMessage("Mật khẩu phải có ít nhất 8 ký tự.", "error");
        return;
      }
      if (password !== confirmPassword) {
        showMessage("Mật khẩu xác nhận không khớp.", "error");
        return;
      }

      const payload = {
        full_name: fullName,
        email: email,
        phone: phone,
        password: password
      };
      showMessage("Đang tạo tài khoản…", "");
      setBusy(registerForm, true);
      try {
        const response = await fetch(api.apiBase + "/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (!response.ok) throw new Error(await getErrorMessage(response));
        window.location.assign("./Login.html?registered=1");
      } catch (error) {
        showMessage(error.message || "Không thể tạo tài khoản. Hãy thử lại.", "error");
      } finally {
        setBusy(registerForm, false);
      }
    });
  }

  window.addEventListener("t1shop:session-expired", function () {
    showMessage("Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.", "error");
  });
})();
