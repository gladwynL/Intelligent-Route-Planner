"""Capture evidence screenshots of the running application with Playwright.

Prerequisites: the app is running (python run.py) against a freshly
initialised database (python scripts/init_db.py), and Chromium is installed
(python -m playwright install chromium).

    python scripts/capture_screenshots.py [--base-url http://127.0.0.1:8000] [--out docs/screenshots]

The ten SQL-view screenshots are taken first, while the data still matches the
Phase II sample data; later steps create records and call the live weather API.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent

VIEW_FILES = {
    "v1": "view-01-trip-route-details.png",
    "v2": "view-02-all-mode-averages.png",
    "v3": "view-03-faster-than-trip-average.png",
    "v4": "view-04-users-and-feedback.png",
    "v5": "view-05-relevant-locations.png",
    "v6": "view-06-ranked-route-recommendations.png",
    "v7": "view-07-condition-risk-by-route.png",
    "v8": "view-08-favourite-saved-locations.png",
    "v9": "view-09-low-carbon-alternatives.png",
    "v10": "view-10-user-feedback-summary.png",
}

ACCOUNTS = {
    "admin": ("avery.morgan@example.com", "Admin#2026"),
    "user": ("jordan.rivera@example.com", "User#2026"),
    "guest": ("daniel.chen@example.com", "Guest#2026"),
}


def login(page: Page, base: str, role: str):
    page.goto(f"{base}/login")
    email, pw = ACCOUNTS[role]
    page.fill("#email", email)
    page.fill("#password", pw)
    page.click("#login-submit")
    page.wait_for_url("**/planner**")
    page.wait_for_load_state("networkidle")


def logout(page: Page):
    page.click("#logout-btn")
    page.wait_for_url("**/login**")


def shot(page: Page, out: Path, name: str, full_page: bool = True, locator=None):
    path = out / name
    if locator is not None:
        locator.screenshot(path=str(path))
    else:
        page.screenshot(path=str(path), full_page=full_page)
    print(f"  saved {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    args = ap.parse_args(argv)
    base = args.base_url.rstrip("/")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    exports = out / "exports"
    exports.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                  accept_downloads=True, locale="en-CA", timezone_id="America/Toronto")
        page = ctx.new_page()
        # Keep the sticky top bar from overlapping element screenshots.
        ctx.add_init_script("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');s.textContent='header.topbar{position:static!important}';document.head.appendChild(s);});")
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        # 1. Login page
        page.goto(f"{base}/login")
        page.wait_for_load_state("networkidle")
        shot(page, out, "01-login.png", full_page=False)

        # 2. Admin: all ten views in the Database Explorer
        login(page, base, "admin")
        page.goto(f"{base}/explorer")
        page.wait_for_selector("#view-list .view-item")
        for key, fname in VIEW_FILES.items():
            page.click(f"#view-list [data-key='{key}']")
            page.wait_for_function(
                "k => document.querySelector('#view-title').textContent.startsWith('View ' + k + ':')"
                " && document.querySelector('#view-table table.data, #view-table .empty')", arg=key[1:])
            page.wait_for_load_state("networkidle")
            page.evaluate("document.getElementById('sql-box').open = true")
            shot(page, out, fname, locator=page.locator("#view-panel"))

        # 3. Search / filter on a view (View 6 filtered to driving routes)
        page.click("#view-list [data-key='v6']")
        page.wait_for_function("document.querySelector('#view-title').textContent.startsWith('View 6:')")
        page.wait_for_selector("#view-table table.data")
        page.select_option("#vf-travel_mode", "driving")
        page.wait_for_timeout(700)
        page.wait_for_load_state("networkidle")
        shot(page, out, "08-search-filter-explorer.png", full_page=False)

        # 4. Export controls + real export files
        with page.expect_download() as dl:
            page.click("#export-csv")
        dl.value.save_as(str(exports / "v6-driving-routes.csv"))
        with page.expect_download() as dl:
            page.click("#export-pdf")
        dl.value.save_as(str(exports / "v6-driving-routes.pdf"))
        page.locator("#export-csv").hover()
        shot(page, out, "10-export-controls.png", locator=page.locator("#view-panel .card-header"))
        print("  saved exports/v6-driving-routes.csv and .pdf")

        # 5. Admin planner (admin interface) + route comparison
        page.goto(f"{base}/planner#trip=4")
        page.wait_for_selector("#routes-table table.data")
        page.wait_for_timeout(800)
        shot(page, out, "02-admin-planner.png")
        shot(page, out, "05-route-comparison.png", locator=page.locator("#cmp-h").locator("xpath=ancestor::section"))
        shot(page, out, "05b-ranking-explanation.png", locator=page.locator("#why-h").locator("xpath=ancestor::section"))

        # 6. Admin management page with a modal form open
        page.goto(f"{base}/admin#users")
        page.wait_for_selector("#mgr-table table.data")
        shot(page, out, "11-admin-management.png", full_page=False)
        page.goto(f"{base}/admin#routes")
        page.wait_for_selector("#mgr-table table.data")
        page.click("#mgr-add")
        page.wait_for_selector("dialog.modal[open]")
        page.wait_for_timeout(300)
        shot(page, out, "11b-admin-create-form.png", full_page=False)
        page.keyboard.press("Escape")
        logout(page)

        # 7. Normal user: planner, CRUD (create trip with generated alternatives), weather
        login(page, base, "user")
        page.wait_for_timeout(800)
        shot(page, out, "03-user-planner.png")
        page.select_option("select[name=origin_location_id]", "2")
        page.select_option("select[name=destination_location_id]", "7")
        page.click("#plan-form button[type=submit]")
        page.wait_for_selector(".toast.success")
        page.wait_for_selector("#routes-table table.data")
        page.wait_for_timeout(900)
        shot(page, out, "06-crud-create-trip.png", full_page=False)
        # Client-side validation demo: submit the empty form
        page.click("#plan-form button[type=submit]")
        page.wait_for_timeout(300)
        shot(page, out, "06b-form-validation.png", locator=page.locator("#plan-title").locator("xpath=ancestor::section"))

        # Live weather on the first route of the new trip (real Open-Meteo call)
        page.locator("#routes-table [data-act=weather]").first.click()
        page.wait_for_selector("#weather-result .weather-card, #weather-result .form-alert", timeout=30000)
        page.wait_for_timeout(600)
        shot(page, out, "07-weather-integration-planner.png",
             locator=page.locator("#wx-h").locator("xpath=ancestor::section"))

        # Conditions & analytics page (charts) + live fetch panel
        page.goto(f"{base}/conditions")
        page.wait_for_selector("#chart-severity")
        page.wait_for_timeout(1500)
        shot(page, out, "09-analytics-charts.png")
        page.select_option("#of-type", "weather")
        page.wait_for_timeout(800)
        shot(page, out, "08b-search-filter-observations.png",
             locator=page.locator("#obs-h").locator("xpath=ancestor::section"))

        # Places + profile
        page.goto(f"{base}/places")
        page.wait_for_selector("#loc-table table.data")
        page.locator("#loc-table [data-act=weather]").first.click()
        page.wait_for_selector("#loc-weather .weather-card, #loc-weather .form-alert", timeout=30000)
        shot(page, out, "12-places-weather.png", full_page=False)
        page.goto(f"{base}/profile")
        page.wait_for_selector("#fb-table table.data, #fb-table .empty")
        shot(page, out, "13-profile.png", full_page=False)

        # Mobile layout
        mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                     is_mobile=True, has_touch=True)
        mpage = mobile.new_page()
        login(mpage, base, "user")
        mpage.wait_for_timeout(800)
        shot(mpage, out, "14-mobile-planner.png", full_page=False)
        mobile.close()
        logout(page)

        # 8. Guest interface
        login(page, base, "guest")
        page.goto(f"{base}/explorer")
        page.wait_for_selector("#view-table table.data")
        shot(page, out, "04-guest-explorer.png", full_page=False)

        browser.close()
        if errors:
            print("Console errors observed:")
            for e in errors:
                print("   ", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
