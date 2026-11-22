import { post } from "./api.js";
import { $, $$, bindForm, esc } from "./ui.js";

const form = $("#login-form");
const alertBox = $("#login-alert");
const fields = [
  { name: "email", label: "Email address", type: "email", required: true, maxlength: 150 },
  { name: "password", label: "Password", type: "password", required: true, maxlength: 200 },
];

const go = (redirect) => { window.location.href = window.LOGIN_NEXT || redirect || "/planner"; };

bindForm(form, fields, async (values) => {
  const res = await post("/api/auth/login", values);
  go(res.redirect);
}, { alertBox });

$("#guest-btn").addEventListener("click", async (e) => {
  e.target.disabled = true;
  try {
    const res = await post("/api/auth/guest");
    window.location.href = res.redirect;
  } catch (err) {
    alertBox.innerHTML = `<div class="form-alert error">${esc(err.message)}</div>`;
    e.target.disabled = false;
  }
});

$$(".demo-accounts button").forEach((b) => b.addEventListener("click", () => {
  form.elements.email.value = b.dataset.email;
  form.elements.password.value = b.dataset.pass;
  form.elements.password.focus();
}));
