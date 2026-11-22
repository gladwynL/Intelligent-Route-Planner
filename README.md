# Intelligent Route Planning System

A database-backed web application for planning trips, comparing driving, transit, cycling and walking
alternatives, and getting a **transparent, database-computed route recommendation** that weighs travel time,
distance, road/weather conditions, tolls and personal preferences.

Built for **SOFE 3700U – Data Management Systems (Fall 2026), Phase III**, by Group 16. The PostgreSQL
schema, sample data, ten SQL views and the weighted recommendation algorithm come from the team's Phase II
design. Phase III adds a Flask REST/JSON API, a multi-page JavaScript front end, live Open-Meteo weather
integration, CSV/PDF export and an automated test suite.

![Route planner](docs/screenshots/02-admin-planner.png)

---

## Contents

1. [Features](#features)
2. [Technology stack](#technology-stack)
3. [Architecture](#architecture)
4. [Quick start (Windows)](#quick-start-windows)
5. [Manual setup](#manual-setup)
6. [Demo accounts](#demo-accounts)
7. [Using the application](#using-the-application)
8. [The ten SQL views](#the-ten-sql-views)
9. [Route recommendation algorithm](#route-recommendation-algorithm)
10. [External API integration (Open-Meteo)](#external-api-integration-open-meteo)
11. [REST API overview](#rest-api-overview)
12. [Running the tests](#running-the-tests)
13. [Project structure](#project-structure)
14. [Security and configuration notes](#security-and-configuration-notes)
15. [Troubleshooting](#troubleshooting)
16. [Documentation index](#documentation-index)

---

## Features

| Area | What is implemented |
|---|---|
| **Database** | PostgreSQL 16: 9 normalized relations with primary/foreign keys, CHECK, UNIQUE and partial-unique constraints, cascading deletes; seed data (6–12 rows per table); the 10 Phase II views. |
| **Authentication** | Session login and logout, Werkzeug scrypt password hashes, session-fixation protection, HttpOnly/SameSite cookies, CSRF tokens on every state-changing request. |
| **Roles** | **admin** (full management of all 9 tables and all 10 views), **user** (own trips, routes, preferences, saved places and feedback; personal views limited to their own rows), **guest** (read-only; 6 views with no personal data). Enforced on the server, not only hidden in the UI. |
| **REST/JSON API** | `GET`, `POST`, `PUT`, `DELETE` endpoints for every relation, plus search/filter, views, exports, analytics, weather and health. Validation errors come back per field. |
| **Route planning** | Create trips from stored locations, generate estimated alternatives (OSRM for driving when reachable, otherwise a clearly labelled heuristic), add routes by hand, select a preferred route, and see why one route ranks above another. |
| **External API** | Open-Meteo current weather: the app queries PostgreSQL for segment coordinates, calls the API, parses the JSON, stores `condition_observation` rows, then queries them back. Rankings update immediately. |
| **Database Explorer** | All 10 views shown as sortable HTML tables, with keyword and column filters run on the server, the SQL definition (`pg_get_viewdef`) and CSV/PDF export. |
| **Analytics** | Six Chart.js charts built from SQL aggregates: severity distribution, average time by mode, scores by trip, condition types, rating distribution, and the weighted-score breakdown per route. |
| **Exports** | CSV (UTF-8 with BOM, protected against spreadsheet formula injection) and PDF (ReportLab tables) for every view, trips and observations, always using the current filters. |
| **Error handling** | PostgreSQL error codes mapped to friendly HTTP 400/404/409 messages, 502 when the external API fails, 503 when the database is down. Responses never include tracebacks, hashes or connection strings. |
| **UI/UX** | Responsive layout from desktop down to a 390 px phone, accessible labels, loading and empty states, toasts, confirmation dialogs, JavaScript form validation with server errors mapped back to fields, and a Leaflet/OpenStreetMap map. |

## Technology stack

| Layer | Technology |
|---|---|
| Database | PostgreSQL 16 (Docker `postgres:16-alpine`, or any local PostgreSQL 14+) |
| Backend | Python 3.12, Flask 3.1, SQLAlchemy 2 Core, psycopg 3, Flask-WTF (CSRF), Werkzeug security |
| Frontend | HTML5, CSS3, modern vanilla JavaScript (ES modules, Fetch API), Chart.js 4, Leaflet 1.9 |
| External services | Open-Meteo REST/JSON weather API; OSRM public demo server (optional driving estimates) |
| Exports | Python `csv`, ReportLab (PDF) |
| Testing | pytest, Playwright (Chromium) |

There is no build step and no Node.js requirement. Chart.js, Leaflet and the map tiles load from public CDNs.

## Architecture

![Architecture](docs/diagrams/architecture.png)

The browser loads HTML page shells from Flask, which checks the user's role before rendering. Each page then
uses the Fetch API to call the `/api/*` REST endpoints, which return JSON. Every endpoint validates its input,
checks role and record ownership, and runs parameterised SQL through SQLAlchemy Core. The recommendation
scoring lives in exactly one place: PostgreSQL **View 6**. More diagrams are in [`docs/diagrams/`](docs/diagrams)
(Mermaid source plus PNG/SVG): [weather data flow](docs/diagrams/weather-sequence.png) and
[relational schema](docs/diagrams/relational-schema.png).

---

## Quick start (Windows)

**Prerequisites**

* **Python 3.10+** (tested with 3.12): <https://www.python.org/downloads/> (tick "Add python.exe to PATH")
* **PostgreSQL**, using *either*
  * **Docker Desktop** (recommended; the database runs in a container on port **5433**), *or*
  * a local **PostgreSQL 14+** install (<https://www.postgresql.org/download/windows/>)
* **Git**, to clone the repository
* An internet connection, for the weather API, map tiles and chart library

Open **PowerShell** in the project folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run.ps1
```

Then open **<http://127.0.0.1:8000>** and sign in with a [demo account](#demo-accounts).

`setup.ps1` creates `.venv`, installs the dependencies, creates `.env` with a random `SECRET_KEY`, starts
PostgreSQL with Docker Compose, and creates and seeds the database. If you use your own PostgreSQL instead,
add `-SkipDocker` (see below). To also install the test tools and Chromium, add `-Dev`.

## Manual setup

The same steps as the script, one at a time (PowerShell, from the project root):

**1. Create a virtual environment and install dependencies**

```powershell
python -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

```powershell
pip install -r requirements.txt
```

For running the tests, use `pip install -r requirements-dev.txt` and then `python -m playwright install chromium`.

**2. Configure environment variables**

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `SECRET_KEY` to a long random value. You can generate one with:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs session cookies and CSRF tokens | *(must be set)* |
| `DATABASE_URL` | Application database | `postgresql+psycopg://route_planner:route_planner_dev@localhost:5433/route_planner` |
| `TEST_DATABASE_URL` | Separate database used by the tests | `…/route_planner_test` |
| `APP_HOST` / `APP_PORT` | Where Flask listens | `127.0.0.1` / `8000` |
| `SESSION_COOKIE_SECURE` | Set to `1` when served over HTTPS | `0` |
| `OPEN_METEO_URL` | Weather API endpoint | `https://api.open-meteo.com/v1/forecast` |
| `ENABLE_OSRM` / `OSRM_URL` | Optional OSRM driving estimates | `1` / public demo server |
| `EXTERNAL_TIMEOUT_SECONDS` | Timeout for external HTTP calls | `8` |
| `DB_TIMEZONE` | Session time zone for timestamps | `America/Toronto` |

**3. Start PostgreSQL**

* **Docker:** run `docker compose up -d`. This starts `postgres:16-alpine` on `localhost:5433` with the
  development credentials from `.env`; the data lives in a named Docker volume.
* **Local PostgreSQL:** create a login role (or reuse `postgres`) and point `DATABASE_URL` and
  `TEST_DATABASE_URL` at it, for example
  `postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/route_planner`. The init script creates the
  database itself if the role is allowed to (`CREATEDB`); otherwise create an empty database first in pgAdmin.

**4. Create the schema, seed data and views**

```powershell
python scripts\init_db.py
```

This runs `database/schema.sql`, `seed.sql` and `views.sql`, then prints the row counts of every table and
view. Re-running it resets the project's tables to the demo data. It only ever drops this project's 9 tables
and 10 views, never a database. `python scripts\init_db.py --verify-only` prints the counts without changing
anything.

**5. Start the application**

```powershell
python run.py
```

Then open <http://127.0.0.1:8000>.

## Demo accounts

All accounts are **fictional demonstration identities** (see also [`docs/DEMO_CREDENTIALS.md`](docs/DEMO_CREDENTIALS.md)):

| Role | Email | Password | Notes |
|---|---|---|---|
| admin | `avery.morgan@example.com` | `Admin#2026` | Full management, all 10 views, every trip |
| user | `jordan.rivera@example.com` | `User#2026` | Owns trip 2 (Oshawa Centre → Ontario Tech) |
| user | `taylor.brooks@example.com` | `User#2026` | Owns trip 3 |
| user | `casey.nguyen@example.com` | `User#2026` | Owns trip 4 (includes a $2.50 toll route) |
| user | `aisha.khan@example.com` | `User#2026` | Owns trip 5 |
| guest | `daniel.chen@example.com` | `Guest#2026` | Read-only account |
| guest | *Continue as guest* button | — | Anonymous read-only session |

The login page also has one-click buttons that fill in the admin, user and guest credentials. These passwords
exist only for the local demo. Change or remove the accounts before deploying anywhere.

## Using the application

| Page | URL | Roles | What you can do |
|---|---|---|---|
| Login | `/login` | everyone | Sign in, continue as a guest, fill in a demo account |
| Route Planner | `/planner` | all (guests read-only) | Create, edit and delete trips; generate or add routes; select a route; compare scores; see why one route ranks higher; fetch live weather; rate a trip |
| Places | `/places` | all | Search locations; add locations (user/admin); edit and delete them (admin); manage saved and favourite places; look up current weather at a location |
| Database Explorer | `/explorer` | all (guests: 6 views) | Run the 10 SQL views as HTML tables; keyword and column filters; sort; view the SQL; export CSV/PDF |
| Conditions & Analytics | `/conditions` | all | Fetch and save route weather; six charts; search, filter and export observations |
| My Profile | `/profile` | admin, user | Edit routing preferences; manage your own feedback |
| Admin | `/admin` | admin | Create, edit and delete records in all nine tables (users and roles, locations, preferences, trips, route options, segments, observations, saved locations, feedback) |

**A short demo script:** sign in as the admin → open **Database Explorer** and step through views 1–10 →
filter View 6 by `driving` and export a PDF → sign out and sign in as **Jordan** (user) → plan a trip from
*Oshawa Centre* to *Lakeview Park* with "Generate estimated alternatives" ticked → compare the alternatives
and read *Why this ranking?* → press **Weather** on a route to store live Open-Meteo conditions → open
**Conditions & Analytics** to see the new observation and the charts.

## The ten SQL views

Defined in [`database/views.sql`](database/views.sql), unchanged from Phase II. Row counts are for the seeded
data.

| # | View | SQL feature | Rows |
|---|---|---|---|
| 1 | `v1_trip_route_details` | Join of five tables (trip, app_user, location ×2, route_option) | 12 |
| 2 | `v2_faster_than_all_mode_averages` | Nested query with **ALL** over a **GROUP BY** subquery | 4 |
| 3 | `v3_faster_than_trip_average` | **Correlated** nested query | 6 |
| 4 | `v4_users_and_feedback` | **FULL JOIN** | 8 |
| 5 | `v5_relevant_locations` | Nested query with **UNION** | 8 |
| 6 | `v6_ranked_route_recommendations` | CTEs, window functions, weighted scoring, DENSE_RANK | 12 |
| 7 | `v7_condition_risk_by_route` | LEFT JOIN + aggregation | 12 |
| 8 | `v8_favourite_saved_locations` | Three-table join + filter | 4 |
| 9 | `v9_low_carbon_alternatives` | Filtering (IN list, toll = 0) | 7 |
| 10 | `v10_user_feedback_summary` | LEFT JOIN + aggregation | 6 |

In the browser, open **Database Explorer** and pick a view. Through the API, use `GET /api/views/v1` …
`/api/views/v10`. Filters are passed as query parameters, for example `/api/views/v6?travel_mode=driving&sort=total_route_score&dir=desc`.
The CSV/PDF downloads are at `/api/views/<key>/export?format=csv|pdf` and accept the same filters.

## Route recommendation algorithm

View 6 implements the Phase II method. For each alternative within one trip:

| Component | Weight | Score (0–100) |
|---|---|---|
| Estimated travel time | **45%** | `100 × fastest duration in trip ÷ route duration` |
| Distance | **25%** | `100 × shortest distance in trip ÷ route distance` |
| Safety and conditions | **15%** | `100 − 20 × highest observation severity (0–5)` on the route's segments |
| Toll cost | **10%** | `max(0, 100 − 20 × toll in dollars)` |
| Preference match | **5%** | `100` if the mode equals the traveller's preferred mode, else `50` |

`total = 0.45·time + 0.25·distance + 0.15·safety + 0.10·toll + 0.05·preference`, ranked with `DENSE_RANK()`
per trip. The planner page labels each route's role: the **database recommendation** (rank 1), the route the
**user selected** (`is_selected`, at most one per trip, enforced by a partial unique index), and the
**source** of each route: *stored data* (seeded or saved), *manual entry*, *heuristic estimate* or *OSRM estimate*.
The routes are planning estimates, not live turn-by-turn navigation.

## External API integration (Open-Meteo)

`POST /api/weather/routes/<route_id>` (the database-connected REST/JSON web service):

1. **Query 1:** `SELECT` the route's segments joined with their start and end `location` coordinates.
2. **External call:** `GET https://api.open-meteo.com/v1/forecast?latitude=…&longitude=…&current=temperature_2m,precipitation,weather_code,wind_speed_10m,wind_gusts_10m` for each segment midpoint, then parse the JSON.
3. **Query 2:** `INSERT INTO condition_observation` (`condition_type='weather'`, `source_name='Open-Meteo'`, mapped severity, description).
4. **Query 3:** `SELECT` the stored Open-Meteo observations for the route, plus the refreshed View 6 ranking.

`GET /api/weather/locations/<id>` is a display-only lookup and stores nothing. The severity mapping is
deterministic and defined by the application: it starts from the WMO weather code (clear 0 … thunderstorm
with hail 5) and raises the value for strong wind (≥ 50 km/h → at least 2), damaging gusts (≥ 70 km/h → 3)
and extreme cold (≤ −15 °C → 2). It is **a heuristic risk estimate, not an authoritative road-safety
assessment**. Network, HTTP and format failures return HTTP 502 with a clear message, and nothing is stored.

## REST API overview

Every endpoint returns JSON. Errors look like `{"error": {"status": 400, "message": "...", "details": {"field": "..."}}}`.
Requests that change data must include the `X-CSRFToken` header, available from the page's
`<meta name="csrf-token">` tag or from `GET /api/auth/csrf`. The complete reference is in [`docs/API.md`](docs/API.md).

| Resource | Endpoints |
|---|---|
| Auth | `POST /api/auth/login`, `POST /api/auth/logout`, `POST /api/auth/guest`, `GET /api/auth/me`, `GET /api/auth/csrf` |
| Trips | `GET/POST /api/trips`, `GET/PUT/DELETE /api/trips/<id>` |
| Routes | `GET/POST /api/trips/<id>/routes`, `POST /api/trips/<id>/routes/generate`, `PUT/DELETE /api/routes/<id>`, `POST /api/routes/<id>/select`, `GET /api/routes` (admin) |
| Segments | `GET/POST /api/routes/<id>/segments`, `GET /api/segments`, `PUT/DELETE /api/segments/<id>` |
| Locations | `GET/POST /api/locations`, `GET/PUT/DELETE /api/locations/<id>` |
| Users | `GET/POST /api/users`, `GET/PUT/DELETE /api/users/<id>` (admin) |
| Preferences | `GET/PUT /api/preferences/me`, `GET/POST /api/preferences`, `PUT/DELETE /api/preferences/<id>` |
| Saved locations | `GET/POST /api/saved-locations`, `PUT/DELETE /api/saved-locations/<id>` |
| Feedback | `GET/POST /api/feedback`, `PUT/DELETE /api/feedback/<id>` |
| Observations | `GET/POST /api/observations`, `PUT/DELETE /api/observations/<id>` |
| Weather | `GET /api/weather/locations/<id>`, `POST /api/weather/routes/<id>` |
| Views | `GET /api/views`, `GET /api/views/<v1..v10>`, `GET /api/views/<key>/export?format=csv\|pdf` |
| Exports | `GET /api/export/trips`, `GET /api/export/observations` (`?format=csv\|pdf` plus filters) |
| Analytics / health | `GET /api/analytics/summary`, `GET /api/health` (public) |

## Running the tests

The tests use a **separate database** (`TEST_DATABASE_URL`). It is created automatically and re-seeded
before each test module, so your demo data is never touched.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Dev
```

```powershell
.\.venv\Scripts\python -m pytest
```

| Suite | File | What it covers |
|---|---|---|
| Database | `tests/test_database.py` | 9 tables, at least 6 rows each; all 10 views and their exact row counts; required SQL patterns; ALL, correlated and UNION semantics; View 6 recomputed independently in Python; FK/UNIQUE/CHECK/partial-unique constraints; cascades |
| Auth | `tests/test_auth.py` | Login success and failure, validation, CSRF, logout, cookie flags, 401/403 behaviour, role-specific pages and navigation, guest restrictions, immediate role changes |
| CRUD | `tests/test_api_crud.py` | GET/POST/PUT/DELETE for every relation, ownership isolation (other users' records return 404), validation, duplicates, invalid foreign keys, filters, error format |
| Views & exports | `tests/test_views_exports.py` | View endpoints, role scoping, keyword/filter/sort, SQL-injection attempts, CSV contents and escaping, valid PDF files, analytics |
| Integration | `tests/test_weather.py` | Open-Meteo parsing and persistence (mocked), failure modes (502, nothing stored), severity mapping, routing estimates, OSRM fallback, database-down 503, **one real Open-Meteo call** (marked `network`; skipped automatically when offline) |
| Browser | `tests/e2e/test_browser.py` | Headless Chromium against a live server: each role's interface, all pages without console errors, all 10 views, filter/sort/export downloads, trip CRUD through forms, client validation, weather, charts, admin CRUD, mobile layout |

Useful variants: `python -m pytest -m "not e2e"` (skip the browser tests), `python -m pytest -m "not network"`
(fully offline), or `scripts\test.ps1`. The latest results are in [`docs/TEST_RESULTS.md`](docs/TEST_RESULTS.md).

To regenerate the evidence screenshots and diagrams, start the app against freshly seeded data, then run:

```powershell
python scripts\capture_screenshots.py
```

```powershell
python scripts\render_diagrams.py
```

## Project structure

```
├── backend/app/
│   ├── __init__.py          # Flask application factory, JSON encoder, security headers
│   ├── config.py            # settings from .env
│   ├── db.py                # SQLAlchemy Core helpers (parameterised SQL)
│   ├── auth.py              # login/logout, role decorators, ownership checks
│   ├── validation.py        # server-side input validation
│   ├── errors.py            # JSON error handling, SQLSTATE → HTTP mapping
│   ├── pages.py             # HTML page routes (server-side role guard)
│   ├── api/                 # REST blueprints: trips, locations, users, preferences,
│   │                        #   saved_locations, feedback, observations, weather, views_api, analytics
│   └── services/            # weather.py (Open-Meteo), routing.py (OSRM/heuristic), exporter.py (CSV/PDF)
├── frontend/
│   ├── templates/           # Jinja2 page shells (login, planner, places, explorer, conditions, profile, admin)
│   └── static/              # css/app.css, js/*.js (ES modules: api.js, ui.js, one per page)
├── database/                # schema.sql, seed.sql, views.sql
├── scripts/                 # init_db.py, setup/run/test .ps1, capture_screenshots.py, render_diagrams.py
├── tests/                   # pytest suites + e2e/ Playwright tests
├── docs/                    # API reference, test results, traceability, diagrams, screenshots
├── docker-compose.yml       # optional PostgreSQL 16 container
├── requirements.txt / requirements-dev.txt
├── .env.example             # configuration template (copy to .env)
└── run.py                   # local entry point
```

## Security and configuration notes

* Never commit `.env`; it is git-ignored. `.env.example` contains placeholders only.
* Passwords are stored only as salted scrypt hashes, and no API response ever includes `password_hash`.
* Every SQL statement uses bound parameters. Table and column names come only from constants in the code;
  view names and filter or sort columns are checked against an allowlist, and LIKE wildcards are escaped.
* Session cookie: HttpOnly, SameSite=Lax, 8-hour lifetime; the session is cleared on login. Set
  `SESSION_COOKIE_SECURE=1` behind HTTPS.
* CSRF tokens (Flask-WTF) are required for every POST, PUT and DELETE, including login.
* Authorisation happens on the server for every request, and the user's role is re-read from the database
  each time. Requests for another user's records return 404, so the API does not even reveal that they exist.
* Responses set `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: strict-origin-when-cross-origin` (other sites receive only the origin, which the OpenStreetMap tile servers require), and API JSON is `no-store`.
* `run.py` uses Flask's built-in server, which is fine for a local demonstration. A production deployment
  would use a WSGI server (for example waitress or gunicorn) behind HTTPS.
* The Phase II reference PDFs contain student information, so they are kept local only (`docs/phase2-reference/*.pdf` is git-ignored).

## Troubleshooting

| Problem | Fix |
|---|---|
| `running scripts is disabled on this system` | Run the scripts as `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1` |
| `Could not connect to PostgreSQL` | Start Docker Desktop and run `docker compose up -d`, or check `DATABASE_URL` (host, port **5433** for Docker, password) |
| Port 5433 or 8000 already in use | Change `POSTGRES_PORT` and the port in `DATABASE_URL`, or `APP_PORT`, in `.env` |
| `permission denied to create database` | Create the database manually (for example in pgAdmin) or give your role `CREATEDB`, then run `python scripts\init_db.py` again |
| Login always says "Security token missing or expired" | Refresh the page; make sure `SECRET_KEY` does not change between restarts |
| Weather shows "Weather service unavailable" | Check your internet connection or proxy; Open-Meteo needs outbound HTTPS. The rest of the app keeps working |
| Charts or map are empty | Chart.js, Leaflet and the map tiles come from public CDNs, so an internet connection is required |
| Demo data got messy | `python scripts\init_db.py` restores the seeded data |
| Playwright errors about a missing browser | `python -m playwright install chromium` |

## Documentation index

* [`docs/API.md`](docs/API.md): REST API reference
* [`docs/TEST_RESULTS.md`](docs/TEST_RESULTS.md): environment, test counts, schema verification, defects fixed
* [`docs/REQUIREMENTS_TRACEABILITY.md`](docs/REQUIREMENTS_TRACEABILITY.md): every Phase III requirement mapped to implementation and evidence
* [`docs/DEMO_CREDENTIALS.md`](docs/DEMO_CREDENTIALS.md): demo accounts
* [`docs/IMPLEMENTATION_SUMMARY.md`](docs/IMPLEMENTATION_SUMMARY.md): factual summary for the final report and presentation
* [`docs/diagrams/`](docs/diagrams): architecture, weather data flow and relational schema (Mermaid source plus PNG/SVG)
* [`docs/screenshots/`](docs/screenshots): screenshots of the running application, including all 10 views

### Screenshots

| | |
|---|---|
| ![Login](docs/screenshots/01-login.png) | ![Explorer](docs/screenshots/view-06-ranked-route-recommendations.png) |
| ![Analytics](docs/screenshots/09-analytics-charts.png) | ![Weather](docs/screenshots/07-weather-integration-planner.png) |
