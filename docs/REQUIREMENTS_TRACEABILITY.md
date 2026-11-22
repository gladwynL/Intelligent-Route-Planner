# Requirements Traceability: Phase III

This maps every requirement in the official *Data Management Projects Information Sheet (F26), Phase III*,
and the matching TA checklist (*Project Review – What We Expect*), to its implementation, how it was
verified, and the evidence. A requirement is marked **PASS** only when an automated test or a captured
screenshot of the running application supports it.

Abbreviations: **DB** = `tests/test_database.py`, **AUTH** = `tests/test_auth.py`, **CRUD** = `tests/test_api_crud.py`,
**VX** = `tests/test_views_exports.py`, **WX** = `tests/test_weather.py`, **E2E** = `tests/e2e/test_browser.py`,
**SS** = `docs/screenshots/`.

## A. Database (Phase II carried forward; TA step 1)

| Requirement | Implementation | Verification | Evidence | Status |
|---|---|---|---|---|
| Relational schema with actual CREATE TABLE commands (9 relations) | `database/schema.sql` | DB `test_table_exists_with_at_least_six_rows` (×9) | `docs/TEST_RESULTS.md` §4 | PASS |
| ≥ 6 tuples per relation | `database/seed.sql` (6–12 rows per table) | DB tests; `scripts/init_db.py` verification | TEST_RESULTS §4 | PASS |
| 10 views run without errors and return rows | `database/views.sql` | DB `test_view_executes_and_returns_expected_rows` (×10); VX `test_each_view_returns_rows_for_admin` (×10) | TEST_RESULTS §4; SS `view-01…view-10` | PASS |
| View 1: join of ≥ 3 tables | `v1_trip_route_details` (5 tables) | DB `test_v1_joins_at_least_three_tables` | SS `view-01-trip-route-details.png` | PASS |
| View 2: nested ANY/ALL + GROUP BY | `v2_faster_than_all_mode_averages` | DB pattern test + `test_v2_all_operator_semantics` | SS `view-02-all-mode-averages.png` | PASS |
| View 3: correlated nested query | `v3_faster_than_trip_average` | DB pattern test + `test_v3_correlated_semantics` | SS `view-03-…png` | PASS |
| View 4: FULL JOIN | `v4_users_and_feedback` | DB pattern test + `test_v4_full_join_keeps_users_without_feedback` | SS `view-04-…png` | PASS |
| View 5: nested set operation (UNION) | `v5_relevant_locations` | DB pattern test + `test_v5_union_matches_saved_or_destination` | SS `view-05-…png` | PASS |
| Views 6–10 (team-defined) | `v6`–`v10` | DB row-count tests; `test_v6_scores_match_phase_ii_weighting` | SS `view-06…view-10` | PASS |
| Integrity constraints (PK, FK, UNIQUE, CHECK, cascade) | `schema.sql` | DB constraint tests (13) | TEST_RESULTS §3 | PASS |
| Run on real PostgreSQL (Phase II used SQLite substitutions) | Docker PostgreSQL 16.15 | Entire DB suite runs on PostgreSQL | TEST_RESULTS §1, §4 | PASS |

## B. Backend operations and functions

| Requirement | Implementation | Verification | Evidence | Status |
|---|---|---|---|---|
| 1. Secure login/logout using session management | `backend/app/auth.py` (`/api/auth/login`, `/logout`, session cookie, scrypt, `session.clear()` on login) | AUTH `test_login_success…`, `test_login_invalid_credentials`, `test_logout_clears_session`, `test_session_cookie_flags`; E2E `test_login_validation_and_failure`, `test_anonymous_guest_and_logout` | SS `01-login.png` | PASS |
| 1. Roles admin / user / guest with restricted functionality | `roles_required`, `ensure_owner`, `page_login_required`; role-aware `base.html` navigation | AUTH `test_admin_only_endpoints_forbidden_for_user` (11), `test_guest_cannot_mutate` (7×2), `test_navigation_differs_by_role`, `test_admin_page_access_by_role`; E2E `test_role_dependent_interface` (×3) | SS `02-admin-planner.png`, `03-user-planner.png`, `04-guest-explorer.png` | PASS |
| 2. Input validation (email format, required fields, data types) | `backend/app/validation.py`, used by every endpoint; database CHECKs as a final safeguard | AUTH `test_login_validation_errors`; CRUD `test_location_validation`, `test_trip_validation`, `test_route_validation`, `test_admin_user_crud_and_email_validation` | SS `06b-form-validation.png` | PASS |
| 3. REST/JSON API with GET, POST, PUT, DELETE | `backend/app/api/*.py`; `docs/API.md` | CRUD suite (all four methods on every resource) | `docs/API.md` | PASS |
| 3. External API integration that saves results in the database | `services/weather.py`, `api/weather.py` (`POST /api/weather/routes/<id>`) | WX `test_route_weather_fetches_parses_and_persists` (mocked), `test_live_open_meteo` (live); live row #13 recorded | TEST_RESULTS §5; SS `07-weather-integration-planner.png`, `12-places-weather.png` | PASS |
| 3. A web service that you implement (REST/JSON) | Flask `/api/*` blueprints | CRUD/VX suites | `docs/API.md` | PASS |
| 3. A web service that generates JSON | All `/api/*` endpoints return JSON | All API tests parse JSON | `docs/API.md` | PASS |
| 3. A web service that interacts with a database | e.g. `/api/views/<key>`, `/api/trips`, `/api/weather/routes/<id>` | VX, CRUD, WX suites | TEST_RESULTS §3 | PASS |
| 3. (REST/JSON option) A web page that uses an external REST/JSON API | Planner, Conditions and Places pages call the backend, which calls Open-Meteo | E2E `test_weather_fetch_saves_observation`; live screenshot run | SS `07-…`, `12-places-weather.png` | PASS |
| 3. (REST/JSON option) At least two queries for that functionality | Query 1 `SELECT` segment coordinates; Query 2 `INSERT condition_observation`; Query 3 `SELECT` stored observations (+ View 6 ranking) | WX persistence test checks all three; `docs/diagrams/weather-sequence.png` | diagram; TEST_RESULTS §5 | PASS |
| 4. Full CRUD for the data entities | Endpoints for all 9 relations; Admin page CRUD for all 9 | CRUD suite; E2E `test_user_creates_edits_and_deletes_trip`, `test_admin_crud_via_management_page` | SS `06-crud-create-trip.png`, `11-admin-management.png`, `11b-admin-create-form.png` | PASS |
| 5. Data export to CSV and PDF | `services/exporter.py`; `/api/views/<key>/export`, `/api/export/trips`, `/api/export/observations` | VX export tests (7); E2E download test | SS `10-export-controls.png`; `docs/screenshots/exports/*.csv, *.pdf` | PASS |
| 6. Error handling: database connection failures, wrong API inputs, exceptions | `backend/app/errors.py` (SQLSTATE mapping, 502, 503, JSON 404/405) | WX `test_database_unavailable_returns_503`, `test_external_api_failures_return_502…` (×4); CRUD `test_malformed_json_body`, `test_errors_do_not_leak_internals` | TEST_RESULTS §3 | PASS |

## C. Frontend operations

| Requirement | Implementation | Verification | Evidence | Status |
|---|---|---|---|---|
| Two or more web pages | 7 pages: login, planner, places, explorer, conditions, profile, admin | E2E `test_navigate_all_pages_without_errors` | SS `01`–`14` | PASS |
| Pages run the 10 views and show the results as HTML tables | `frontend/templates/explorer.html`, `static/js/explorer.js` | E2E `test_all_ten_views_render_as_tables` | SS `view-01` … `view-10` | PASS |
| 1. Dynamic forms with JavaScript (validation, auto-fill) | `ui.js` (`bindForm`, `validateValues`, `formModal`); demo-account auto-fill on login | E2E client-validation steps in the trip, admin and login tests | SS `06b-form-validation.png`, `11b-admin-create-form.png` | PASS |
| 2. AJAX / Fetch without page refresh | `static/js/api.js`; every page loads and submits through `fetch` | E2E checks that a JS marker survives a form submit (no reload) | SS `06-crud-create-trip.png` | PASS |
| 3. Data visualisation (Chart.js / D3) from database queries | `conditions.js` (5 charts from `/api/analytics/summary`), `planner.js` (score-breakdown chart from View 6) | E2E `test_charts_render_from_database` (≥ 5 Chart instances with DB data) | SS `09-analytics-charts.png`, `05b-ranking-explanation.png` | PASS |
| 4. Search and filter (date, category, keyword, id) using backend queries | Trips: keyword/status/mode/id/date range; Views: keyword plus column filters and sort; Observations: type/severity/source/trip/date; Locations; Admin tabs | CRUD `test_trip_filters`, `test_location_search_filter`, `test_observation_filters`; VX `test_view_filters_keyword_and_sort`; E2E explorer test | SS `08-search-filter-explorer.png`, `08b-search-filter-observations.png` | PASS |

## D. Documentation and other deliverables

| Requirement | Implementation | Verification | Evidence | Status |
|---|---|---|---|---|
| Detailed README on installing and running (Windows or Linux) | `README.md`, `scripts/setup.ps1`, `run.ps1`, `test.ps1`, `.env.example`, `docker-compose.yml` | Setup followed in a fresh clone of the repository (see TEST_RESULTS §8) | `README.md` | PASS |
| Design diagrams / schematics (for the report) | `docs/diagrams/*.mmd` → PNG/SVG (architecture, weather sequence, relational schema); Phase II ER diagram kept | Rendered from source by `scripts/render_diagrams.py` | `docs/diagrams/` | PASS |
| Snapshots of the results of every query (for the report) | 10 view screenshots plus feature screenshots | Captured from the running app by `scripts/capture_screenshots.py` | `docs/screenshots/` | PASS |
| Bugs found and fixed (evaluation factor) | Defect log | — | TEST_RESULTS §6 | PASS |
| Final report (10–12 pages), slides, contribution matrix | **Out of scope for this implementation task**; the team will write them separately | — | `docs/IMPLEMENTATION_SUMMARY.md` provides the facts | NOT VERIFIED (separate deliverable) |

## E. TA checklist ("Done when…")

| TA step | Done-when criterion | Status |
|---|---|---|
| 1 Fix your database | All 10 views run without errors and return rows | PASS |
| 2 Login and roles | Admin and normal user see different pages | PASS (SS `02` vs `03`; AUTH/E2E role tests) |
| 3 Backend API | Each endpoint can be called and changes the database | PASS (CRUD suite) |
| 4 Web pages | A user can do everything from the browser without the page reloading | PASS (E2E) |
| 5 Export, test, README | A classmate can install and run it from the README alone | PASS (fresh-clone setup, TEST_RESULTS §8) |
| 6–7 Report, slides, presentation | — | Not part of this task |
