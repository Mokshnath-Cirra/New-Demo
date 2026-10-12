/* AURA AI - authenticated REST client */
const API = (() => {
  const base = window.AURA_API_BASE || "";
  const TOKEN_KEY = "aura_token";
  let token = localStorage.getItem(TOKEN_KEY) || "";
  let onAuthRequired = () => {};

  async function request(path, options = {}) {
    const headers = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    let res;
    try {
      res = await fetch(base + path, { ...options, headers });
    } catch (err) {
      throw new Error("Cannot reach the AURA server. Check that the backend is running.");
    }
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) onAuthRequired();
    if (!res.ok) {
      const error = new Error(data.message || `Request failed (${res.status})`);
      error.status = res.status;
      throw error;
    }
    return data;
  }
  const post = (path, body) => request(path, { method: "POST", body: JSON.stringify(body) });

  return {
    setAuthHandler: (fn) => { onAuthRequired = fn; },
    isSignedIn: () => Boolean(token),
    signOut: () => { token = ""; localStorage.removeItem(TOKEN_KEY); },
    async login(username, password) {
      const data = await post("/api/auth/login", { username, password });
      token = data.access_token;
      localStorage.setItem(TOKEN_KEY, token);
    },
    health: () => request("/api/health"),
    predict: (payload) => post("/api/predict", payload),
    assets: () => request("/api/assets"),
    summary: () => request("/api/assets/summary/health"),
    connect: (id, body) => post(`/api/assets/${id}/connect`, body),
    history: (limit = 50, assetId = "") =>
      request(`/api/telemetry/history?limit=${limit}${assetId ? `&asset_id=${assetId}` : ""}`),
    roi: () => request("/api/metrics/roi"),
    modelMetrics: () => request("/api/model/metrics"),
  };
})();
