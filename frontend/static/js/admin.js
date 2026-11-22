// Admin page: one configurable CRUD manager covering all nine relations.
import { del, get, post, put } from "./api.js";
import {
  $, $$, confirmDialog, debounce, emptyHTML, esc, formModal, initChrome, loadingHTML, renderTable, showError,
  toast, user,
} from "./ui.js";

initChrome();

const MODES = ["driving", "transit", "cycling", "walking"];
const lookups = {};
async function lookup(name) {
  const loaders = {
    users: async () => (await get("/api/users")).users.map((u) => ({ value: u.user_id, label: `#${u.user_id} ${u.full_name} (${u.user_role})` })),
    locations: async () => (await get("/api/locations")).locations.map((l) => ({ value: l.location_id, label: `${l.location_name} (${l.city})` })),
    trips: async () => (await get("/api/trips")).trips.map((t) => ({ value: t.trip_id, label: `#${t.trip_id} ${t.origin} → ${t.destination} · ${t.full_name}` })),
    routes: async () => (await get("/api/routes")).routes.map((r) => ({ value: r.route_id, label: `Route #${r.route_id} · trip ${r.trip_id} · ${r.travel_mode}` })),
    segments: async () => (await get("/api/segments")).segments.map((s) => ({ value: s.segment_id, label: `Segment #${s.segment_id} · route ${s.route_id} · ${s.road_name}` })),
  };
  if (!lookups[name]) lookups[name] = await loaders[name]();
  return lookups[name];
}
const invalidate = (...names) => names.forEach((n) => delete lookups[n]);
const num = (v) => (v === null || v === undefined || v === "" ? v : Number(v));

const locationFields = [
  { name: "location_name", label: "Location name", type: "text", required: true, maxlength: 120, full: true },
  { name: "street_address", label: "Street address", type: "text", required: true, maxlength: 180, full: true },
  { name: "city", label: "City", type: "text", required: true, maxlength: 80 },
  { name: "location_type", label: "Type", type: "select", required: true, options: ["home", "work", "school", "public", "other"] },
  { name: "latitude", label: "Latitude", type: "number", required: true, min: -90, max: 90, step: 0.000001 },
  { name: "longitude", label: "Longitude", type: "number", required: true, min: -180, max: 180, step: 0.000001 },
];
const prefFields = [
  { name: "preferred_mode", label: "Preferred mode", type: "select", required: true, options: MODES },
  { name: "max_walking_km", label: "Max walking (km)", type: "number", min: 0, max: 999.9, step: 0.1 },
  { name: "avoid_tolls", label: "Avoid tolls", type: "checkbox" },
  { name: "avoid_highways", label: "Avoid highways", type: "checkbox" },
  { name: "prioritize_safety", label: "Prioritise safety", type: "checkbox" },
];
const routeFields = [
  { name: "travel_mode", label: "Travel mode", type: "select", required: true, options: MODES },
  { name: "distance_km", label: "Distance (km)", type: "number", required: true, min: 0.01, step: 0.01 },
  { name: "estimated_duration_min", label: "Est. duration (min)", type: "number", required: true, min: 1, step: 1 },
  { name: "toll_cost", label: "Toll cost ($)", type: "number", min: 0, step: 0.01 },
];
const segmentFields = async () => [
  { name: "sequence_no", label: "Sequence no.", type: "number", required: true, min: 1, step: 1 },
  { name: "road_name", label: "Road / service", type: "text", required: true, maxlength: 120 },
  { name: "start_location_id", label: "Start location", type: "select", required: true, options: await lookup("locations") },
  { name: "end_location_id", label: "End location", type: "select", required: true, options: await lookup("locations") },
  { name: "distance_km", label: "Distance (km)", type: "number", required: true, min: 0.01, step: 0.01 },
  { name: "estimated_duration_min", label: "Est. duration (min)", type: "number", required: true, min: 1, step: 1 },
];
const obsFields = [
  { name: "observed_at", label: "Observed at", type: "datetime", required: true },
  { name: "condition_type", label: "Condition type", type: "select", required: true, options: ["traffic", "weather", "closure", "construction"] },
  { name: "severity", label: "Severity (0–5)", type: "number", required: true, min: 0, max: 5, step: 1 },
  { name: "source_name", label: "Source", type: "text", required: true, maxlength: 80 },
  { name: "description", label: "Description", type: "text", required: true, maxlength: 200, full: true },
];
const differ = (a, b, msg) => (v) => (v[a] && v[a] === v[b] ? { [b]: msg } : null);

const MANAGERS = {
  users: {
    title: "Users", table: "app_user", desc: "Accounts and roles. Passwords are hashed with scrypt; hashes are never returned by the API.",
    list: "/api/users", key: "users", id: "user_id",
    columns: ["user_id", "full_name", "email", "user_role", "preferred_mode", "trip_count", "created_at"],
    filters: [{ name: "q", label: "Search name/email", type: "search" }, { name: "role", label: "Role", type: "select", options: ["admin", "user", "guest"] }],
    createFields: async () => [
      { name: "full_name", label: "Full name", type: "text", required: true, maxlength: 100, full: true },
      { name: "email", label: "Email", type: "email", required: true, maxlength: 150 },
      { name: "user_role", label: "Role", type: "select", required: true, options: ["admin", "user", "guest"] },
      { name: "password", label: "Password", type: "password", required: true, minlength: 8, maxlength: 128, hint: "At least 8 characters", full: true },
    ],
    editFields: async () => [
      { name: "full_name", label: "Full name", type: "text", required: true, maxlength: 100, full: true },
      { name: "email", label: "Email", type: "email", required: true, maxlength: 150 },
      { name: "user_role", label: "Role", type: "select", required: true, options: ["admin", "user", "guest"] },
      { name: "password", label: "New password", type: "password", minlength: 8, maxlength: 128, hint: "Leave blank to keep the current password", full: true },
    ],
    create: (v) => post("/api/users", v),
    update: (r, v) => { if (!v.password) delete v.password; return put(`/api/users/${r.user_id}`, v); },
    remove: (r) => del(`/api/users/${r.user_id}`),
    deleteMsg: (r) => `${r.full_name}'s account and all of their trips, routes, saved places and feedback will be permanently deleted (ON DELETE CASCADE).`,
    canDelete: (r) => r.user_id !== user.user_id,
    after: () => invalidate("users"),
  },
  locations: {
    title: "Locations", table: "location", desc: "Reusable origins, destinations and segment endpoints.",
    list: "/api/locations", key: "locations", id: "location_id",
    columns: ["location_id", "location_name", "street_address", "city", "latitude", "longitude", "location_type", "trip_count"],
    filters: [{ name: "q", label: "Search", type: "search" }, { name: "type", label: "Type", type: "select", options: ["home", "work", "school", "public", "other"] }],
    createFields: async () => locationFields, editFields: async () => locationFields,
    create: (v) => post("/api/locations", v), update: (r, v) => put(`/api/locations/${r.location_id}`, v),
    remove: (r) => del(`/api/locations/${r.location_id}`),
    deleteMsg: (r) => `${r.location_name} will be deleted. This fails if trips or route segments still reference it.`,
    after: () => invalidate("locations"),
  },
  preferences: {
    title: "User preferences", table: "user_preference", desc: "One routing profile per user (UNIQUE user_id). Used by View 6's preference score.",
    list: "/api/preferences", key: "preferences", id: "preference_id",
    columns: ["preference_id", "user_id", "full_name", "preferred_mode", "max_walking_km", "avoid_tolls", "avoid_highways", "prioritize_safety"],
    filters: [],
    createFields: async () => [{ name: "user_id", label: "User", type: "select", required: true, options: await lookup("users"), full: true }, ...prefFields],
    editFields: async () => prefFields,
    create: (v) => post("/api/preferences", { ...v, user_id: num(v.user_id) }),
    update: (r, v) => put(`/api/preferences/${r.preference_id}`, v),
    remove: (r) => del(`/api/preferences/${r.preference_id}`),
    deleteMsg: (r) => `${r.full_name}'s preference profile will be deleted. Their trips will not be scored by View 6 until a new profile exists.`,
  },
  trips: {
    title: "Trips", table: "trip", desc: "Route-planning requests. Deleting a trip cascades to its routes, segments, observations and feedback.",
    list: "/api/trips", key: "trips", id: "trip_id",
    columns: ["trip_id", "full_name", "origin", "destination", "departure_time", "trip_status", "actual_duration_min", "route_count"],
    filters: [{ name: "q", label: "Search", type: "search" }, { name: "status", label: "Status", type: "select", options: ["planned", "completed", "cancelled"] }],
    createFields: async () => [
      { name: "user_id", label: "Traveller", type: "select", required: true, options: await lookup("users"), full: true },
      { name: "origin_location_id", label: "Origin", type: "select", required: true, options: await lookup("locations") },
      { name: "destination_location_id", label: "Destination", type: "select", required: true, options: await lookup("locations") },
      { name: "departure_time", label: "Departure", type: "datetime", required: true },
      { name: "trip_status", label: "Status", type: "select", required: true, options: ["planned", "completed", "cancelled"] },
    ],
    editFields: async () => [
      { name: "origin_location_id", label: "Origin", type: "select", required: true, options: await lookup("locations") },
      { name: "destination_location_id", label: "Destination", type: "select", required: true, options: await lookup("locations") },
      { name: "departure_time", label: "Departure", type: "datetime", required: true },
      { name: "trip_status", label: "Status", type: "select", required: true, options: ["planned", "completed", "cancelled"] },
      { name: "actual_duration_min", label: "Actual duration (min)", type: "number", min: 1, step: 1 },
    ],
    extra: differ("origin_location_id", "destination_location_id", "Destination must differ from the origin."),
    create: (v) => post("/api/trips", { ...v, user_id: num(v.user_id), origin_location_id: num(v.origin_location_id), destination_location_id: num(v.destination_location_id) }),
    update: (r, v) => put(`/api/trips/${r.trip_id}`, { ...v, origin_location_id: num(v.origin_location_id), destination_location_id: num(v.destination_location_id) }),
    remove: (r) => del(`/api/trips/${r.trip_id}`),
    deleteMsg: (r) => `Trip #${r.trip_id} and all dependent routes, segments, observations and feedback will be permanently deleted.`,
    after: () => invalidate("trips", "routes", "segments"),
  },
  routes: {
    title: "Route options", table: "route_option", desc: "Alternatives per trip. At most one may be selected per trip (partial unique index).",
    list: "/api/routes", key: "routes", id: "route_id",
    columns: ["route_id", "trip_id", "option_number", "travel_mode", "distance_km", "estimated_duration_min", "toll_cost", "is_selected", "total_route_score", "recommendation_rank"],
    filters: [{ name: "trip_id", label: "Trip ID", type: "number" }, { name: "mode", label: "Mode", type: "select", options: MODES }],
    createFields: async () => [{ name: "trip_id", label: "Trip", type: "select", required: true, options: await lookup("trips"), full: true }, ...routeFields],
    editFields: async () => routeFields,
    create: (v) => { const t = v.trip_id; delete v.trip_id; return post(`/api/trips/${t}/routes`, v); },
    update: (r, v) => put(`/api/routes/${r.route_id}`, v),
    remove: (r) => del(`/api/routes/${r.route_id}`),
    rowActions: (r) => (r.is_selected ? "" : `<button class="btn btn-sm btn-primary" data-act="select" data-id="${r.route_id}">Select</button>`),
    custom: { select: async (r) => { await post(`/api/routes/${r.route_id}/select`); toast(`Route #${r.route_id} selected for trip ${r.trip_id}.`, "success"); } },
    deleteMsg: (r) => `Route #${r.route_id} and its segments and observations will be permanently deleted.`,
    after: () => invalidate("routes", "segments"),
  },
  segments: {
    title: "Route segments", table: "route_segment", desc: "Ordered road or transit sections of each route.",
    list: "/api/segments", key: "segments", id: "segment_id",
    columns: ["segment_id", "route_id", "trip_id", "sequence_no", "start_location", "end_location", "road_name", "distance_km", "estimated_duration_min"],
    filters: [{ name: "q", label: "Road name", type: "search" }, { name: "route_id", label: "Route ID", type: "number" }, { name: "trip_id", label: "Trip ID", type: "number" }],
    createFields: async () => [{ name: "route_id", label: "Route", type: "select", required: true, options: await lookup("routes"), full: true }, ...(await segmentFields())],
    editFields: segmentFields,
    extra: differ("start_location_id", "end_location_id", "End location must differ from the start."),
    create: (v) => { const r = v.route_id; delete v.route_id; return post(`/api/routes/${r}/segments`, { ...v, start_location_id: num(v.start_location_id), end_location_id: num(v.end_location_id) }); },
    update: (r, v) => put(`/api/segments/${r.segment_id}`, { ...v, start_location_id: num(v.start_location_id), end_location_id: num(v.end_location_id) }),
    remove: (r) => del(`/api/segments/${r.segment_id}`),
    deleteMsg: (r) => `Segment #${r.segment_id} and its condition observations will be permanently deleted.`,
    after: () => invalidate("segments"),
  },
  observations: {
    title: "Condition observations", table: "condition_observation", desc: "Traffic, weather, closure and construction reports per segment (severity 0–5).",
    list: "/api/observations", key: "observations", id: "observation_id",
    columns: ["observation_id", "segment_id", "road_name", "observed_at", "condition_type", "severity", "description", "source_name"],
    filters: [{ name: "q", label: "Search", type: "search" }, { name: "type", label: "Type", type: "select", options: ["traffic", "weather", "closure", "construction"] }, { name: "min_severity", label: "Min. severity", type: "number" }],
    createFields: async () => [{ name: "segment_id", label: "Segment", type: "select", required: true, options: await lookup("segments"), full: true }, ...obsFields],
    editFields: async () => obsFields,
    create: (v) => post("/api/observations", { ...v, segment_id: num(v.segment_id) }),
    update: (r, v) => put(`/api/observations/${r.observation_id}`, v),
    remove: (r) => del(`/api/observations/${r.observation_id}`),
    deleteMsg: (r) => `Observation #${r.observation_id} will be permanently deleted.`,
  },
  saved: {
    title: "Saved locations", table: "saved_location", desc: "User labels and favourites (UNIQUE user_id + location_id).",
    list: "/api/saved-locations", key: "saved_locations", id: "saved_location_id",
    columns: ["saved_location_id", "full_name", "label", "location_name", "city", "is_favourite", "saved_at"],
    filters: [{ name: "q", label: "Search", type: "search" }],
    createFields: async () => [
      { name: "user_id", label: "User", type: "select", required: true, options: await lookup("users"), full: true },
      { name: "location_id", label: "Location", type: "select", required: true, options: await lookup("locations"), full: true },
      { name: "label", label: "Label", type: "text", required: true, maxlength: 50 },
      { name: "is_favourite", label: "Favourite", type: "checkbox" },
    ],
    editFields: async () => [
      { name: "location_id", label: "Location", type: "select", required: true, options: await lookup("locations"), full: true },
      { name: "label", label: "Label", type: "text", required: true, maxlength: 50 },
      { name: "is_favourite", label: "Favourite", type: "checkbox" },
    ],
    create: (v) => post("/api/saved-locations", { ...v, user_id: num(v.user_id), location_id: num(v.location_id) }),
    update: (r, v) => put(`/api/saved-locations/${r.saved_location_id}`, { ...v, location_id: num(v.location_id) }),
    remove: (r) => del(`/api/saved-locations/${r.saved_location_id}`),
    deleteMsg: (r) => `Saved place “${r.label}” for ${r.full_name} will be removed.`,
  },
  feedback: {
    title: "Feedback", table: "feedback", desc: "Ratings (1–5) and comments. New feedback created here is attributed to your admin account.",
    list: "/api/feedback", key: "feedback", id: "feedback_id",
    columns: ["feedback_id", "full_name", "trip_id", "rating", "comments", "submitted_at"],
    filters: [{ name: "q", label: "Search comments", type: "search" }, { name: "rating", label: "Rating", type: "select", options: ["1", "2", "3", "4", "5"] }, { name: "trip_id", label: "Trip ID", type: "number" }],
    createFields: async () => [
      { name: "trip_id", label: "Trip", type: "select", required: true, options: await lookup("trips"), full: true },
      { name: "rating", label: "Rating", type: "number", required: true, min: 1, max: 5, step: 1 },
      { name: "comments", label: "Comments", type: "textarea", maxlength: 500, full: true },
    ],
    editFields: async () => [
      { name: "rating", label: "Rating", type: "number", required: true, min: 1, max: 5, step: 1 },
      { name: "comments", label: "Comments", type: "textarea", maxlength: 500, full: true },
    ],
    create: (v) => post("/api/feedback", { ...v, trip_id: num(v.trip_id) }),
    update: (r, v) => put(`/api/feedback/${r.feedback_id}`, v),
    remove: (r) => del(`/api/feedback/${r.feedback_id}`),
    deleteMsg: (r) => `Feedback #${r.feedback_id} by ${r.full_name} will be permanently deleted.`,
  },
};

const state = { key: null, rows: [] };

function renderTabs() {
  $("#admin-tabs").innerHTML = Object.entries(MANAGERS).map(([k, m]) =>
    `<button class="tab ${state.key === k ? "active" : ""}" role="tab" aria-selected="${state.key === k}" data-key="${k}">${esc(m.title)}</button>`).join("");
}

function renderFilters(m) {
  const form = $("#mgr-filters");
  form.innerHTML = m.filters.map((f) => {
    const id = `mf-${f.name}`;
    if (f.type === "select") return `<div class="field"><label for="${id}">${esc(f.label)}</label><select id="${id}" name="${f.name}"><option value="">Any</option>${f.options.map((o) => `<option>${esc(o)}</option>`).join("")}</select></div>`;
    if (f.type === "number") return `<div class="field"><label for="${id}">${esc(f.label)}</label><input id="${id}" name="${f.name}" type="number" min="0" step="1"></div>`;
    return `<div class="field wide"><label for="${id}">${esc(f.label)}</label><input id="${id}" name="${f.name}" type="search"></div>`;
  }).join("");
  form.style.display = m.filters.length ? "" : "none";
}

async function load() {
  const m = MANAGERS[state.key];
  const box = $("#mgr-table");
  box.innerHTML = loadingHTML(`Loading ${m.title.toLowerCase()}…`);
  const params = Object.fromEntries([...new FormData($("#mgr-filters")).entries()].filter(([, v]) => v.trim() !== ""));
  try {
    const data = await get(m.list, params);
    state.rows = data[m.key];
    renderTable(box, {
      columns: m.columns.map((c) => ({ key: c, num: state.rows.some((r) => typeof r[c] === "number") })),
      rows: state.rows, idKey: m.id,
      actions: (r) => `${m.rowActions ? m.rowActions(r) : ""}
        <button class="btn btn-sm btn-secondary" data-act="edit" data-id="${r[m.id]}">Edit</button>
        ${!m.canDelete || m.canDelete(r) ? `<button class="btn btn-sm btn-danger" data-act="delete" data-id="${r[m.id]}" aria-label="Delete record">✕</button>` : ""}`,
    });
    const meta = box.querySelector(".table-meta span:last-child");
    if (meta) meta.textContent = `table: ${m.table}`;
  } catch (e) {
    box.innerHTML = emptyHTML(`Could not load ${m.title.toLowerCase()}`, e.message, "!");
  }
}

async function select(key) {
  state.key = key;
  history.replaceState(null, "", `#${key}`);
  const m = MANAGERS[key];
  renderTabs();
  $("#mgr-title").textContent = m.title;
  $("#mgr-desc").innerHTML = `<code>${m.table}</code> — ${esc(m.desc)}`;
  renderFilters(m);
  await load();
}

async function onAdd() {
  const m = MANAGERS[state.key];
  try {
    const fields = await m.createFields();
    const ok = await formModal({ title: `Add ${m.title.toLowerCase().replace(/s$/, "")}`, fields, submitText: "Create", extra: m.extra, onSubmit: m.create });
    if (ok) { m.after?.(); toast("Record created.", "success"); load(); }
  } catch (e) { showError(e); }
}

async function onTableClick(e) {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const m = MANAGERS[state.key];
  const row = state.rows.find((r) => String(r[m.id]) === btn.dataset.id);
  try {
    if (btn.dataset.act === "edit") {
      const fields = await m.editFields();
      const ok = await formModal({ title: `Edit ${m.table} #${row[m.id]}`, fields, values: row, extra: m.extra, onSubmit: (v) => m.update(row, v) });
      if (ok) { m.after?.(); toast("Record updated.", "success"); load(); }
    } else if (btn.dataset.act === "delete") {
      if (!(await confirmDialog({ title: `Delete ${m.table} #${row[m.id]}?`, message: m.deleteMsg(row) + " This cannot be undone." }))) return;
      await m.remove(row);
      m.after?.();
      toast("Record deleted.", "success");
      load();
    } else if (m.custom?.[btn.dataset.act]) {
      await m.custom[btn.dataset.act](row);
      load();
    }
  } catch (err) { showError(err); }
}

function init() {
  get("/api/health").then((h) => { $("#health").innerHTML = `<span class="status-dot"></span> PostgreSQL ${esc(h.server_version)} · ${h.database_name}`; })
    .catch(() => { $("#health").innerHTML = `<span class="status-dot down"></span> Database unavailable`; });
  $("#admin-tabs").addEventListener("click", (e) => { const b = e.target.closest("[data-key]"); if (b) select(b.dataset.key); });
  $("#mgr-add").addEventListener("click", onAdd);
  $("#mgr-table").addEventListener("click", onTableClick);
  $("#mgr-filters").addEventListener("input", debounce(load, 300));
  $("#mgr-filters").addEventListener("submit", (e) => { e.preventDefault(); load(); });
  window.addEventListener("hashchange", () => {
    const h = location.hash.replace("#", "");
    if (MANAGERS[h] && h !== state.key) select(h);
  });
  const k = location.hash.replace("#", "");
  select(MANAGERS[k] ? k : "users");
}
init();
