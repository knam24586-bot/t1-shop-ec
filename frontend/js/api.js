(() => {
  const baseUrl = window.T1_API_BASE_URL || "http://127.0.0.1:8000/api";
  const tokenKey = "t1shop_access_token";

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (options.body !== undefined && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    const token = sessionStorage.getItem(tokenKey);
    if (token) headers.set("Authorization", `Bearer ${token}`);

    const response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers,
      body: options.body === undefined || options.body instanceof FormData
        ? options.body
        : JSON.stringify(options.body),
    });
    const text = await response.text();
    let payload = null;
    try { payload = text ? JSON.parse(text) : null; } catch { payload = text; }
    if (!response.ok) {
      const detail = payload && typeof payload === "object" ? payload.detail : null;
      const error = new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  window.T1Api = {
    getToken: () => sessionStorage.getItem(tokenKey),
    setToken: (token) => sessionStorage.setItem(tokenKey, token),
    clearToken: () => sessionStorage.removeItem(tokenKey),
    get: (path) => request(path),
    post: (path, body) => request(path, { method: "POST", body }),
    put: (path, body) => request(path, { method: "PUT", body }),
    patch: (path, body) => request(path, { method: "PATCH", body }),
    delete: (path) => request(path, { method: "DELETE" }),
  };
})();
