# Implementation Summary (factual input for the final report and presentation)

This file describes only what is actually implemented and verified in this repository. Team contributions
are not included here; the contribution matrix will be written separately with input from the team.

## Goal and course relevance

The Intelligent Route Planning System puts a web front end on the Phase II PostgreSQL design. Users plan
trips between stored locations in Durham Region, Ontario, compare driving, transit, cycling and walking
alternatives, and get a recommendation computed entirely in SQL (View 6) from weighted time, distance,
safety, toll and preference scores. It uses the course topics: relational design and constraints, SQL views
(joins, ALL with GROUP BY, correlated subqueries, FULL JOIN, UNION, CTEs, window functions), web
programming, scripting (JavaScript), JSON, and REST web services, including an external one.

## Architecture (as built)

* **Database:** PostgreSQL 16.15 (Docker `postgres:16-alpine`, port 5433). 9 relations and 10 views taken
  unchanged from Phase II; demo identities replaced with fictional ones; identity sequences reset after
  seeding; 5 foreign-key indexes added for performance.
* **Backend:** Python 3.12, Flask 3.1 application factory with 12 blueprints, SQLAlchemy 2 Core with
  psycopg 3 and fully parameterised SQL. Sessions use Werkzeug scrypt hashes and Flask-WTF CSRF protection.
  Server-side validation layer; PostgreSQL error codes mapped to HTTP responses.
* **Frontend:** 7 Jinja2 page shells (login, planner, places, explorer, conditions, profile, admin) plus
  vanilla JavaScript ES modules (about 1,900 lines). Uses the Fetch API, Chart.js 4 and Leaflet 1.9 with
  OpenStreetMap tiles. No build step.
* **External services:** Open-Meteo current weather (required integration: data is fetched, parsed and
  stored in `condition_observation`, then queried back). The OSRM public demo server optionally supplies
  driving distance and time for new trips; if it fails, a labelled straight-line heuristic is used instead.
* **Size:** about 7,500 lines across Python, JavaScript, HTML, CSS, SQL and PowerShell (including tests).
* **Diagrams:** `docs/diagrams/architecture.png`, `weather-sequence.png`, `relational-schema.png`
  (Mermaid source alongside). The Phase II ER and relational diagrams still apply unchanged.

## Key features to demonstrate

1. Login with role-specific navigation (admin sees Admin; guests are read-only and see 6 of the 10 views).
2. Database Explorer: all 10 views as HTML tables, with keyword and column filters, sorting, the SQL
   definition, and CSV/PDF export.
3. Route Planner: create a trip, have alternatives estimated automatically, see the database recommendation
   next to the user's selected route and the fastest route, the component scores, and an explanation with a
   weighted-contribution chart. Every route carries a source label (stored, manual, heuristic or OSRM).
4. Live weather: pressing "Weather" on a route stores an Open-Meteo observation and refreshes the ranking.
5. Conditions & Analytics: six Chart.js charts from SQL aggregates, plus a searchable, exportable
   observations table.
6. Admin: create, edit and delete records in all nine tables, with validation and confirmation dialogs.

## Testing outcomes

* **186 automated tests, all passing** (pytest 9.2): 48 database, 37 auth/authorisation/security headers, 40 CRUD and
  validation, 25 views/exports, 23 integration/error handling (including one live Open-Meteo call), and 13
  Playwright browser tests in headless Chromium.
* View row counts on PostgreSQL match the Phase II appendix exactly (12, 4, 6, 8, 8, 12, 12, 4, 7, 6).
* View 6 scores were recomputed independently in Python and match exactly.
* A fresh clone set up with `scripts/setup.ps1` worked end to end.
* Details: `docs/TEST_RESULTS.md`. Mapping to every requirement: `docs/REQUIREMENTS_TRACEABILITY.md`.

## Bugs found and fixed (see TEST_RESULTS §6)

Identity sequences were not advanced after the explicit-ID seed inserts (Phase II defect). Phase II password
placeholders made login impossible. Route generation re-added every mode when none were missing. Several
layout problems were found in the screenshots (view list, mobile overflow, wide comparison table, map
zoom). Hash navigation did not switch views. A race in one browser test was fixed. PDFs needed to be marked
binary in git.

## Screenshots (docs/screenshots/)

`01-login`, `02-admin-planner`, `03-user-planner`, `04-guest-explorer`, `05-route-comparison`,
`05b-ranking-explanation`, `06-crud-create-trip`, `06b-form-validation`, `07-weather-integration-planner`,
`08-search-filter-explorer`, `08b-search-filter-observations`, `09-analytics-charts`, `10-export-controls`,
`11-admin-management`, `11b-admin-create-form`, `12-places-weather`, `13-profile`, `14-mobile-planner`, and
`view-01` … `view-10` (one per SQL view, each showing its SQL definition and result table). Sample exports:
`exports/v6-driving-routes.csv` and `.pdf`.

## Limitations and possible future work

* The alternatives are seeded demonstration data or estimates; there is no live navigation and no transit
  timetable. Future work: GTFS transit data, multi-segment routing, real road geometry on the map.
* The safety score uses the highest severity ever recorded on a route (Phase II design). Future work: weight
  observations by recency, or expire old ones.
* Weather severity is a heuristic defined by the application. Future work: weather forecasts at the departure
  time, and traffic feeds.
* Local deployment uses the Flask development server. Future work: a WSGI server, HTTPS, rate limiting on
  login, and a hosted database.
