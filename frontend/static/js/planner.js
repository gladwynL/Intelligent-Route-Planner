// Route Planner page: trip CRUD, route comparison, recommendation explanation, weather.
import { del, exportUrl, get, post, put } from "./api.js";
import {
  $, bindForm, canEdit, confirmDialog, debounce, emptyHTML, esc, fieldHTML, fmtDate, fmtNum, formModal,
  initChrome, isAdmin, loadingHTML, modeBadge, money, setBusy, sevBadge, showError, sourceBadge, stars,
  statusBadge, toast, user,
} from "./ui.js";

initChrome();

const WEIGHTS = { time_score: 0.45, distance_score: 0.25, safety_score: 0.15, toll_score: 0.10, preference_score: 0.05 };
const COMPONENT_LABELS = { time_score: "Time", distance_score: "Distance", safety_score: "Safety", toll_score: "Toll", preference_score: "Preference" };
const COMPONENT_COLORS = { time_score: "#1f5fa8", distance_score: "#0f9d8a", safety_score: "#7c4dbd", toll_score: "#d97706", preference_score: "#94a3b8" };
const MODES = ["driving", "transit", "cycling", "walking"];

const state = { locations: [], trips: [], current: null, chart: null, map: null };
const locLabel = (l) => `${l.location_name} (${l.city})`;
const locOptions = () => state.locations.map((l) => ({ value: l.location_id, label: locLabel(l) }));

// ------------------------------------------------------------------ plan form
function planFields() {
  const now = new Date(Date.now() + 3600e3);
  now.setMinutes(0, 0, 0);
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  return [
    { name: "origin_location_id", label: "Origin", type: "select", required: true, options: locOptions(), full: true },
    { name: "destination_location_id", label: "Destination", type: "select", required: true, options: locOptions(), full: true },
    { name: "departure_time", label: "Departure time", type: "datetime", required: true, value: local, full: true },
    { name: "generate_routes", label: "Generate estimated alternatives for each travel mode", type: "checkbox", value: true, full: true,
      hint: "Uses OSRM for driving when reachable, otherwise a labelled straight-line heuristic." },
  ];
}
const differentPlaces = (v) =>
  v.origin_location_id && v.origin_location_id === v.destination_location_id
    ? { destination_location_id: "Destination must be different from the origin." } : null;

function setupPlanForm() {
  const form = $("#plan-form");
  if (!form) return;
  const fields = planFields();
  $("#plan-fields").innerHTML = fields.map((f) => fieldHTML(f, f.value)).join("");
  bindForm(form, fields, async (v) => {
    const res = await post("/api/trips", {
      origin_location_id: Number(v.origin_location_id),
      destination_location_id: Number(v.destination_location_id),
      departure_time: v.departure_time,
      generate_routes: v.generate_routes,
    });
    const n = res.generated_routes.length;
    toast(`Trip #${res.trip.trip_id} created${n ? ` with ${n} estimated alternatives` : ""}.`, "success");
    form.reset();
    $("#plan-fields").innerHTML = planFields().map((f) => fieldHTML(f, f.value)).join("");
    await loadTrips();
    openTrip(res.trip.trip_id);
  }, { extra: differentPlaces, alertBox: $("#plan-alert") });
}

// ------------------------------------------------------------------ trip list
function tripFilters() {
  const fd = new FormData($("#trip-filters"));
  return Object.fromEntries([...fd.entries()].filter(([, v]) => String(v).trim() !== ""));
}

async function loadTrips() {
  const list = $("#trip-list");
  list.innerHTML = loadingHTML("Loading trips…");
  const params = tripFilters();
  $("#trips-csv").href = exportUrl("/api/export/trips", "csv", params);
  $("#trips-pdf").href = exportUrl("/api/export/trips", "pdf", params);
  try {
    const data = await get("/api/trips", params);
    state.trips = data.trips;
    $("#trip-count").textContent = `${data.count} trip${data.count === 1 ? "" : "s"} found`;
    if (!data.trips.length) {
      list.innerHTML = emptyHTML("No trips found", canEdit ? "Plan a new trip or change the filters." : "Guest accounts have no trips of their own.");
      return;
    }
    list.innerHTML = data.trips.map((t) => `
      <button type="button" class="trip-item ${state.current?.trip.trip_id === t.trip_id ? "active" : ""}" data-trip="${t.trip_id}">
        <div class="route-line"><span class="faint">#${t.trip_id}</span> ${esc(t.origin)} <span class="faint">→</span> ${esc(t.destination)}</div>
        <div class="meta">${statusBadge(t.trip_status)} <span>${fmtDate(t.departure_time)}</span>
          <span>${t.route_count} option${t.route_count === 1 ? "" : "s"}</span>
          ${t.recommended_mode ? `<span title="Database recommendation">★ ${esc(t.recommended_mode)}</span>` : ""}
          ${isAdmin ? `<span>· ${esc(t.full_name)}</span>` : ""}</div>
      </button>`).join("");
  } catch (e) {
    list.innerHTML = emptyHTML("Could not load trips", e.message, "!");
  }
}

// ------------------------------------------------------------------ trip detail
async function openTrip(id) {
  const box = $("#trip-detail");
  box.innerHTML = `<section class="card">${loadingHTML("Loading trip…")}</section>`;
  history.replaceState(null, "", `#trip=${id}`);
  try {
    state.current = await get(`/api/trips/${id}`);
    document.querySelectorAll(".trip-item").forEach((b) => b.classList.toggle("active", Number(b.dataset.trip) === id));
    renderTrip();
  } catch (e) {
    state.current = null;
    box.innerHTML = `<section class="card">${emptyHTML("Trip unavailable", e.message, "!")}</section>`;
  }
}

function ownsCurrent() {
  return canEdit && (isAdmin || state.current?.trip.user_id === user.user_id);
}

function renderTrip() {
  const { trip, routes, preferred_mode } = state.current;
  const box = $("#trip-detail");
  const editable = ownsCurrent();
  const best = routes.find((r) => r.recommendation_rank === 1);
  const selected = routes.find((r) => r.is_selected);
  const fastest = routes.length ? routes.reduce((a, b) => (a.estimated_duration_min <= b.estimated_duration_min ? a : b)) : null;
  const unscored = routes.length && routes.every((r) => r.total_route_score === null);

  box.innerHTML = `
  <section class="card" aria-labelledby="trip-h">
    <div class="card-header">
      <div>
        <h2 id="trip-h">Trip #${trip.trip_id}: ${esc(trip.origin)} → ${esc(trip.destination)}</h2>
        <p>${statusBadge(trip.trip_status)} Departs ${fmtDate(trip.departure_time)} · requested ${fmtDate(trip.requested_at)}
          ${trip.actual_duration_min ? ` · actual ${trip.actual_duration_min} min` : ""}
          ${isAdmin ? ` · traveller: <b>${esc(trip.full_name)}</b>` : ""}
          ${preferred_mode ? ` · preferred mode: ${modeBadge(preferred_mode)}` : ""}</p>
      </div>
      ${editable ? `<div class="btn-group">
        <button class="btn btn-sm btn-accent" id="gen-btn" type="button">Generate alternatives</button>
        <button class="btn btn-sm btn-secondary" id="add-route-btn" type="button">Add route</button>
        <button class="btn btn-sm btn-secondary" id="edit-trip-btn" type="button">Edit trip</button>
        <button class="btn btn-sm btn-danger" id="del-trip-btn" type="button">Delete</button>
      </div>` : ""}
    </div>
    <div class="card-body stack" style="gap:14px">
      ${unscored ? `<div class="notice">This traveller has no preference profile, so View 6 cannot score these routes. Set preferences on the My Profile page.</div>` : ""}
      <div class="reco-grid">
        <div class="reco best"><div class="label">Database recommendation</div>
          <div class="value">${best ? `${modeBadge(best.travel_mode)} <span>${fmtNum(best.total_route_score)}</span>` : "—"}</div>
          <div class="sub">${best ? `Rank 1 of ${routes.length} in View 6 · option ${best.option_number}` : "No scored alternatives yet"}</div></div>
        <div class="reco"><div class="label">Your selected route</div>
          <div class="value">${selected ? `${modeBadge(selected.travel_mode)} <span>${fmtNum(selected.total_route_score)}</span>` : "None selected"}</div>
          <div class="sub">${selected ? (best && selected.route_id === best.route_id ? "Matches the recommendation" : `Rank ${selected.recommendation_rank ?? "—"} — chosen manually`) : "Use “Select” on a route below"}</div></div>
        <div class="reco"><div class="label">Fastest alternative</div>
          <div class="value">${fastest ? `${modeBadge(fastest.travel_mode)} <span>${fastest.estimated_duration_min} min</span>` : "—"}</div>
          <div class="sub">${fastest ? `${fmtNum(fastest.distance_km)} km · ${money(fastest.toll_cost)} toll` : ""}</div></div>
      </div>
      <div id="map" role="img" aria-label="Map of origin and destination"></div>
      <p class="faint small">Map shows origin and destination markers with a straight connecting line — not the actual road geometry.</p>
    </div>
  </section>

  <section class="card" aria-labelledby="cmp-h">
    <div class="card-header"><div><h2 id="cmp-h">Route comparison</h2><p>Scores come directly from <code>v6_ranked_route_recommendations</code>; condition data from <code>v7_condition_risk_by_route</code>.</p></div></div>
    <div class="card-body flush" id="routes-table"></div>
  </section>

  <section class="card" aria-labelledby="why-h">
    <div class="card-header"><div><h2 id="why-h">Why this ranking?</h2><p>Each component is scored 0–100, then weighted. Bars show each component's weighted contribution to the total.</p></div></div>
    <div class="card-body stack" style="gap:14px">
      <div class="weights">${Object.entries(WEIGHTS).map(([k, w]) => `<div class="weight"><b>${w * 100}%</b><span>${COMPONENT_LABELS[k]}</span></div>`).join("")}</div>
      <div id="why-text" class="small"></div>
      <div class="chart-box short"><canvas id="why-chart" aria-label="Weighted score contributions per route"></canvas></div>
      <details class="small muted"><summary>How each component is calculated</summary>
        <ul>
          <li><b>Time</b> = 100 × fastest duration in this trip ÷ route duration.</li>
          <li><b>Distance</b> = 100 × shortest distance in this trip ÷ route distance.</li>
          <li><b>Safety</b> = 100 − 20 × highest observed condition severity (0–5) on the route's segments.</li>
          <li><b>Toll</b> = 100 − 20 × toll cost in dollars (never below 0).</li>
          <li><b>Preference</b> = 100 if the mode matches the traveller's preferred mode, otherwise 50.</li>
        </ul></details>
    </div>
  </section>

  <section class="card" aria-labelledby="wx-h">
    <div class="card-header"><div><h2 id="wx-h">Conditions &amp; live weather</h2><p>Use “Weather” on a route to fetch current Open-Meteo conditions for its segments and store them in PostgreSQL.</p></div></div>
    <div class="card-body" id="weather-result"></div>
    <div class="card-body flush" id="trip-obs"></div>
  </section>

  <section class="card" aria-labelledby="fb-h">
    <div class="card-header"><div><h2 id="fb-h">Trip feedback</h2><p>Rate how well the route results matched the actual trip.</p></div></div>
    <div class="card-body" id="trip-feedback"></div>
  </section>`;

  renderRoutes();
  renderWhy();
  renderMap();
  loadTripObservations();
  renderFeedback();
  if (editable) {
    $("#gen-btn").onclick = generateRoutes;
    $("#add-route-btn").onclick = addRoute;
    $("#edit-trip-btn").onclick = editTrip;
    $("#del-trip-btn").onclick = deleteTrip;
  }
}

function scoreCell(v) {
  if (v === null || v === undefined) return `<span class="null">—</span>`;
  return `<div class="score"><div class="bar"><span style="width:${Math.max(0, Math.min(100, v))}%"></span></div><b>${fmtNum(v)}</b></div>`;
}

function renderRoutes() {
  const { routes } = state.current;
  const box = $("#routes-table");
  const editable = ownsCurrent();
  if (!routes.length) {
    box.innerHTML = emptyHTML("No route alternatives yet", editable ? "Generate estimated alternatives or add a route manually." : "");
    return;
  }
  box.innerHTML = `<div class="table-wrap"><table class="data compact">
    <thead><tr>
      <th scope="col">Rank</th><th scope="col">Mode</th><th class="num" scope="col">Distance</th><th class="num" scope="col">Est. time</th>
      <th class="num" scope="col">Toll</th><th class="num" scope="col">Max severity</th>
      <th class="num" scope="col" title="Time score (45%)">Time</th><th class="num" scope="col" title="Distance score (25%)">Dist.</th>
      <th class="num" scope="col" title="Safety score (15%)">Safety</th><th class="num" scope="col" title="Toll score (10%)">Toll sc.</th>
      <th class="num" scope="col" title="Preference score (5%)">Pref.</th><th scope="col">Total score</th>
      <th scope="col">Source</th>${editable ? `<th class="num" scope="col">Actions</th>` : ""}
    </tr></thead>
    <tbody>${routes.map((r) => `
      <tr data-route="${r.route_id}">
        <td class="nowrap">${r.recommendation_rank ? `<span class="badge ${r.recommendation_rank === 1 ? "badge-success" : "badge-neutral"}">#${r.recommendation_rank}</span>` : "—"}
          ${r.is_selected ? `<span class="badge badge-primary" title="Route selected by the traveller">Selected</span>` : ""}</td>
        <td>${modeBadge(r.travel_mode)}<div class="faint small via" title="${esc(r.via || "")}">${esc(r.via || "")}</div></td>
        <td class="num">${fmtNum(r.distance_km)} km</td>
        <td class="num">${r.estimated_duration_min} min</td>
        <td class="num">${money(r.toll_cost)}</td>
        <td class="num">${sevBadge(r.maximum_severity)}<div class="faint small">${r.observation_count ?? 0} obs.</div></td>
        <td class="num">${fmtNum(r.time_score)}</td><td class="num">${fmtNum(r.distance_score)}</td>
        <td class="num">${fmtNum(r.safety_score)}</td><td class="num">${fmtNum(r.toll_score)}</td>
        <td class="num">${fmtNum(r.preference_score)}</td>
        <td>${scoreCell(r.total_route_score)}</td>
        <td>${sourceBadge(r.source)}</td>
        ${editable ? `<td class="actions">
          ${r.is_selected ? "" : `<button class="btn btn-sm btn-primary" data-act="select">Select</button>`}
          <button class="btn btn-sm btn-accent" data-act="weather" title="Fetch and store live weather for this route">Weather</button>
          <button class="btn btn-sm btn-secondary" data-act="edit">Edit</button>
          <button class="btn btn-sm btn-danger" data-act="delete" aria-label="Delete route">✕</button></td>` : ""}
      </tr>`).join("")}</tbody></table></div>
    <div class="table-meta"><span>${routes.length} alternative${routes.length === 1 ? "" : "s"} · ranked by total score (DENSE_RANK in View 6)</span><span></span></div>`;
  box.querySelectorAll("[data-act]").forEach((btn) => btn.addEventListener("click", () => {
    const route = routes.find((r) => r.route_id === Number(btn.closest("tr").dataset.route));
    ({ select: selectRoute, weather: routeWeather, edit: editRoute, delete: deleteRoute })[btn.dataset.act](route, btn);
  }));
}

function contributions(r) {
  return Object.fromEntries(Object.entries(WEIGHTS).map(([k, w]) => [k, r[k] === null ? 0 : +(r[k] * w).toFixed(2)]));
}

function renderWhy() {
  const scored = state.current.routes.filter((r) => r.total_route_score !== null)
    .sort((a, b) => a.recommendation_rank - b.recommendation_rank || a.option_number - b.option_number);
  const text = $("#why-text");
  if (state.chart) { state.chart.destroy(); state.chart = null; }
  if (scored.length < 1) { text.innerHTML = `<span class="muted">No scored alternatives to explain yet.</span>`; return; }
  if (scored.length >= 2) {
    const [a, b] = scored;
    const ca = contributions(a), cb = contributions(b);
    const diffs = Object.keys(WEIGHTS).map((k) => [k, +(ca[k] - cb[k]).toFixed(2)]).sort((x, y) => Math.abs(y[1]) - Math.abs(x[1]));
    const pos = diffs.filter(([, d]) => d > 0).map(([k, d]) => `${COMPONENT_LABELS[k].toLowerCase()} (+${d})`);
    const neg = diffs.filter(([, d]) => d < 0).map(([k, d]) => `${COMPONENT_LABELS[k].toLowerCase()} (${d})`);
    text.innerHTML = `<p><b>${esc(a.travel_mode)}</b> (option ${a.option_number}, total ${fmtNum(a.total_route_score)}) ranks above
      <b>${esc(b.travel_mode)}</b> (option ${b.option_number}, total ${fmtNum(b.total_route_score)}).
      ${pos.length ? `It gains weighted points on ${pos.join(", ")}` : ""}${neg.length ? `${pos.length ? ", and" : "It"} loses on ${neg.join(", ")}` : ""}.</p>`;
  } else {
    text.innerHTML = `<p>Only one scored alternative exists, so it is ranked first by default.</p>`;
  }
  if (!window.Chart) return;
  state.chart = new Chart($("#why-chart"), {
    type: "bar",
    data: {
      labels: scored.map((r) => `#${r.recommendation_rank} ${r.travel_mode} (opt ${r.option_number})`),
      datasets: Object.keys(WEIGHTS).map((k) => ({
        label: `${COMPONENT_LABELS[k]} (${WEIGHTS[k] * 100}%)`, data: scored.map((r) => contributions(r)[k]),
        backgroundColor: COMPONENT_COLORS[k], borderRadius: 3, maxBarThickness: 28,
      })),
    },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      scales: { x: { stacked: true, max: 100, title: { display: true, text: "Weighted points (total score)" } }, y: { stacked: true } },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
    },
  });
}

function renderMap() {
  const el = $("#map");
  if (!window.L) { el.innerHTML = emptyHTML("Map unavailable", "The map library could not be loaded (offline?)."); return; }
  const { trip, locations } = state.current;
  const o = locations.find((l) => l.location_id === trip.origin_location_id);
  const d = locations.find((l) => l.location_id === trip.destination_location_id);
  if (state.map) state.map.remove();
  state.map = L.map(el, { scrollWheelZoom: false });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: "&copy; OpenStreetMap contributors",
  }).addTo(state.map);
  const a = [o.latitude, o.longitude], b = [d.latitude, d.longitude];
  L.circleMarker(a, { radius: 8, color: "#0f9d8a", fillOpacity: 0.9 }).addTo(state.map).bindTooltip(`Origin: ${o.location_name}`);
  L.circleMarker(b, { radius: 8, color: "#1f5fa8", fillOpacity: 0.9 }).addTo(state.map).bindTooltip(`Destination: ${d.location_name}`);
  L.polyline([a, b], { color: "#64748b", dashArray: "6 6", weight: 2 }).addTo(state.map);
  state.map.fitBounds([a, b], { padding: [40, 40], maxZoom: 15 });
  // The card may still be laying out; recompute the size once it has settled.
  setTimeout(() => { state.map?.invalidateSize(); state.map?.fitBounds([a, b], { padding: [40, 40], maxZoom: 15 }); }, 120);
}

async function loadTripObservations() {
  const box = $("#trip-obs");
  box.innerHTML = loadingHTML("Loading observations…");
  try {
    const data = await get("/api/observations", { trip_id: state.current.trip.trip_id });
    if (!data.observations.length) { box.innerHTML = emptyHTML("No condition observations", "Fetch live weather for a route to add one."); return; }
    box.innerHTML = `<div class="table-wrap"><table class="data"><thead><tr><th>Observed</th><th>Route</th><th>Segment</th><th>Type</th><th class="num">Severity</th><th>Description</th><th>Source</th></tr></thead>
      <tbody>${data.observations.map((o) => `<tr><td class="nowrap">${fmtDate(o.observed_at)}</td><td>#${o.route_id} ${modeBadge(o.travel_mode)}</td>
        <td>${esc(o.road_name)}</td><td><span class="badge badge-neutral">${esc(o.condition_type)}</span></td><td class="num">${sevBadge(o.severity)}</td>
        <td>${esc(o.description)}</td><td>${esc(o.source_name)}</td></tr>`).join("")}</tbody></table></div>`;
  } catch (e) {
    box.innerHTML = emptyHTML("Could not load observations", e.message, "!");
  }
}

function weatherCardHTML(seg, w) {
  return `<div class="weather-card">
    <div><div class="temp">${w.temperature_c !== null ? `${fmtNum(w.temperature_c, 1)}°C` : "—"}</div><div class="small muted">${esc(w.condition)}</div></div>
    <div><div class="row between"><b>${esc(seg.road_name)}</b> ${sevBadge(w.severity)}</div>
      <dl class="mt-1">
        <div><dt>Wind</dt><dd>${fmtNum(w.wind_speed_kmh, 0)} km/h</dd></div>
        <div><dt>Gusts</dt><dd>${fmtNum(w.wind_gusts_kmh, 0)} km/h</dd></div>
        <div><dt>Precipitation</dt><dd>${fmtNum(w.precipitation_mm, 1)} mm</dd></div>
        <div><dt>Observed</dt><dd>${fmtDate(w.observed_at)}</dd></div>
      </dl>
      <div class="faint small mt-1">Risk mapping: ${esc(w.risk_reasons.join("; "))}</div></div></div>`;
}

async function routeWeather(route, btn) {
  setBusy(btn, true);
  const box = $("#weather-result");
  box.innerHTML = loadingHTML("Contacting Open-Meteo…");
  try {
    const res = await post(`/api/weather/routes/${route.route_id}`);
    state.current.routes = res.routes;
    box.innerHTML = `<div class="stack" style="gap:10px">
      <div class="row between"><h3>Live weather for route #${route.route_id} (${esc(route.travel_mode)})</h3>
        <span class="badge badge-success">Saved ${res.inserted_observation_ids.length} observation(s) · IDs ${res.inserted_observation_ids.join(", ")}</span></div>
      ${res.weather.map((w) => weatherCardHTML(w.segment, w.current)).join("")}
      <p class="faint small">${esc(res.disclaimer)} Source: Open-Meteo (open-meteo.com).</p></div>`;
    toast("Live weather saved to PostgreSQL; ranking refreshed.", "success");
    renderRoutes();
    renderWhy();
    loadTripObservations();
  } catch (e) {
    box.innerHTML = `<div class="form-alert error">${esc(e.message)}</div>`;
    showError(e);
  } finally {
    setBusy(btn, false);
  }
}

async function renderFeedback() {
  const box = $("#trip-feedback");
  const { trip } = state.current;
  const mine = canEdit && trip.user_id === user.user_id;
  try {
    const data = await get("/api/feedback", { trip_id: trip.trip_id });
    const own = data.feedback.find((f) => f.user_id === user.user_id);
    const others = data.feedback.filter((f) => f.user_id !== user.user_id);
    let html = "";
    if (own) {
      html += `<div class="row between"><div>${stars(own.rating)} <span class="muted small">· ${fmtDate(own.submitted_at)}</span><p class="mt-1">${esc(own.comments || "")}</p></div>
        <div class="btn-group"><button class="btn btn-sm btn-secondary" id="fb-edit">Edit</button><button class="btn btn-sm btn-danger" id="fb-del">Delete</button></div></div>`;
    } else if (mine) {
      html += `<button class="btn btn-secondary" id="fb-add">Rate this trip</button>`;
    } else {
      html += `<p class="muted small">Only the traveller can leave feedback on this trip.</p>`;
    }
    if (isAdmin && others.length) {
      html += `<div class="mt-2"><h3 class="small">Other feedback (admin view)</h3>${others.map((f) => `<p class="small mt-1">${stars(f.rating)} <b>${esc(f.full_name)}</b>: ${esc(f.comments || "")}</p>`).join("")}</div>`;
    }
    box.innerHTML = html;
    const fields = [
      { name: "rating", label: "Rating (1–5)", type: "number", min: 1, max: 5, step: 1, required: true },
      { name: "comments", label: "Comments", type: "textarea", maxlength: 500, full: true },
    ];
    $("#fb-add")?.addEventListener("click", async () => {
      if (await formModal({ title: "Rate this trip", fields, submitText: "Submit feedback",
        onSubmit: (v) => post("/api/feedback", { ...v, trip_id: trip.trip_id }) })) { toast("Feedback submitted.", "success"); renderFeedback(); }
    });
    $("#fb-edit")?.addEventListener("click", async () => {
      if (await formModal({ title: "Edit feedback", fields, values: own,
        onSubmit: (v) => put(`/api/feedback/${own.feedback_id}`, v) })) { toast("Feedback updated.", "success"); renderFeedback(); }
    });
    $("#fb-del")?.addEventListener("click", async () => {
      if (!(await confirmDialog({ title: "Delete feedback?", message: "Your rating and comments for this trip will be removed." }))) return;
      try { await del(`/api/feedback/${own.feedback_id}`); toast("Feedback deleted.", "success"); renderFeedback(); } catch (e) { showError(e); }
    });
  } catch (e) {
    box.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
  }
}

// ------------------------------------------------------------------ actions
async function refreshCurrent() {
  await openTrip(state.current.trip.trip_id);
  loadTrips();
}

async function generateRoutes() {
  const btn = $("#gen-btn");
  setBusy(btn, true);
  try {
    const res = await post(`/api/trips/${state.current.trip.trip_id}/routes/generate`);
    toast(res.message, res.generated_routes.length ? "success" : "info");
    await refreshCurrent();
  } catch (e) { showError(e); } finally { setBusy(btn, false); }
}

const routeFields = (withRoad) => [
  { name: "travel_mode", label: "Travel mode", type: "select", required: true, options: MODES },
  { name: "distance_km", label: "Distance (km)", type: "number", required: true, min: 0.01, max: 99999, step: 0.01 },
  { name: "estimated_duration_min", label: "Estimated duration (min)", type: "number", required: true, min: 1, max: 100000, step: 1 },
  { name: "toll_cost", label: "Toll cost ($)", type: "number", min: 0, max: 99999, step: 0.01 },
  ...(withRoad ? [{ name: "road_name", label: "Road / service name", type: "text", maxlength: 90, full: true, placeholder: "e.g. Highway 407 ETR" }] : []),
];

async function addRoute() {
  const ok = await formModal({
    title: "Add a route alternative", fields: routeFields(true), values: { toll_cost: 0 }, submitText: "Add route",
    intro: "Manually entered routes are labelled as such and are scored by View 6 like any other alternative.",
    onSubmit: (v) => post(`/api/trips/${state.current.trip.trip_id}/routes`, v),
  });
  if (ok) { toast("Route added.", "success"); refreshCurrent(); }
}

async function editRoute(route) {
  const ok = await formModal({
    title: `Edit route option ${route.option_number}`, fields: routeFields(false), values: route,
    onSubmit: (v) => put(`/api/routes/${route.route_id}`, v),
  });
  if (ok) { toast("Route updated.", "success"); refreshCurrent(); }
}

async function deleteRoute(route) {
  if (!(await confirmDialog({ title: "Delete this route?", message: `Option ${route.option_number} (${route.travel_mode}) and its segments and observations will be permanently deleted.` }))) return;
  try { await del(`/api/routes/${route.route_id}`); toast("Route deleted.", "success"); refreshCurrent(); } catch (e) { showError(e); }
}

async function selectRoute(route, btn) {
  setBusy(btn, true);
  try {
    const res = await post(`/api/routes/${route.route_id}/select`);
    state.current.routes = res.routes;
    toast(`Selected the ${route.travel_mode} route.`, "success");
    renderTrip();
    loadTrips();
  } catch (e) { showError(e); setBusy(btn, false); }
}

async function editTrip() {
  const t = state.current.trip;
  const fields = [
    { name: "origin_location_id", label: "Origin", type: "select", required: true, options: locOptions(), full: true },
    { name: "destination_location_id", label: "Destination", type: "select", required: true, options: locOptions(), full: true },
    { name: "departure_time", label: "Departure time", type: "datetime", required: true },
    { name: "trip_status", label: "Status", type: "select", required: true, options: ["planned", "completed", "cancelled"] },
    { name: "actual_duration_min", label: "Actual duration (min)", type: "number", min: 1, step: 1, hint: "Only for completed trips" },
  ];
  const ok = await formModal({
    title: `Edit trip #${t.trip_id}`, fields, values: t,
    extra: (v) => ({
      ...(differentPlaces(v) || {}),
      ...(v.actual_duration_min && v.trip_status !== "completed" ? { actual_duration_min: "Only completed trips can record an actual duration." } : {}),
    }),
    onSubmit: (v) => put(`/api/trips/${t.trip_id}`, { ...v, origin_location_id: Number(v.origin_location_id), destination_location_id: Number(v.destination_location_id) }),
  });
  if (ok) { toast("Trip updated.", "success"); refreshCurrent(); }
}

async function deleteTrip() {
  const t = state.current.trip;
  if (!(await confirmDialog({ title: `Delete trip #${t.trip_id}?`, message: "All of its route options, segments, observations and feedback will be permanently deleted (ON DELETE CASCADE)." }))) return;
  try {
    await del(`/api/trips/${t.trip_id}`);
    toast("Trip deleted.", "success");
    state.current = null;
    history.replaceState(null, "", location.pathname);
    $("#trip-detail").innerHTML = `<section class="card">${emptyHTML("Select a trip", "Choose a trip from the list to compare its routes.")}</section>`;
    loadTrips();
  } catch (e) { showError(e); }
}

// ------------------------------------------------------------------ init
async function init() {
  $("#trip-detail").innerHTML = `<section class="card">${emptyHTML("Select a trip", "Choose a trip from the list to compare its route alternatives and see the recommendation.", "⇢")}</section>`;
  try {
    state.locations = (await get("/api/locations")).locations;
  } catch (e) { showError(e); }
  setupPlanForm();
  const reload = debounce(loadTrips, 300);
  $("#trip-filters").addEventListener("input", reload);
  $("#trip-filters").addEventListener("submit", (e) => { e.preventDefault(); loadTrips(); });
  $("#trip-list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-trip]");
    if (b) openTrip(Number(b.dataset.trip));
  });
  await loadTrips();
  window.addEventListener("hashchange", () => {
    const h = location.hash.match(/trip=(\d+)/);
    if (h && Number(h[1]) !== state.current?.trip.trip_id) openTrip(Number(h[1]));
  });
  const m = location.hash.match(/trip=(\d+)/);
  if (m) openTrip(Number(m[1]));
  else if (state.trips.length) openTrip(state.trips[0].trip_id);
}
init();
