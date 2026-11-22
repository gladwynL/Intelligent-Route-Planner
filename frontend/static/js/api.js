// Thin Fetch API wrapper: JSON in/out, CSRF header, uniform error objects.

const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";

export class ApiError extends Error {
  constructor(status, message, details) {
    super(message);
    this.status = status;
    this.details = details || {};
  }
}

export async function api(path, { method = "GET", body, params } = {}) {
  let url = path;
  if (params) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v).trim() !== "") qs.append(k, v);
    });
    const s = qs.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }
  const opts = { method, headers: { Accept: "application/json" }, credentials: "same-origin" };
  if (method !== "GET") opts.headers["X-CSRFToken"] = csrfToken();
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let resp;
  try {
    resp = await fetch(url, opts);
  } catch (e) {
    throw new ApiError(0, "Cannot reach the server. Check that the application is running.");
  }
  let data = null;
  const type = resp.headers.get("content-type") || "";
  if (type.includes("application/json")) data = await resp.json().catch(() => null);
  if (!resp.ok) {
    if (resp.status === 401 && !path.startsWith("/api/auth/")) {
      window.location.href = "/login?next=" + encodeURIComponent(location.pathname);
    }
    const err = data?.error || {};
    throw new ApiError(resp.status, err.message || `Request failed (HTTP ${resp.status}).`, err.details);
  }
  return data;
}

export const get = (path, params) => api(path, { params });
export const post = (path, body) => api(path, { method: "POST", body: body ?? {} });
export const put = (path, body) => api(path, { method: "PUT", body });
export const del = (path) => api(path, { method: "DELETE" });

/** Build a download URL for a CSV/PDF export, carrying the current filters. */
export function exportUrl(path, format, params = {}) {
  const qs = new URLSearchParams({ format });
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && String(v).trim() !== "") qs.append(k, v);
  });
  return `${path}?${qs}`;
}
