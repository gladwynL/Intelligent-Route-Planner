# REST/JSON API Reference

Base URL: `http://127.0.0.1:8000`. Every `/api/*` endpoint returns JSON, except the export endpoints, which
return a file download.

## Conventions

* **Authentication:** session cookie set by `POST /api/auth/login`, or by `POST /api/auth/guest` for an
  anonymous guest session.
* **CSRF:** every `POST`, `PUT` and `DELETE` request must send the header `X-CSRFToken: <token>`. Get the
  token from `GET /api/auth/csrf` or from the page's `<meta name="csrf-token">`. A new token is issued after login.
* **Bodies:** `Content-Type: application/json`. Unknown fields are ignored. `PUT` is a partial update: only
  the fields you send are validated and changed.
* **Roles:** `A` = admin, `U` = user, `G` = guest. "own" means users can only reach their own records;
  requests for another user's record return **404**.
* **Errors:**

```json
{ "error": { "status": 400, "message": "Please correct the highlighted fields.",
             "details": { "email": "Email must be a valid email address." } } }
```

| Status | Meaning |
|---|---|
| 400 | Validation failed, malformed JSON, missing CSRF token, invalid filter, or CHECK/NOT NULL violation |
| 401 | Not signed in |
| 403 | Signed in, but the role is not allowed |
| 404 | Record does not exist, or belongs to another user |
| 405 | HTTP method not allowed |
| 409 | Duplicate (UNIQUE) or still referenced by other records (FK) |
| 502 | External weather service failed (nothing stored) |
| 503 | Database unavailable |

## Authentication

| Method & path | Roles | Body / notes | Response |
|---|---|---|---|
| `GET /api/auth/csrf` | public | — | `{"csrf_token": "…"}` |
| `POST /api/auth/login` | public | `{"email", "password"}` | `200 {"user": {...}, "redirect": "/planner"}` · `401` invalid credentials |
| `POST /api/auth/guest` | public | — | anonymous guest session |
| `POST /api/auth/logout` | any | — | `{"ok": true}` |
| `GET /api/auth/me` | public | — | `{"authenticated": bool, "user": {...}\|null}` |

## Trips, routes and segments

| Method & path | Roles | Notes |
|---|---|---|
| `GET /api/trips` | A (all), U/G (own) | Filters: `q` (origin/destination/traveller), `status`, `mode`, `trip_id`, `location_id`, `from`, `to` (YYYY-MM-DD), `user_id` (admin) |
| `POST /api/trips` | A, U | `{origin_location_id, destination_location_id, departure_time, trip_status?, actual_duration_min?, generate_routes?: bool, user_id? (admin)}` → `201 {"trip", "generated_routes"}` |
| `GET /api/trips/<id>` | own / A | `{"trip", "routes" (with View 6 scores, View 7 risk, source label), "locations", "preferred_mode"}` |
| `PUT /api/trips/<id>` | own / A | any trip field; `actual_duration_min` only allowed when `trip_status` is `completed` |
| `DELETE /api/trips/<id>` | own / A | cascades to routes, segments, observations and feedback |
| `GET /api/trips/<id>/routes` | own / A | ranked alternatives |
| `POST /api/trips/<id>/routes` | own / A | `{travel_mode, distance_km, estimated_duration_min, toll_cost?, road_name?}`; creates one origin→destination segment |
| `POST /api/trips/<id>/routes/generate` | own / A | adds estimated alternatives for any travel modes the trip doesn't have yet |
| `PUT /api/routes/<id>` | own / A | partial route update (a single segment is kept in sync) |
| `DELETE /api/routes/<id>` | own / A | |
| `POST /api/routes/<id>/select` | own / A | marks the route as the user's choice (unselects the others) |
| `GET /api/routes` | A | all route options; filters `trip_id`, `mode` |
| `GET /api/routes/<id>/segments` | own / A | |
| `POST /api/routes/<id>/segments` | A | `{sequence_no, start_location_id, end_location_id, road_name, distance_km, estimated_duration_min}` |
| `GET /api/segments` | A | filters `route_id`, `trip_id`, `q` |
| `PUT /api/segments/<id>`, `DELETE /api/segments/<id>` | A | |

Example: create a trip and estimate alternatives.

```http
POST /api/trips
X-CSRFToken: …
Content-Type: application/json

{"origin_location_id": 2, "destination_location_id": 7, "departure_time": "2026-12-01T08:15", "generate_routes": true}
```

```json
{ "trip": {"trip_id": 7, "user_id": 2, "trip_status": "planned", "...": "..."},
  "generated_routes": [{"route_id": 13, "travel_mode": "driving", "distance_km": 7.17,
                        "estimated_duration_min": 12, "source": "osrm"}, "..."] }
```

## Locations, users, preferences, saved locations, feedback

| Method & path | Roles | Notes |
|---|---|---|
| `GET /api/locations` | A, U, G | filters `q`, `city`, `type`; includes `trip_count` |
| `GET /api/locations/<id>` | A, U, G | |
| `POST /api/locations` | A, U | `{location_name, street_address, city, latitude, longitude, location_type}` |
| `PUT /api/locations/<id>`, `DELETE /api/locations/<id>` | A | delete returns 409 if trips or segments still reference it |
| `GET /api/users`, `POST /api/users` | A | filters `q`, `role`; create `{full_name, email, password (≥ 8), user_role}` (also creates a default preference) |
| `GET/PUT/DELETE /api/users/<id>` | A | `password` is optional on PUT; admins cannot demote or delete themselves; `password_hash` is never returned |
| `GET /api/preferences/me`, `PUT /api/preferences/me` | any / A, U | upsert `{preferred_mode, max_walking_km?, avoid_tolls?, avoid_highways?, prioritize_safety?}` |
| `GET /api/preferences`, `POST /api/preferences` | A | |
| `PUT/DELETE /api/preferences/<id>` | A | |
| `GET /api/saved-locations` | own / A | filters `q`, `user_id` (admin) |
| `POST /api/saved-locations` | A, U | `{location_id, label, is_favourite?, user_id? (admin)}` |
| `PUT/DELETE /api/saved-locations/<id>` | own / A | |
| `GET /api/feedback` | own / A | filters `trip_id`, `rating`, `q`, `user_id` (admin) |
| `POST /api/feedback` | A, U | `{trip_id, rating (1–5), comments?}`; users may only rate their own trips |
| `PUT/DELETE /api/feedback/<id>` | own / A | |

## Condition observations and weather (external REST/JSON)

| Method & path | Roles | Notes |
|---|---|---|
| `GET /api/observations` | A, U, G | filters `type`, `min_severity`, `source`, `route_id`, `trip_id`, `q`, `from`, `to` |
| `POST /api/observations` | A | `{segment_id, observed_at, condition_type, severity (0–5), description, source_name}` |
| `PUT/DELETE /api/observations/<id>` | A | |
| `GET /api/weather/locations/<id>` | A, U, G | live Open-Meteo lookup for one location, **not stored** |
| `POST /api/weather/routes/<id>` | own / A | Query 1 (segment coordinates) → Open-Meteo → Query 2 (INSERT observations) → Query 3 (stored rows plus refreshed ranking); `201` |

Example response from `POST /api/weather/routes/13` (abridged, from a live call):

```json
{ "route_id": 13, "trip_id": 7,
  "weather": [{ "segment": {"segment_id": 13, "road_name": "OSRM driving route (public demo server)"},
                "current": {"temperature_c": 4.2, "condition": "Clear sky", "weather_code": 0,
                            "wind_speed_kmh": 4.0, "severity": 0,
                            "risk_reasons": ["Clear sky (WMO 0) -> base 0"]} }],
  "inserted_observation_ids": [13],
  "stored_observations": [{"observation_id": 13, "severity": 0, "source_name": "Open-Meteo", "...": "..."}],
  "routes": ["... View 6 ranking ..."],
  "disclaimer": "Severity is an application-defined risk estimate, not an official road-safety rating." }
```

## SQL views, exports, analytics, health

| Method & path | Roles | Notes |
|---|---|---|
| `GET /api/views` | any | the views your role may open, with their columns and filters |
| `GET /api/views/<v1…v10>` | per view | `{"view", "rows", "count", "sql"}`; params: `q` (keyword across all columns), the per-view column filters, `sort`, `dir` |
| `GET /api/views/<key>/export?format=csv\|pdf` | per view | same filters and scoping as the view itself |
| `GET /api/export/trips?format=csv\|pdf` | any (scoped) | trip filters apply |
| `GET /api/export/observations?format=csv\|pdf` | any | observation filters apply |
| `GET /api/analytics/summary` | any | table counts, average duration by mode, severity distribution, conditions by type, View 6 scores, rating distribution, weather trend |
| `GET /api/health` | public | `{"status": "ok", "server_version", "table_count": 9, "view_count": 10}`, or `503` |

View access: admins see all ten. Users see all ten, but views 1, 4, 8 and 10 return only their own rows.
Guests see views 2, 3, 5, 6, 7 and 9.
