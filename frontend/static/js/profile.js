// Profile page: preference upsert and feedback CRUD for the signed-in user.
import { del, get, post, put } from "./api.js";
import {
  $, bindForm, confirmDialog, debounce, emptyHTML, esc, fieldHTML, formModal, initChrome, loadingHTML,
  renderTable, showError, toast, user,
} from "./ui.js";

initChrome();
const state = { feedback: [], trips: [] };

const prefFields = [
  { name: "preferred_mode", label: "Preferred travel mode", type: "select", required: true, options: ["driving", "transit", "cycling", "walking"], full: true },
  { name: "max_walking_km", label: "Maximum walking distance (km)", type: "number", min: 0, max: 999.9, step: 0.1, full: true },
  { name: "avoid_tolls", label: "Avoid tolls", type: "checkbox", full: true },
  { name: "avoid_highways", label: "Avoid highways", type: "checkbox", full: true },
  { name: "prioritize_safety", label: "Prioritise safety", type: "checkbox", full: true },
];

async function loadPreference() {
  const { preference } = await get("/api/preferences/me");
  const p = preference || { preferred_mode: "", max_walking_km: 2.0, avoid_tolls: false, avoid_highways: false, prioritize_safety: true };
  $("#pref-fields").innerHTML = prefFields.map((f) => fieldHTML(f, p[f.name])).join("");
  if (!preference) $("#pref-alert").innerHTML = `<div class="form-alert warn">You have no preference profile yet, so View 6 cannot score your trips. Save one below.</div>`;
}

function fbParams() {
  return Object.fromEntries([...new FormData($("#fb-filters")).entries()].filter(([, v]) => v.trim() !== ""));
}

async function loadFeedback() {
  const box = $("#fb-table");
  box.innerHTML = loadingHTML();
  try {
    const data = await get("/api/feedback", { ...fbParams(), user_id: user.user_role === "admin" ? user.user_id : undefined });
    state.feedback = data.feedback;
    $("#fb-count").textContent = `${data.count} feedback record${data.count === 1 ? "" : "s"}`;
    renderTable(box, {
      columns: [
        { key: "trip_id", label: "Trip", num: true },
        { key: "route", label: "Journey", render: (r) => `${esc(r.origin)} → ${esc(r.destination)}` },
        { key: "rating" },
        { key: "comments" },
        { key: "submitted_at", label: "Submitted" },
      ],
      rows: data.feedback, idKey: "feedback_id",
      emptyTitle: "No feedback yet", emptyText: "Rate one of your trips to help improve recommendations.",
      actions: (r) => `<button class="btn btn-sm btn-secondary" data-act="edit" data-id="${r.feedback_id}">Edit</button>
        <button class="btn btn-sm btn-danger" data-act="delete" data-id="${r.feedback_id}" aria-label="Delete feedback">✕</button>`,
    });
  } catch (e) {
    box.innerHTML = emptyHTML("Could not load feedback", e.message, "!");
  }
}

const fbFields = (withTrip) => [
  ...(withTrip ? [{ name: "trip_id", label: "Trip", type: "select", required: true, full: true,
    options: state.trips.map((t) => ({ value: t.trip_id, label: `#${t.trip_id} ${t.origin} → ${t.destination}` })) }] : []),
  { name: "rating", label: "Rating (1–5)", type: "number", required: true, min: 1, max: 5, step: 1 },
  { name: "comments", label: "Comments", type: "textarea", maxlength: 500, full: true },
];

async function init() {
  try { await loadPreference(); } catch (e) { showError(e); }
  bindForm($("#pref-form"), prefFields, async (v) => {
    await put("/api/preferences/me", v);
    $("#pref-alert").innerHTML = "";
    toast("Preferences saved. Route preference scores are recalculated by View 6 automatically.", "success");
  }, { alertBox: $("#pref-alert") });

  get("/api/trips", user.user_role === "admin" ? { user_id: user.user_id } : {}).then((d) => { state.trips = d.trips; }).catch(showError);
  $("#fb-filters").addEventListener("input", debounce(loadFeedback, 300));
  $("#fb-filters").addEventListener("submit", (e) => { e.preventDefault(); loadFeedback(); });
  $("#fb-add").addEventListener("click", async () => {
    if (!state.trips.length) { toast("You need a trip before you can leave feedback.", "warn"); return; }
    const ok = await formModal({ title: "Add trip feedback", fields: fbFields(true), submitText: "Submit",
      onSubmit: (v) => post("/api/feedback", { ...v, trip_id: Number(v.trip_id) }) });
    if (ok) { toast("Feedback submitted.", "success"); loadFeedback(); }
  });
  $("#fb-table").addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const f = state.feedback.find((x) => String(x.feedback_id) === btn.dataset.id);
    if (btn.dataset.act === "edit") {
      const ok = await formModal({ title: `Edit feedback for trip #${f.trip_id}`, fields: fbFields(false), values: f,
        onSubmit: (v) => put(`/api/feedback/${f.feedback_id}`, v) });
      if (ok) { toast("Feedback updated.", "success"); loadFeedback(); }
    } else if (btn.dataset.act === "delete") {
      if (!(await confirmDialog({ title: "Delete feedback?", message: `Your feedback for trip #${f.trip_id} will be permanently deleted.` }))) return;
      try { await del(`/api/feedback/${f.feedback_id}`); toast("Feedback deleted.", "success"); loadFeedback(); } catch (err) { showError(err); }
    }
  });
  loadFeedback();
}
init();
