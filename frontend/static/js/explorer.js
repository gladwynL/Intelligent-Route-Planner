// Database Explorer: lists the ten SQL views and renders the selected one as an HTML table.
import { exportUrl, get } from "./api.js";
import { $, debounce, emptyHTML, esc, initChrome, isNumCol, label, loadingHTML, renderTable, user } from "./ui.js";

initChrome();

const ALL_KEYS = ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10"];
const state = { views: [], current: null, sort: null };

function paramsFromForm() {
  const p = Object.fromEntries([...new FormData($("#view-filters")).entries()].filter(([, v]) => String(v).trim() !== ""));
  if (state.sort) { p.sort = state.sort.key; p.dir = state.sort.dir; }
  return p;
}

function buildFilters(view) {
  const form = $("#view-filters");
  const parts = [`<div class="field wide"><label for="vf-q">Keyword</label><input id="vf-q" name="q" type="search" maxlength="100" placeholder="Search every column…"></div>`];
  for (const [col, kind] of Object.entries(view.filters)) {
    const id = `vf-${col}`;
    if (Array.isArray(kind)) {
      parts.push(`<div class="field"><label for="${id}">${esc(label(col))}</label><select id="${id}" name="${col}"><option value="">Any</option>${kind.map((k) => `<option>${esc(k)}</option>`).join("")}</select></div>`);
    } else if (kind === "bool") {
      parts.push(`<div class="field"><label for="${id}">${esc(label(col))}</label><select id="${id}" name="${col}"><option value="">Any</option><option value="true">Yes</option><option value="false">No</option></select></div>`);
    } else if (kind === "int") {
      parts.push(`<div class="field"><label for="${id}">${esc(label(col))}</label><input id="${id}" name="${col}" type="number" min="0" step="1"></div>`);
    } else {
      parts.push(`<div class="field"><label for="${id}">${esc(label(col))}</label><input id="${id}" name="${col}" type="text" maxlength="80"></div>`);
    }
  }
  parts.push(`<div class="field" style="flex:0 0 auto"><label>&nbsp;</label><button class="btn btn-secondary" type="reset">Reset</button></div>`);
  form.innerHTML = parts.join("");
}

function renderList() {
  const allowed = new Set(state.views.map((v) => v.key));
  const byKey = Object.fromEntries(state.views.map((v) => [v.key, v]));
  $("#view-access").textContent = `${allowed.size} of ${ALL_KEYS.length} views available to your role (${user.user_role})`;
  $("#view-list").innerHTML = ALL_KEYS.map((k) => {
    const v = byKey[k];
    const n = k.slice(1);
    if (!v) {
      return `<button class="view-item locked" type="button" disabled title="Sign in as a user or administrator to open this view">
        <span class="num">${n}</span><span><span class="t">View ${n} 🔒</span><span class="f">Contains personal data</span></span></button>`;
    }
    return `<button class="view-item ${state.current?.key === k ? "active" : ""}" type="button" data-key="${k}" aria-current="${state.current?.key === k}">
      <span class="num">${n}</span><span><span class="t">${esc(v.title)}</span><span class="f">${esc(v.feature)}</span></span></button>`;
  }).join("");
}

async function selectView(key) {
  const view = state.views.find((v) => v.key === key);
  if (!view) return;
  state.current = view;
  state.sort = null;
  history.replaceState(null, "", `#${key}`);
  renderList();
  $("#view-title").innerHTML = `View ${key.slice(1)}: ${esc(view.title)} <span class="badge badge-primary">${esc(view.feature)}</span>`;
  $("#view-desc").innerHTML = `<code>${esc(view.name)}</code> — ${esc(view.description)}`;
  $("#scope-note").innerHTML = view.scoped_to_current_user
    ? `<div class="notice info mt-2"><span aria-hidden="true">🔒</span><div>This view contains personal data, so only rows belonging to your account are shown. Administrators see every row.</div></div>` : "";
  buildFilters(view);
  await runView();
}

async function runView() {
  const view = state.current;
  if (!view) return;
  const params = paramsFromForm();
  $("#export-csv").href = exportUrl(`/api/views/${view.key}/export`, "csv", params);
  $("#export-pdf").href = exportUrl(`/api/views/${view.key}/export`, "pdf", params);
  const box = $("#view-table");
  box.innerHTML = loadingHTML(`Running ${view.name}…`);
  try {
    const data = await get(`/api/views/${view.key}`, params);
    $("#sql-text").textContent = data.sql;
    const cols = view.columns.map((c) => ({ key: c, label: label(c), num: isNumCol(data.rows, c) }));
    renderTable(box, {
      columns: cols, rows: data.rows,
      emptyTitle: "No rows match", emptyText: "Clear the keyword or filters to see all rows.",
      sort: state.sort,
      onSort: (key) => {
        state.sort = state.sort?.key === key ? { key, dir: state.sort.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" };
        runView();
      },
    });
    const meta = box.querySelector(".table-meta span:last-child");
    if (meta) meta.textContent = `${view.name} · executed in PostgreSQL`;
  } catch (e) {
    box.innerHTML = emptyHTML("Query failed", e.message, "!");
  }
}

async function init() {
  get("/api/health").then((h) => {
    $("#db-status").innerHTML = `<span class="status-dot"></span> PostgreSQL ${esc(h.server_version)} · ${h.table_count} tables · ${h.view_count} views`;
  }).catch(() => { $("#db-status").innerHTML = `<span class="status-dot down"></span> Database unavailable`; });
  try {
    state.views = (await get("/api/views")).views;
  } catch (e) {
    $("#view-table").innerHTML = emptyHTML("Could not load views", e.message, "!");
    return;
  }
  renderList();
  $("#view-list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-key]");
    if (b) selectView(b.dataset.key);
  });
  const rerun = debounce(runView, 300);
  $("#view-filters").addEventListener("input", rerun);
  $("#view-filters").addEventListener("change", rerun);
  $("#view-filters").addEventListener("submit", (e) => { e.preventDefault(); runView(); });
  $("#view-filters").addEventListener("reset", () => setTimeout(runView, 0));
  window.addEventListener("hashchange", () => {
    const k = location.hash.replace("#", "");
    if (k && k !== state.current?.key) selectView(k);
  });
  const fromHash = location.hash.replace("#", "");
  const first = state.views.find((v) => v.key === fromHash) || state.views[0];
  if (first) selectView(first.key);
}
init();
