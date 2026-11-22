// Conditions & Analytics: live weather integration, Chart.js visualisations, observation search.
import { exportUrl, get, post } from "./api.js";
import {
  $, canEdit, debounce, emptyHTML, esc, fmtDate, fmtNum, initChrome, loadingHTML, modeBadge, renderTable,
  setBusy, sevBadge, showError, showFieldErrors, toast,
} from "./ui.js";

initChrome();

const MODE_COLORS = { driving: "#1f5fa8", transit: "#7c4dbd", cycling: "#0f9d8a", walking: "#d97706" };
const SEV_COLORS = ["#1e8e4e", "#65a30d", "#ca8a04", "#ea580c", "#dc2626", "#7f1d1d"];
const charts = {};

function chart(id, config) {
  if (!window.Chart) { document.getElementById(id).replaceWith(Object.assign(document.createElement("p"), { className: "muted", textContent: "Chart library unavailable (offline?)." })); return; }
  charts[id]?.destroy();
  charts[id] = new Chart(document.getElementById(id), config);
}
const base = (extra = {}) => ({ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, ...extra });

async function loadAnalytics() {
  let a;
  try { a = await get("/api/analytics/summary"); } catch (e) { showError(e); return; }
  const c = a.table_counts;
  const kpis = [["Users", c.app_user], ["Locations", c.location], ["Trips", c.trip], ["Route options", c.route_option],
    ["Segments", c.route_segment], ["Observations", c.condition_observation], ["Saved places", c.saved_location], ["Feedback", c.feedback]];
  $("#kpis").innerHTML = kpis.map(([l, v]) => `<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div></div>`).join("");

  chart("chart-severity", {
    type: "bar",
    data: { labels: a.severity_distribution.map((r) => `Severity ${r.severity}`),
      datasets: [{ label: "Observations", data: a.severity_distribution.map((r) => r.observations), backgroundColor: SEV_COLORS, borderRadius: 4 }] },
    options: base({ scales: { y: { beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: "Observations" } } } }),
  });
  chart("chart-mode", {
    type: "bar",
    data: { labels: a.duration_by_mode.map((r) => r.travel_mode),
      datasets: [{ label: "Average minutes", data: a.duration_by_mode.map((r) => r.avg_duration_min),
        backgroundColor: a.duration_by_mode.map((r) => MODE_COLORS[r.travel_mode]), borderRadius: 4 }] },
    options: base({ scales: { y: { beginAtZero: true, title: { display: true, text: "Minutes" } } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: (ctx) => `${a.duration_by_mode[ctx.dataIndex].routes} routes, avg ${a.duration_by_mode[ctx.dataIndex].avg_distance_km} km` } } } }),
  });
  const trips = [...new Set(a.route_scores.map((r) => r.trip_id))];
  const modes = ["driving", "transit", "cycling", "walking"];
  chart("chart-scores", {
    type: "bar",
    data: { labels: trips.map((t) => `Trip ${t}`),
      datasets: modes.map((m) => ({ label: m, backgroundColor: MODE_COLORS[m], borderRadius: 3,
        data: trips.map((t) => a.route_scores.find((r) => r.trip_id === t && r.travel_mode === m)?.total_route_score ?? null) })) },
    options: base({ plugins: { legend: { display: true, position: "bottom", labels: { boxWidth: 12 } } },
      scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: "Total route score" } } } }),
  });
  chart("chart-types", {
    type: "bar",
    data: { labels: a.conditions_by_type.map((r) => r.condition_type),
      datasets: [
        { label: "Observations", data: a.conditions_by_type.map((r) => r.observations), backgroundColor: "#1f5fa8", borderRadius: 4, yAxisID: "y" },
        { label: "Average severity", data: a.conditions_by_type.map((r) => r.avg_severity), backgroundColor: "#d97706", borderRadius: 4, yAxisID: "y2" },
      ] },
    options: base({ plugins: { legend: { display: true, position: "bottom", labels: { boxWidth: 12 } } },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 }, position: "left" }, y2: { beginAtZero: true, max: 5, position: "right", grid: { drawOnChartArea: false } } } }),
  });
  chart("chart-ratings", {
    type: "doughnut",
    data: { labels: a.rating_distribution.map((r) => `${r.rating} star${r.rating > 1 ? "s" : ""}`),
      datasets: [{ data: a.rating_distribution.map((r) => r.count), backgroundColor: ["#dc2626", "#ea580c", "#ca8a04", "#65a30d", "#1e8e4e"] }] },
    options: base({ plugins: { legend: { display: true, position: "right" } } }),
  });
  const svr = a.selected_vs_recommended;
  $("#rating-sub").innerHTML = `<code>feedback</code> grouped by rating · ${svr.matches} of ${svr.selected_total} selected routes match the View 6 recommendation.`;
}

function obsParams() {
  return Object.fromEntries([...new FormData($("#obs-filters")).entries()].filter(([, v]) => v.trim() !== ""));
}

async function loadObservations() {
  const box = $("#obs-table");
  const params = obsParams();
  $("#obs-csv").href = exportUrl("/api/export/observations", "csv", params);
  $("#obs-pdf").href = exportUrl("/api/export/observations", "pdf", params);
  box.innerHTML = loadingHTML();
  try {
    const data = await get("/api/observations", params);
    $("#obs-count").textContent = `${data.count} observation${data.count === 1 ? "" : "s"} match`;
    renderTable(box, {
      columns: [
        { key: "observation_id", label: "ID", num: true },
        { key: "observed_at", label: "Observed" },
        { key: "condition_type", label: "Type", render: (r) => `<span class="badge badge-neutral">${esc(r.condition_type)}</span>` },
        { key: "severity", num: true },
        { key: "description" },
        { key: "source_name", label: "Source", render: (r) => r.source_name === "Open-Meteo" ? `<span class="badge badge-accent">Open-Meteo</span>` : esc(r.source_name) },
        { key: "road_name", label: "Segment" },
        { key: "route", label: "Route / trip", render: (r) => `#${r.route_id} ${modeBadge(r.travel_mode)} <span class="faint">trip ${r.trip_id}</span>` },
      ],
      rows: data.observations,
      emptyTitle: "No observations match",
    });
  } catch (e) {
    box.innerHTML = emptyHTML("Could not load observations", e.message, "!");
  }
}

async function loadRouteOptions() {
  const sel = $("#live-route");
  if (!sel) return;
  try {
    const { trips } = await get("/api/trips");
    const groups = await Promise.all(trips.slice(0, 40).map(async (t) => ({ t, routes: (await get(`/api/trips/${t.trip_id}/routes`)).routes })));
    sel.innerHTML = `<option value="">Select a route…</option>` + groups.filter((g) => g.routes.length).map(({ t, routes }) =>
      `<optgroup label="Trip #${t.trip_id}: ${esc(t.origin)} → ${esc(t.destination)}">${routes.map((r) =>
        `<option value="${r.route_id}">#${r.route_id} · ${esc(r.travel_mode)} · ${fmtNum(r.distance_km)} km · ${r.estimated_duration_min} min</option>`).join("")}</optgroup>`).join("");
  } catch (e) { showError(e); }
}

function setupLive() {
  const form = $("#live-form");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const routeId = form.elements.route_id.value;
    showFieldErrors(form, routeId ? {} : { route_id: "Choose a route first." });
    if (!routeId) return;
    const btn = $("#live-btn");
    setBusy(btn, true);
    const box = $("#live-result");
    box.innerHTML = loadingHTML("Querying segments and contacting Open-Meteo…");
    try {
      const res = await post(`/api/weather/routes/${routeId}`);
      const route = res.routes.find((r) => r.route_id === Number(routeId));
      box.innerHTML = `
        <div class="stack" style="gap:10px">
          ${res.weather.map(({ segment: s, current: w }) => `
            <div class="weather-card" data-testid="weather-card">
              <div><div class="temp">${w.temperature_c !== null ? `${fmtNum(w.temperature_c, 1)}°C` : "—"}</div><div class="small muted">${esc(w.condition)}</div></div>
              <div><div class="row between"><b>${esc(s.road_name)}</b>${sevBadge(w.severity)}</div>
                <dl class="mt-1"><div><dt>Wind</dt><dd>${fmtNum(w.wind_speed_kmh, 0)} km/h</dd></div>
                <div><dt>Gusts</dt><dd>${fmtNum(w.wind_gusts_kmh, 0)} km/h</dd></div>
                <div><dt>Precip.</dt><dd>${fmtNum(w.precipitation_mm, 1)} mm</dd></div>
                <div><dt>Observed</dt><dd>${fmtDate(w.observed_at)}</dd></div></dl></div></div>`).join("")}
          <div class="form-alert info"><b>Stored in PostgreSQL:</b> observation ID(s) ${res.inserted_observation_ids.join(", ")} ·
            ${res.stored_observations.length} Open-Meteo observation(s) now on this route ·
            route safety score ${fmtNum(route?.safety_score)} → total ${fmtNum(route?.total_route_score)} (rank ${route?.recommendation_rank ?? "—"}).</div>
          <p class="faint small">${esc(res.disclaimer)}</p>
        </div>`;
      toast("Weather fetched from Open-Meteo and saved.", "success");
      loadObservations();
      loadAnalytics();
    } catch (err) {
      box.innerHTML = `<div class="form-alert error">${esc(err.message)}</div>`;
    } finally {
      setBusy(btn, false);
    }
  });
}

async function init() {
  $("#obs-filters").addEventListener("input", debounce(loadObservations, 300));
  $("#obs-filters").addEventListener("submit", (e) => { e.preventDefault(); loadObservations(); });
  setupLive();
  await Promise.all([loadAnalytics(), loadObservations(), canEdit ? loadRouteOptions() : null]);
}
init();
