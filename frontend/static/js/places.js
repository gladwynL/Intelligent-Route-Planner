// Places page: locations CRUD, saved locations CRUD, display-only weather lookup.
import { del, get, post, put } from "./api.js";
import {
  $, canEdit, confirmDialog, debounce, emptyHTML, esc, fmtDate, fmtNum, formModal, initChrome, isAdmin,
  loadingHTML, renderTable, setBusy, sevBadge, showError, toast,
} from "./ui.js";

initChrome();
const state = { locations: [], allLocations: [], saved: [] };
const TYPES = ["home", "work", "school", "public", "other"];

const locationFields = [
  { name: "location_name", label: "Location name", type: "text", required: true, maxlength: 120, full: true },
  { name: "street_address", label: "Street address", type: "text", required: true, maxlength: 180, full: true },
  { name: "city", label: "City", type: "text", required: true, maxlength: 80 },
  { name: "location_type", label: "Type", type: "select", required: true, options: TYPES },
  { name: "latitude", label: "Latitude", type: "number", required: true, min: -90, max: 90, step: 0.000001, hint: "Decimal degrees, −90 to 90" },
  { name: "longitude", label: "Longitude", type: "number", required: true, min: -180, max: 180, step: 0.000001, hint: "Decimal degrees, −180 to 180" },
];

function filters() {
  return Object.fromEntries([...new FormData($("#loc-filters")).entries()].filter(([, v]) => v.trim() !== ""));
}

async function loadLocations() {
  const box = $("#loc-table");
  box.innerHTML = loadingHTML();
  try {
    const data = await get("/api/locations", filters());
    state.locations = data.locations;
    $("#loc-count").textContent = `${data.count} location${data.count === 1 ? "" : "s"}`;
    renderTable(box, {
      columns: [
        { key: "location_id", label: "ID", num: true },
        { key: "location_name", label: "Name", render: (r) => `<b>${esc(r.location_name)}</b><div class="faint small">${esc(r.street_address)}</div>` },
        { key: "city" },
        { key: "location_type", label: "Type", render: (r) => `<span class="badge badge-neutral">${esc(r.location_type)}</span>` },
        { key: "coords", label: "Coordinates", render: (r) => `<span class="small nowrap">${fmtNum(r.latitude, 5)}, ${fmtNum(r.longitude, 5)}</span>` },
        { key: "trip_count", label: "Trips", num: true },
      ],
      rows: data.locations,
      emptyTitle: "No locations match",
      actions: (r) => `<button class="btn btn-sm btn-accent" data-act="weather" data-id="${r.location_id}">Weather</button>
        ${isAdmin ? `<button class="btn btn-sm btn-secondary" data-act="edit" data-id="${r.location_id}">Edit</button>
        <button class="btn btn-sm btn-danger" data-act="delete" data-id="${r.location_id}" aria-label="Delete location">✕</button>` : ""}`,
    });
  } catch (e) {
    box.innerHTML = emptyHTML("Could not load locations", e.message, "!");
  }
}

async function showWeather(loc, btn) {
  const box = $("#loc-weather");
  setBusy(btn, true);
  box.innerHTML = loadingHTML("Contacting Open-Meteo…");
  try {
    const { weather: w, disclaimer } = await get(`/api/weather/locations/${loc.location_id}`);
    box.innerHTML = `<div class="weather-card" data-testid="weather-card">
      <div><div class="temp">${w.temperature_c !== null ? `${fmtNum(w.temperature_c, 1)}°C` : "—"}</div><div class="small muted">${esc(w.condition)}</div></div>
      <div><div class="row between"><b>${esc(loc.location_name)}</b>${sevBadge(w.severity)}</div>
        <dl class="mt-1">
          <div><dt>Wind</dt><dd>${fmtNum(w.wind_speed_kmh, 0)} km/h</dd></div>
          <div><dt>Gusts</dt><dd>${fmtNum(w.wind_gusts_kmh, 0)} km/h</dd></div>
          <div><dt>Precipitation</dt><dd>${fmtNum(w.precipitation_mm, 1)} mm</dd></div>
          <div><dt>Observed</dt><dd>${fmtDate(w.observed_at)}</dd></div>
        </dl></div></div>
      <p class="faint small mt-2">${esc(disclaimer)} Source: Open-Meteo. Risk mapping: ${esc(w.risk_reasons.join("; "))}</p>`;
  } catch (e) {
    box.innerHTML = `<div class="form-alert error">${esc(e.message)}</div>`;
  } finally {
    setBusy(btn, false);
  }
}

async function addLocation() {
  const ok = await formModal({
    title: "Add a location", fields: locationFields, submitText: "Add location",
    intro: "Tip: right-click a spot in any online map to copy its latitude and longitude.",
    onSubmit: (v) => post("/api/locations", v),
  });
  if (ok) { toast("Location added.", "success"); await loadLocations(); state.allLocations = (await get("/api/locations")).locations; }
}

async function editLocation(loc) {
  const ok = await formModal({ title: `Edit ${loc.location_name}`, fields: locationFields, values: loc, onSubmit: (v) => put(`/api/locations/${loc.location_id}`, v) });
  if (ok) { toast("Location updated.", "success"); loadLocations(); loadSaved(); }
}

async function deleteLocation(loc) {
  if (!(await confirmDialog({ title: `Delete ${loc.location_name}?`, message: "This cannot be undone. Locations used by trips or route segments cannot be deleted; saved-place entries for it will be removed." }))) return;
  try { await del(`/api/locations/${loc.location_id}`); toast("Location deleted.", "success"); loadLocations(); loadSaved(); } catch (e) { showError(e); }
}

// ---- saved places
async function loadSaved() {
  const box = $("#saved-list");
  if (!box) return;
  box.innerHTML = loadingHTML();
  try {
    const data = await get("/api/saved-locations");
    state.saved = data.saved_locations;
    if (!state.saved.length) { box.innerHTML = emptyHTML("No saved places yet", "Save locations you visit often."); return; }
    box.innerHTML = `<div class="table-wrap"><table class="data"><thead><tr><th>Fav.</th><th>Label</th><th>Location</th>${isAdmin ? "<th>User</th>" : ""}<th class="num">Actions</th></tr></thead><tbody>
      ${state.saved.map((s) => `<tr data-id="${s.saved_location_id}">
        <td><button class="fav-btn ${s.is_favourite ? "on" : ""}" data-sact="fav" aria-label="${s.is_favourite ? "Remove from" : "Add to"} favourites" aria-pressed="${s.is_favourite}">★</button></td>
        <td><b>${esc(s.label)}</b><div class="faint small">saved ${fmtDate(s.saved_at, false)}</div></td>
        <td>${esc(s.location_name)}<div class="faint small">${esc(s.city)}</div></td>
        ${isAdmin ? `<td class="small">${esc(s.full_name)}</td>` : ""}
        <td class="actions"><button class="btn btn-sm btn-secondary" data-sact="edit">Edit</button>
          <button class="btn btn-sm btn-danger" data-sact="delete" aria-label="Remove saved place">✕</button></td></tr>`).join("")}
      </tbody></table></div>`;
  } catch (e) {
    box.innerHTML = emptyHTML("Could not load saved places", e.message, "!");
  }
}

const savedFields = () => [
  { name: "location_id", label: "Location", type: "select", required: true, full: true,
    options: state.allLocations.map((l) => ({ value: l.location_id, label: `${l.location_name} (${l.city})` })) },
  { name: "label", label: "Label", type: "text", required: true, maxlength: 50, placeholder: "e.g. Home, Gym, Work" },
  { name: "is_favourite", label: "Mark as favourite", type: "checkbox" },
];

async function addSaved() {
  const ok = await formModal({ title: "Save a place", fields: savedFields(), submitText: "Save place",
    onSubmit: (v) => post("/api/saved-locations", { ...v, location_id: Number(v.location_id) }) });
  if (ok) { toast("Place saved.", "success"); loadSaved(); }
}

async function onSavedAction(e) {
  const btn = e.target.closest("[data-sact]");
  if (!btn) return;
  const s = state.saved.find((x) => x.saved_location_id === Number(btn.closest("tr").dataset.id));
  try {
    if (btn.dataset.sact === "fav") {
      await put(`/api/saved-locations/${s.saved_location_id}`, { is_favourite: !s.is_favourite });
      toast(s.is_favourite ? "Removed from favourites." : "Added to favourites.", "success");
      loadSaved();
    } else if (btn.dataset.sact === "edit") {
      const ok = await formModal({ title: `Edit “${s.label}”`, fields: savedFields(), values: s,
        onSubmit: (v) => put(`/api/saved-locations/${s.saved_location_id}`, { ...v, location_id: Number(v.location_id) }) });
      if (ok) { toast("Saved place updated.", "success"); loadSaved(); }
    } else if (btn.dataset.sact === "delete") {
      if (!(await confirmDialog({ title: "Remove saved place?", message: `“${s.label}” will be removed from your saved places. The location itself is kept.`, confirmText: "Remove" }))) return;
      await del(`/api/saved-locations/${s.saved_location_id}`);
      toast("Saved place removed.", "success");
      loadSaved();
    }
  } catch (err) { showError(err); }
}

async function init() {
  $("#loc-filters").addEventListener("input", debounce(loadLocations, 300));
  $("#loc-filters").addEventListener("submit", (e) => { e.preventDefault(); loadLocations(); });
  $("#loc-table").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const loc = state.locations.find((l) => String(l.location_id) === btn.dataset.id);
    ({ weather: showWeather, edit: editLocation, delete: deleteLocation })[btn.dataset.act](loc, btn);
  });
  $("#add-location-btn")?.addEventListener("click", addLocation);
  $("#add-saved-btn")?.addEventListener("click", addSaved);
  $("#saved-list")?.addEventListener("click", onSavedAction);
  await loadLocations();
  state.allLocations = [...state.locations];
  if (canEdit) loadSaved();
}
init();
