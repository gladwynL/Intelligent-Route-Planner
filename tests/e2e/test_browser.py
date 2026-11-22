"""End-to-end browser tests: real Flask server + PostgreSQL test DB + headless Chromium.

Run with:  python -m pytest tests/e2e -m e2e
The weather HTTP call is mocked inside the server process for determinism
(the live API is exercised by tests/test_weather.py::test_live_open_meteo and
by scripts/capture_screenshots.py).
"""
from __future__ import annotations

import socket
import threading

import pytest
from playwright.sync_api import Page, expect, sync_playwright
from werkzeug.serving import make_server

from backend.app.services import weather as wx
from tests.conftest import ACCOUNTS
from tests.test_weather import FakeResponse, open_meteo_payload

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def live_server(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    original = wx.requests.get
    wx.requests.get = lambda *a, **k: FakeResponse(open_meteo_payload(code=61, temp=5.5))
    server = make_server("127.0.0.1", port, app, threaded=True)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    wx.requests.get = original


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser, live_server):
    ctx = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
    pg = ctx.new_page()
    pg.errors = []
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.base = live_server
    yield pg
    ctx.close()


def login(page: Page, role: str):
    email, pw, _ = ACCOUNTS[role]
    page.goto(page.base + "/login")
    page.fill("#email", email)
    page.fill("#password", pw)
    page.click("#login-submit")
    page.wait_for_url("**/planner**")


def significant_errors(page):
    # Map tiles / CDN hiccups are not application errors.
    return [e for e in page.errors if "tile.openstreetmap" not in e and "Failed to load resource" not in e]


def test_login_validation_and_failure(page):
    page.goto(page.base + "/login")
    page.click("#login-submit")
    expect(page.locator('[data-field="email"] .error')).to_have_text("Email address is required.")
    page.fill("#email", "not-an-email")
    page.fill("#password", "x")
    page.click("#login-submit")
    expect(page.locator('[data-field="email"] .error')).to_contain_text("valid email")
    page.fill("#email", "avery.morgan@example.com")
    page.fill("#password", "wrong")
    page.click("#login-submit")
    expect(page.locator("#login-alert")).to_contain_text("Invalid email or password")


@pytest.mark.parametrize("role,admin_link,profile_link,plan_form", [
    ("admin", True, True, True), ("user", False, True, True), ("guest", False, False, False),
])
def test_role_dependent_interface(page, role, admin_link, profile_link, plan_form):
    login(page, role)
    expect(page.get_by_test_id("role-badge")).to_have_text(role)
    expect(page.locator('nav a[href="/admin"]')).to_have_count(1 if admin_link else 0)
    expect(page.locator('nav a[href="/profile"]')).to_have_count(1 if profile_link else 0)
    expect(page.locator("#plan-form")).to_have_count(1 if plan_form else 0)
    resp = page.goto(page.base + "/admin")
    assert resp.status == (200 if admin_link else 403)


def test_anonymous_guest_and_logout(page):
    page.goto(page.base + "/login")
    page.click("#guest-btn")
    page.wait_for_url("**/explorer**")
    expect(page.locator("#view-access")).to_contain_text("6 of 10")
    expect(page.locator(".view-item.locked")).to_have_count(4)
    page.click("#logout-btn")
    page.wait_for_url("**/login**")
    page.goto(page.base + "/planner")
    page.wait_for_url("**/login**")


def test_navigate_all_pages_without_errors(page):
    login(page, "admin")
    for path, marker in [("/planner", "#routes-table table"), ("/places", "#loc-table table"),
                         ("/explorer", "#view-table table"), ("/conditions", "#obs-table table"),
                         ("/profile", "#pref-form"), ("/admin", "#mgr-table table")]:
        page.goto(page.base + path)
        page.wait_for_selector(marker)
        page.wait_for_load_state("networkidle")
    assert significant_errors(page) == []


def test_all_ten_views_render_as_tables(page):
    login(page, "admin")
    page.goto(page.base + "/explorer")
    page.wait_for_selector("#view-list .view-item")
    for i in range(1, 11):
        page.click(f"#view-list [data-key='v{i}']")
        expect(page.locator("#view-title")).to_contain_text(f"View {i}:")
        page.wait_for_selector("#view-table table.data tbody tr")
        assert page.locator("#view-table tbody tr").count() > 0
        assert page.locator("#view-table thead th").count() >= 4


def test_explorer_search_filter_sort_and_exports(page, tmp_path):
    login(page, "admin")
    page.goto(page.base + "/explorer#v6")
    page.wait_for_selector("#view-table tbody tr")
    total = page.locator("#view-table tbody tr").count()
    page.select_option("#vf-travel_mode", "transit")
    # Wait until the re-queried table is rendered (not the transient loading state).
    page.wait_for_function(
        "n => { const m = [...document.querySelectorAll('#view-table tbody td .mode')].map(e => e.textContent.trim());"
        " return m.length > 0 && m.length < n && m.every(x => x === 'transit'); }", arg=total)
    modes = page.locator("#view-table tbody td .mode").all_inner_texts()
    assert modes and all(m.lower() == "transit" for m in modes)
    page.fill("#vf-q", "zzz-nothing")
    expect(page.locator("#view-table .empty")).to_be_visible()
    page.fill("#vf-q", "")
    page.click("#view-table th[data-key='total_route_score']")
    expect(page.locator("#view-table th[data-key='total_route_score'] .sort-ind")).to_be_visible()
    with page.expect_download() as d:
        page.click("#export-csv")
    csv_path = tmp_path / "v6.csv"
    d.value.save_as(csv_path)
    text = csv_path.read_text(encoding="utf-8-sig")
    assert text.startswith("route_id,trip_id,travel_mode") and "transit" in text and "driving" not in text
    with page.expect_download() as d:
        page.click("#export-pdf")
    pdf_path = tmp_path / "v6.pdf"
    d.value.save_as(pdf_path)
    assert pdf_path.read_bytes()[:5] == b"%PDF-"


def test_user_creates_edits_and_deletes_trip(page):
    login(page, "user")
    # client-side validation on empty submit
    page.click("#plan-form button[type=submit]")
    expect(page.locator('#plan-form [data-field="origin_location_id"] .error')).to_have_text("Origin is required.")
    page.select_option("#plan-form select[name=origin_location_id]", "3")
    page.select_option("#plan-form select[name=destination_location_id]", "3")
    page.click("#plan-form button[type=submit]")
    expect(page.locator('#plan-form [data-field="destination_location_id"] .error')).to_contain_text("different")
    # valid submit via fetch (no page reload)
    page.evaluate("window.__marker = 42")
    page.select_option("#plan-form select[name=destination_location_id]", "5")
    page.click("#plan-form button[type=submit]")
    expect(page.locator(".toast.success")).to_contain_text("created")
    assert page.evaluate("window.__marker") == 42
    page.wait_for_selector("#routes-table tbody tr")
    expect(page.locator("#routes-table tbody tr")).to_have_count(4)
    expect(page.locator("#routes-table .badge", has_text="Heuristic estimate").first).to_be_visible()
    # select the second-ranked route
    page.locator("#routes-table tbody tr").nth(1).locator("[data-act=select]").click()
    expect(page.locator(".toast.success").last).to_contain_text("Selected")
    expect(page.locator("#routes-table .badge", has_text="Selected")).to_have_count(1)
    # edit trip status
    page.click("#edit-trip-btn")
    page.select_option("dialog.modal select[name=trip_status]", "cancelled")
    page.click("dialog.modal button[type=submit]")
    expect(page.locator("#trip-h + p .badge").first).to_have_text("cancelled")
    # delete with confirmation dialog
    page.click("#del-trip-btn")
    page.click("dialog.modal [data-ok]")
    expect(page.locator(".toast.success").last).to_contain_text("Trip deleted")


def test_weather_fetch_saves_observation(page):
    login(page, "user")
    page.goto(page.base + "/planner#trip=2")
    page.wait_for_selector("#routes-table tbody tr")
    page.locator("#routes-table [data-act=weather]").first.click()
    expect(page.locator("#weather-result .weather-card")).to_contain_text("Slight rain")
    expect(page.locator("#weather-result")).to_contain_text("Saved 1 observation")
    expect(page.locator("#trip-obs tbody tr", has_text="Open-Meteo").first).to_be_visible()


def test_charts_render_from_database(page):
    login(page, "user")
    page.goto(page.base + "/conditions")
    page.wait_for_function("window.Chart && Object.keys(Chart.instances).length >= 5")
    n = page.evaluate("Object.keys(Chart.instances).length")
    assert n >= 5
    data = page.evaluate("Chart.getChart('chart-severity').data.datasets[0].data")
    assert sum(data) >= 12
    page.select_option("#of-type", "closure")
    expect(page.locator("#obs-table tbody tr")).to_have_count(1)


def test_admin_crud_via_management_page(page):
    login(page, "admin")
    page.goto(page.base + "/admin#locations")
    page.wait_for_selector("#mgr-table tbody tr")
    page.click("#mgr-add")
    dlg = page.locator("dialog.modal")
    dlg.locator("[name=location_name]").fill("E2E Test Plaza")
    dlg.locator("[name=street_address]").fill("1 Test Way")
    dlg.locator("[name=city]").fill("Ajax")
    dlg.locator("[name=location_type]").select_option("other")
    dlg.locator("[name=latitude]").fill("95")
    dlg.locator("[name=longitude]").fill("-79.02")
    dlg.locator("button[type=submit]").click()
    expect(dlg.locator('[data-field="latitude"] .error')).to_contain_text("at most 90")
    dlg.locator("[name=latitude]").fill("43.85")
    dlg.locator("button[type=submit]").click()
    expect(page.locator(".toast.success")).to_contain_text("created")
    row = page.locator("#mgr-table tbody tr", has_text="E2E Test Plaza")
    expect(row).to_have_count(1)
    row.locator("[data-act=edit]").click()
    page.locator("dialog.modal [name=city]").fill("Pickering")
    page.locator("dialog.modal button[type=submit]").click()
    expect(page.locator("#mgr-table tbody tr", has_text="Pickering")).to_have_count(1)
    page.locator("#mgr-table tbody tr", has_text="E2E Test Plaza").locator("[data-act=delete]").click()
    page.click("dialog.modal [data-ok]")
    expect(page.locator("#mgr-table tbody tr", has_text="E2E Test Plaza")).to_have_count(0)
    # server rejects deleting a referenced location; the UI shows the error
    page.locator("#mgr-table tbody tr", has_text="Ontario Tech North Campus").locator("[data-act=delete]").click()
    page.click("dialog.modal [data-ok]")
    expect(page.locator(".toast.error")).to_contain_text("still used")


def test_mobile_layout_has_no_horizontal_overflow(browser, live_server):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.base = live_server
    login(pg, "user")
    for path in ["/planner", "/explorer", "/conditions", "/places"]:
        pg.goto(live_server + path)
        pg.wait_for_load_state("networkidle")
        overflow = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"{path} overflows horizontally by {overflow}px"
    expect(pg.locator(".nav")).to_be_hidden()
    pg.click(".nav-toggle")
    expect(pg.locator(".nav")).to_be_visible()
    ctx.close()
