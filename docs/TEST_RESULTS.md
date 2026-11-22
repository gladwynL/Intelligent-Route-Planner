# Test Results

Results recorded on **2026-11-21** from the finished Phase III implementation. Everything below was produced
by running the commands shown against the actual PostgreSQL database. Nothing is simulated.

## 1. Environment

| Item | Value |
|---|---|
| OS | Windows 11 Pro (10.0.26200) |
| Python | 3.12.10 (virtual environment `.venv`) |
| PostgreSQL | **16.15** (`postgres:16-alpine` via Docker Compose, `localhost:5433`) |
| Key packages | Flask 3.1.3, Flask-WTF 1.3.0, SQLAlchemy 2.1.9, psycopg 3.3.9, ReportLab 5.1.0, requests 2.34.2 |
| Test tools | pytest 9.2.0, Playwright 1.65.2 (headless Chromium), pytest-playwright 0.10.0 |
| Application DB | `route_planner` |
| Test DB | `route_planner_test`, a separate database re-created from `database/*.sql` before every test module |

## 2. Commands

```powershell
python scripts\init_db.py                 # create/seed the application database and verify it
python -m pytest                          # full suite (database, API, integration, browser)
python -m pytest -m "not e2e"             # without the browser tests
python scripts\capture_screenshots.py     # evidence screenshots against the running app
```

## 3. Automated test summary

Final full run: `python -m pytest` → **185 passed, 0 failed, 0 skipped, 0 errors in 61.3 s**.

| Suite | File | Tests | Result |
|---|---|---|---|
| Database (direct PostgreSQL) | `tests/test_database.py` | 48 | 48 passed |
| Authentication & authorisation | `tests/test_auth.py` | 36 | 36 passed |
| CRUD, validation, ownership, filters | `tests/test_api_crud.py` | 40 | 40 passed |
| SQL views, scoping, exports, analytics | `tests/test_views_exports.py` | 25 | 25 passed |
| External API, routing, failure handling | `tests/test_weather.py` | 23 | 23 passed (incl. one **live** Open-Meteo call) |
| Browser end-to-end (Playwright/Chromium) | `tests/e2e/test_browser.py` | 13 | 13 passed (run 3 more times on their own: 13/13 each time) |
| **Total** | | **185** | **185 passed** |

### What the tests verify (highlights)

* **Schema:** all 9 tables exist, each with at least 6 rows; PostgreSQL ≥ 14.
* **Views:** all 10 views exist, run, and return exactly the Phase II row counts (12, 4, 6, 8, 8, 12, 12, 4, 7, 6).
* **Required SQL patterns:** checked in `pg_get_viewdef` (JOIN, `ALL (`, `GROUP BY`, correlated predicate, `FULL JOIN`, `UNION`, `dense_rank()`); View 1 depends on ≥ 3 tables in `pg_depend`.
* **Semantics:** the ALL view returns only routes faster than the smallest mode average; the correlated view never returns a route at or above its trip average; the FULL JOIN keeps the 2 users who have no feedback; the UNION view matches the set computed independently.
* **Recommendation algorithm:** every View 6 component score, total and rank-1 flag is recomputed in Python with `Decimal` and matches exactly. Known Phase II totals (94.00, 76.20, 83.00, 69.17) are confirmed.
* **Constraints:** UNIQUE email, role CHECK, FK to location, origin ≠ destination, rating 1–5, severity 0–5, toll ≥ 0, latitude range, UNIQUE (trip, option), UNIQUE (user, location), the one-selected-route partial unique index, RESTRICT on a referenced location, ON DELETE CASCADE from a trip.
* **Auth:** valid and invalid login, validation, CSRF required (login and mutations), logout, HttpOnly/SameSite cookie, 401 for anonymous API calls, redirect for anonymous pages, 403 for the admin page as user or guest, different navigation per role, guests blocked from every mutation, role changes applied immediately, admin cannot demote or delete themselves.
* **CRUD:** create, read, update and delete for locations, trips, route options, segments, observations, users, preferences, saved locations and feedback, with duplicates (409), invalid foreign keys (400), invalid emails, missing fields and out-of-range values (400 with per-field details).
* **Isolation:** 13 crafted requests against another user's trip, route, saved place, feedback or weather return 404; a supplied `user_id` is ignored for non-admins.
* **Views API:** guests see 6 views and get 403 on the other 4; a user's personal views are limited to their own rows; filters, keyword search and sort work; SQL-injection strings have no effect.
* **Exports:** CSV header and rows, quoting and special characters, formula-injection protection, valid `%PDF-…%%EOF` files, empty results, format validation.
* **External API:** JSON parsing, coordinates sent from Query 1, persistence (Query 2) and read-back (Query 3); timeouts, HTTP 500, malformed JSON and missing fields all give 502 and store nothing; display-only lookup stores nothing.
* **Error handling:** unreachable database gives 503 on `/api/health` and on login, with no credentials leaked; malformed JSON gives 400; unknown route gives a JSON 404; wrong method gives a JSON 405.
* **Browser:** each role's interface, all six pages load without console errors, all 10 views render as tables, filter/sort/CSV/PDF downloads, trip create/edit/select/delete through the forms with client-side validation and no page reload, weather saving, at least 5 Chart.js charts drawn from database data, admin CRUD including the server's rejection of deleting a referenced location, no horizontal overflow at 390 px and a working mobile menu.

## 4. Schema verification (`python scripts\init_db.py`)

```
PostgreSQL server version: 16.15

Table row counts:
  app_user                    6
  location                    8
  user_preference             6
  trip                        6
  route_option               12
  route_segment              12
  condition_observation      12
  saved_location              6
  feedback                    6

View row counts:
  v1_trip_route_details                  12
  v2_faster_than_all_mode_averages        4
  v3_faster_than_trip_average             6
  v4_users_and_feedback                   8
  v5_relevant_locations                   8
  v6_ranked_route_recommendations        12
  v7_condition_risk_by_route             12
  v8_favourite_saved_locations            4
  v9_low_carbon_alternatives              7
  v10_user_feedback_summary               6

Verification: PASS (9 tables >= 6 rows, 10 views non-empty)
```

These counts are identical to the SQLite-based appendix of the Phase II report. Phase III confirms them on
real PostgreSQL. View 6 output on PostgreSQL:

| route | trip | mode | time | dist. | safety | toll | pref. | total | rank |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | driving | 100.00 | 100.00 | 60 | 100 | 100 | 94.00 | 1 |
| 2 | 1 | transit | 62.86 | 93.65 | 80 | 100 | 50 | 76.20 | 2 |
| 3 | 2 | driving | 100.00 | 100.00 | 40 | 100 | 50 | 88.50 | 1 |
| 4 | 2 | transit | 71.43 | 94.44 | 80 | 100 | 100 | 82.75 | 2 |
| 6 | 3 | driving | 100.00 | 91.36 | 60 | 100 | 50 | 89.34 | 1 |
| 5 | 3 | cycling | 66.67 | 100.00 | 100 | 100 | 100 | 85.00 | 2 |
| 7 | 4 | driving | 100.00 | 100.00 | 20 | 50 | 100 | 83.00 | 1 |
| 8 | 4 | transit | 73.81 | 95.03 | 60 | 100 | 50 | 78.47 | 2 |
| 10 | 5 | cycling | 100.00 | 91.18 | 60 | 100 | 50 | 89.30 | 1 |
| 9 | 5 | walking | 38.16 | 100.00 | 80 | 100 | 100 | 69.17 | 2 |
| 12 | 6 | driving | 100.00 | 100.00 | 40 | 100 | 50 | 88.50 | 1 |
| 11 | 6 | transit | 68.42 | 92.86 | 80 | 100 | 100 | 81.00 | 2 |

## 5. Live external-service verification

During the screenshot run (`scripts/capture_screenshots.py`, 2026-11-21 ≈21:15 local time), the user
*Jordan Rivera* created trip 7 (Oshawa Centre → Lakeview Park) through the web form, then pressed
**Weather** on the driving route. Both external services were really called. The resulting rows in PostgreSQL:

```
 route_id | trip_id | travel_mode | distance_km | estimated_duration_min | road_name
       13 |       7 | driving     |        7.17 |                     12 | OSRM driving route (public demo server)
       14 |       7 | cycling     |        6.76 |                     29 | Heuristic estimate (straight-line x detour factor)
       15 |       7 | walking     |        6.49 |                     81 | Heuristic estimate (straight-line x detour factor)
       16 |       7 | transit     |        7.58 |                     29 | Heuristic estimate (straight-line x detour factor)

 observation_id | segment_id | observed_at         | severity | description                                           | source_name
             13 |         13 | 2026-11-21 21:15:00 |        0 | Clear sky, 4.2 C, wind 4 km/h (app risk estimate 0/5) | Open-Meteo
```

The automated live test `tests/test_weather.py::test_live_open_meteo` also passed in the final run. The other
Open-Meteo tests use mocked HTTP responses so that they always give the same result. They are labelled as
mocks in the file.

## 6. Defects found and corrections applied

| # | Found by | Defect | Correction |
|---|---|---|---|
| 1 | PostgreSQL verification of Phase II SQL | The Phase II inserts use explicit IDs, which do not advance `GENERATED BY DEFAULT AS IDENTITY` sequences, so the first row added by the app would fail with a duplicate-key error. | `seed.sql` calls `setval(pg_get_serial_sequence(...), MAX(id))` for all nine tables (`test_identity_sequences_advanced_after_seed`). |
| 2 | Phase II review | The Phase II password values were placeholders (`demo_hash_01`), so nobody could log in. | Replaced with real Werkzeug scrypt hashes of documented demo passwords. |
| 3 | Privacy review | The Phase II sample users were real student names and emails. | Replaced with fictional identities at `example.com`. All IDs and relationships are unchanged, so every view returns the same rows. |
| 4 | API test `test_trip_full_crud_with_generated_routes` | "Generate alternatives" on a trip that already had all four modes re-added all four, because an empty mode list was treated as "all modes". | `routing.estimate_alternatives` now treats only `None` as "all modes". |
| 5 | Visual review of captured screenshots | Explorer list text ran together (inline spans); the mobile planner card overflowed the screen (grid track min-content); the route-comparison table was wider than its card. | Block display for the list labels, `minmax(0,1fr)` grid tracks with `min-width:0`, and a compact table style with a truncated "via" column. |
| 6 | Visual review | Changing only the URL hash (e.g. `/explorer#v6`) did not switch the selected view, trip or admin tab. | Added `hashchange` handlers on the Explorer, Planner and Admin pages. |
| 7 | Visual review | The Leaflet map sometimes zoomed in too far when the card was still laying out. | `invalidateSize()` after layout and `maxZoom` on `fitBounds`. |
| 8 | Full-suite run (browser test) | A race in `test_explorer_search_filter_sort_and_exports`: the assertion could run while the table showed its loading state. This was a problem in the test, not the app. | The test now waits until the filtered rows are rendered; it then passed in 3 separate runs plus the final full run. |
| 9 | Git warning | An exported PDF was treated as text, so line-ending conversion could corrupt it on checkout. | Added `.gitattributes` marking PDF and PNG files as binary. |

**No change was made to any Phase II CREATE TABLE structure or view body.** The only additions are five
non-unique foreign-key indexes (for performance only) and the sequence reset.

## 7. Known limitations

* Seeded route alternatives are demonstration data, and generated alternatives are estimates: OSRM covers
  driving only, and the other modes use a labelled straight-line heuristic. This is not live navigation and
  there is no real transit timetable.
* View 6's safety score uses the **highest severity ever recorded** on a route (the Phase II design), so an
  old severe observation keeps lowering the score until it is deleted. Time-weighting observations is
  possible future work.
* Weather severity is a risk estimate defined by the application, not an official road-safety rating.
* Chart.js, Leaflet, the map tiles, Open-Meteo and OSRM need internet access. Without it the database
  features still work, and the app shows a clear message for the missing parts.
* The Flask development server is used for the local demonstration; a production deployment would use a
  WSGI server behind HTTPS.
