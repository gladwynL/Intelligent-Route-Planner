// Shared UI helpers: escaping, formatting, toasts, dialogs, dynamic forms, tables.
import { ApiError } from "./api.js";

export const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export const user = window.APP_USER || null;
export const isAdmin = user?.user_role === "admin";
export const canEdit = user && user.user_role !== "guest";

// ---------------------------------------------------------------- formatting
const DATE_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

export function fmtDate(v, withTime = true) {
  if (!v) return "";
  const d = new Date(v);
  if (isNaN(d)) return esc(v);
  const opts = withTime
    ? { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }
    : { year: "numeric", month: "short", day: "numeric" };
  return d.toLocaleString("en-CA", opts);
}

export function fmtNum(v, digits = 2) {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  if (!isFinite(n)) return esc(v);
  return Number.isInteger(n) ? String(n) : n.toFixed(digits);
}

export const money = (v) => (v === null || v === undefined ? "" : `$${Number(v).toFixed(2)}`);
export const modeBadge = (m) => (m ? `<span class="mode mode-${esc(m)}">${esc(m)}</span>` : `<span class="null">—</span>`);
export const sevBadge = (n) => (n === null || n === undefined ? `<span class="null">—</span>` : `<span class="sev sev-${Math.round(n)}" title="Severity ${esc(n)} of 5">${esc(fmtNum(n))}</span>`);
export const roleBadge = (r) => `<span class="badge role-${esc(r)}">${esc(r)}</span>`;
export function statusBadge(s) {
  const cls = { planned: "badge-primary", completed: "badge-success", cancelled: "badge-neutral" }[s] || "badge-neutral";
  return `<span class="badge ${cls}">${esc(s)}</span>`;
}
export const stars = (n) =>
  `<span class="stars" aria-label="${n} of 5 stars">${[1, 2, 3, 4, 5].map((i) => `<span class="${i <= n ? "" : "off"}">★</span>`).join("")}</span>`;
export const yesNo = (b) => (b ? `<span class="badge badge-success">Yes</span>` : `<span class="badge badge-neutral">No</span>`);

export const SOURCE_LABELS = {
  stored: ["Stored data", "badge-neutral", "Seeded demonstration data or a record stored in the database"],
  manual: ["Manual entry", "badge-outline", "Entered by a user"],
  heuristic: ["Heuristic estimate", "badge-warning", "Straight-line distance × detour factor ÷ typical speed — not live navigation"],
  osrm: ["OSRM estimate", "badge-accent", "Driving distance/time from the public OSRM routing engine"],
};
export function sourceBadge(src) {
  const [label, cls, title] = SOURCE_LABELS[src] || SOURCE_LABELS.stored;
  return `<span class="badge ${cls}" title="${esc(title)}">${label}</span>`;
}

/** Generic cell formatter used by database tables. */
export function cell(col, v) {
  if (v === null || v === undefined || v === "") return `<span class="null">NULL</span>`;
  if (typeof v === "boolean") return yesNo(v);
  if (col === "travel_mode" || col === "preferred_mode") return modeBadge(v);
  if (/severity$/.test(col) && col !== "average_severity") return sevBadge(v);
  if (col === "user_role") return roleBadge(v);
  if (col === "trip_status") return statusBadge(v);
  if (col === "rating") return stars(Number(v));
  if (col === "toll_cost") return money(v);
  if (typeof v === "string" && DATE_RE.test(v)) return fmtDate(v);
  if (typeof v === "number") return fmtNum(v);
  return esc(v);
}
export const isNumCol = (rows, col) => rows.some((r) => typeof r[col] === "number");
export const label = (col) => col.replace(/_/g, " ");

// ---------------------------------------------------------------- feedback
export function toast(message, type = "info", ms = 4200) {
  let box = $(".toasts");
  if (!box) {
    box = document.createElement("div");
    box.className = "toasts";
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");
    document.body.appendChild(box);
  }
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.textContent = message;
  box.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

export function showError(err, fallback = "Something went wrong.") {
  toast(err?.message || fallback, "error", 6000);
}

export function setBusy(btn, busy, text) {
  if (!btn) return;
  if (busy) {
    btn.dataset.label = btn.innerHTML;
    btn.classList.add("loading");
    btn.disabled = true;
    if (text) btn.textContent = text;
  } else {
    btn.classList.remove("loading");
    btn.disabled = false;
    if (btn.dataset.label) btn.innerHTML = btn.dataset.label;
  }
}

export const loadingHTML = (msg = "Loading…") => `<div class="loading"><span class="spinner"></span>${esc(msg)}</div>`;
export const emptyHTML = (title, text = "", icon = "○") =>
  `<div class="empty"><div class="icon">${icon}</div><h3>${esc(title)}</h3><p>${esc(text)}</p></div>`;

// ---------------------------------------------------------------- dialogs
function makeDialog(inner) {
  const d = document.createElement("dialog");
  d.className = "modal";
  d.innerHTML = inner;
  document.body.appendChild(d);
  d.addEventListener("close", () => setTimeout(() => d.remove(), 50));
  return d;
}

export function confirmDialog({ title = "Are you sure?", message = "", confirmText = "Delete", danger = true } = {}) {
  return new Promise((resolve) => {
    const d = makeDialog(`
      <div class="modal-head"><h2>${esc(title)}</h2><button class="icon-btn" data-x aria-label="Close">×</button></div>
      <div class="modal-body"><p>${esc(message)}</p></div>
      <div class="modal-foot">
        <button class="btn btn-secondary" data-cancel>Cancel</button>
        <button class="btn ${danger ? "btn-danger solid" : "btn-primary"}" data-ok>${esc(confirmText)}</button>
      </div>`);
    let result = false;
    d.querySelector("[data-ok]").onclick = () => { result = true; d.close(); };
    d.querySelector("[data-cancel]").onclick = () => d.close();
    d.querySelector("[data-x]").onclick = () => d.close();
    d.addEventListener("close", () => resolve(result));
    d.showModal();
    d.querySelector("[data-cancel]").focus();
  });
}

// ---------------------------------------------------------------- dynamic forms
const EMAIL_RE = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/;

function toLocalInput(v) {
  if (!v) return "";
  return String(v).slice(0, 16);
}

export function fieldHTML(f, value) {
  const id = `f-${f.name}-${Math.random().toString(36).slice(2, 7)}`;
  const req = f.required ? ` <span class="req" aria-hidden="true">*</span>` : "";
  const attrs = [
    `id="${id}"`, `name="${f.name}"`,
    f.required ? "required" : "",
    f.min !== undefined ? `min="${f.min}"` : "",
    f.max !== undefined ? `max="${f.max}"` : "",
    f.step !== undefined ? `step="${f.step}"` : "",
    f.maxlength ? `maxlength="${f.maxlength}"` : "",
    f.minlength ? `minlength="${f.minlength}"` : "",
    f.placeholder ? `placeholder="${esc(f.placeholder)}"` : "",
    f.autocomplete ? `autocomplete="${f.autocomplete}"` : "",
    f.list ? `list="${f.list}"` : "",
  ].filter(Boolean).join(" ");
  let input;
  if (f.type === "select") {
    const opts = (f.options || []).map((o) => {
      const val = typeof o === "object" ? o.value : o;
      const lab = typeof o === "object" ? o.label : o;
      return `<option value="${esc(val)}" ${String(val) === String(value ?? "") ? "selected" : ""}>${esc(lab)}</option>`;
    }).join("");
    input = `<select ${attrs}><option value="">${esc(f.placeholder || "Select…")}</option>${opts}</select>`;
  } else if (f.type === "checkbox") {
    return `<div class="field ${f.full ? "full" : ""}"><label class="check"><input type="checkbox" ${attrs} ${value ? "checked" : ""}> ${esc(f.label)}</label>${f.hint ? `<span class="hint">${esc(f.hint)}</span>` : ""}</div>`;
  } else if (f.type === "textarea") {
    input = `<textarea ${attrs}>${esc(value ?? "")}</textarea>`;
  } else {
    const type = f.type === "datetime" ? "datetime-local" : f.type || "text";
    const val = f.type === "datetime" ? toLocalInput(value) : value ?? "";
    input = `<input type="${type}" ${attrs} value="${esc(val)}">`;
  }
  return `<div class="field ${f.full ? "full" : ""}" data-field="${f.name}">
    <label for="${id}">${esc(f.label)}${req}</label>${input}
    ${f.hint ? `<span class="hint">${esc(f.hint)}</span>` : ""}<span class="error" aria-live="polite"></span></div>`;
}

export function readForm(form, fields) {
  const out = {};
  for (const f of fields) {
    const el = form.elements[f.name];
    if (!el) continue;
    if (f.type === "checkbox") out[f.name] = el.checked;
    else if (f.type === "number") out[f.name] = el.value === "" ? null : Number(el.value);
    else out[f.name] = el.value.trim() === "" ? null : el.value.trim();
  }
  return out;
}

/** Client-side validation mirroring the server rules. Returns {field: message}. */
export function validateValues(values, fields, extra) {
  const errs = {};
  for (const f of fields) {
    const v = values[f.name];
    if (f.type === "checkbox") continue;
    if (v === null || v === undefined || v === "") {
      if (f.required) errs[f.name] = `${f.label} is required.`;
      continue;
    }
    if (f.type === "email" && !EMAIL_RE.test(v)) errs[f.name] = "Enter a valid email address (e.g. name@example.com).";
    if (f.type === "number") {
      if (!isFinite(v)) errs[f.name] = `${f.label} must be a number.`;
      else if (f.min !== undefined && v < f.min) errs[f.name] = `${f.label} must be at least ${f.min}.`;
      else if (f.max !== undefined && v > f.max) errs[f.name] = `${f.label} must be at most ${f.max}.`;
      else if (f.step === 1 && !Number.isInteger(v)) errs[f.name] = `${f.label} must be a whole number.`;
    }
    if (typeof v === "string") {
      if (f.maxlength && v.length > f.maxlength) errs[f.name] = `${f.label} must be at most ${f.maxlength} characters.`;
      if (f.minlength && v.length < f.minlength) errs[f.name] = `${f.label} must be at least ${f.minlength} characters.`;
    }
  }
  if (extra) Object.assign(errs, extra(values) || {});
  return errs;
}

export function showFieldErrors(form, errs, alertBox) {
  $$(".field", form).forEach((el) => {
    el.classList.remove("invalid");
    const e = $(".error", el);
    if (e) e.textContent = "";
  });
  Object.entries(errs || {}).forEach(([name, msg]) => {
    const el = form.querySelector(`[data-field="${name}"]`);
    if (el) {
      el.classList.add("invalid");
      $(".error", el).textContent = msg;
    } else if (alertBox) {
      alertBox.innerHTML += `<div>${esc(msg)}</div>`;
    }
  });
  const first = form.querySelector(".field.invalid input, .field.invalid select, .field.invalid textarea");
  if (first) first.focus();
}

/**
 * Bind client validation + AJAX submit to an existing <form>.
 * onSubmit(values) must return a promise; server validation details are mapped back to fields.
 */
export function bindForm(form, fields, onSubmit, { extra, submitBtn, alertBox } = {}) {
  const btn = submitBtn || form.querySelector('[type="submit"]');
  // Live re-validation of a field after the user edits it.
  form.addEventListener("input", (e) => {
    const fieldEl = e.target.closest(".field");
    if (fieldEl?.classList.contains("invalid")) {
      fieldEl.classList.remove("invalid");
      const er = $(".error", fieldEl);
      if (er) er.textContent = "";
    }
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (alertBox) alertBox.innerHTML = "";
    const values = readForm(form, fields);
    const errs = validateValues(values, fields, extra);
    showFieldErrors(form, errs);
    if (Object.keys(errs).length) return;
    setBusy(btn, true);
    try {
      await onSubmit(values);
    } catch (err) {
      if (err instanceof ApiError && err.details && Object.keys(err.details).length && !err.details.constraint) {
        showFieldErrors(form, err.details, alertBox);
      }
      if (alertBox) alertBox.innerHTML = `<div class="form-alert error">${esc(err.message)}</div>` + alertBox.innerHTML;
      else showError(err);
    } finally {
      setBusy(btn, false);
    }
  });
}

/** Modal form used for create/edit dialogs. Resolves true when saved. */
export function formModal({ title, fields, values = {}, submitText = "Save", onSubmit, extra, intro }) {
  return new Promise((resolve) => {
    const d = makeDialog(`
      <form novalidate>
        <div class="modal-head"><h2>${esc(title)}</h2><button type="button" class="icon-btn" data-x aria-label="Close">×</button></div>
        <div class="modal-body">
          ${intro ? `<div class="form-alert info">${esc(intro)}</div>` : ""}
          <div data-alert></div>
          <div class="form-grid">${fields.map((f) => fieldHTML(f, values[f.name])).join("")}</div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn-secondary" data-cancel>Cancel</button>
          <button type="submit" class="btn btn-primary">${esc(submitText)}</button>
        </div>
      </form>`);
    const form = d.querySelector("form");
    let saved = false;
    d.querySelector("[data-cancel]").onclick = () => d.close();
    d.querySelector("[data-x]").onclick = () => d.close();
    bindForm(form, fields, async (vals) => {
      await onSubmit(vals);
      saved = true;
      d.close();
    }, { extra, alertBox: d.querySelector("[data-alert]") });
    d.addEventListener("close", () => resolve(saved));
    d.showModal();
    form.querySelector("input:not([type=hidden]), select, textarea")?.focus();
  });
}

// ---------------------------------------------------------------- tables
/**
 * Render a data table.
 * columns: [{key, label, render(row), num, sortable}] ; actions(row) -> HTML string
 */
export function renderTable(container, { columns, rows, actions, onRowClick, activeId, idKey, emptyTitle = "No records found", emptyText = "Try adjusting the search or filters.", sort, onSort, meta = true }) {
  if (!rows.length) {
    container.innerHTML = emptyHTML(emptyTitle, emptyText);
    return;
  }
  const head = columns.map((c) => {
    const s = sort && sort.key === c.key ? `<span class="sort-ind">${sort.dir === "desc" ? "▼" : "▲"}</span>` : "";
    return `<th class="${c.num ? "num" : ""} ${onSort && c.sortable !== false ? "sortable" : ""}" data-key="${c.key}" scope="col">${esc(c.label ?? label(c.key))}${s}</th>`;
  }).join("") + (actions ? `<th class="num" scope="col">Actions</th>` : "");
  const body = rows.map((r, i) => {
    const id = idKey ? r[idKey] : i;
    const tds = columns.map((c) => `<td class="${c.num ? "num" : ""}">${c.render ? c.render(r) : cell(c.key, r[c.key])}</td>`).join("");
    return `<tr data-i="${i}" class="${onRowClick ? "clickable" : ""} ${activeId !== undefined && id === activeId ? "active" : ""}">${tds}${actions ? `<td class="actions">${actions(r)}</td>` : ""}</tr>`;
  }).join("");
  container.innerHTML = `<div class="table-wrap"><table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>
    ${meta ? `<div class="table-meta"><span>${rows.length} row${rows.length === 1 ? "" : "s"}</span><span></span></div>` : ""}`;
  if (onSort) {
    $$("th.sortable", container).forEach((th) => th.addEventListener("click", () => onSort(th.dataset.key)));
  }
  if (onRowClick) {
    $$("tbody tr", container).forEach((tr) => tr.addEventListener("click", (e) => {
      if (e.target.closest("button, a, input")) return;
      onRowClick(rows[Number(tr.dataset.i)]);
    }));
  }
  return (fn) => $$("tbody tr", container).forEach((tr) => fn(tr, rows[Number(tr.dataset.i)]));
}

/** Wire up [data-act] buttons inside a container to handlers keyed by action name. */
export function onActions(container, rows, handlers, idKey) {
  container.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn || !container.contains(btn)) return;
    const row = rows().find((r) => String(r[idKey]) === btn.dataset.id);
    const fn = handlers[btn.dataset.act];
    if (fn && row) {
      e.stopPropagation();
      await fn(row, btn);
    }
  });
}

export function debounce(fn, ms = 300) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

export function options(items, valueKey, labelFn) {
  return items.map((i) => ({ value: i[valueKey], label: labelFn(i) }));
}

// ---------------------------------------------------------------- page chrome
export function initChrome() {
  const toggle = $(".nav-toggle");
  if (toggle) toggle.addEventListener("click", () => {
    const nav = $(".nav");
    nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", nav.classList.contains("open"));
  });
  const logout = $("#logout-btn");
  if (logout) logout.addEventListener("click", async () => {
    const { post } = await import("./api.js");
    try {
      const r = await post("/api/auth/logout");
      window.location.href = r.redirect || "/login";
    } catch (e) {
      showError(e);
    }
  });
}
