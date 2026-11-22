"""CRUD workflows (GET/POST/PUT/DELETE), ownership isolation, validation and filtering."""
from __future__ import annotations

import pytest

NEW_LOCATION = {"location_name": "Oshawa Public Library", "street_address": "65 Bagot Street", "city": "Oshawa",
                "latitude": 43.897200, "longitude": -78.866500, "location_type": "public"}


# ---- locations ------------------------------------------------------------------

def test_location_full_crud(admin, user):
    r = user.post("/api/locations", NEW_LOCATION)
    assert r.status_code == 201
    loc = r.get_json()["location"]
    lid = loc["location_id"]
    assert loc["latitude"] == pytest.approx(43.8972)
    assert admin.get(f"/api/locations/{lid}").get_json()["location"]["city"] == "Oshawa"
    r = admin.put(f"/api/locations/{lid}", {"location_name": "Oshawa Library (McLaughlin)"})
    assert r.status_code == 200 and r.get_json()["location"]["location_name"].startswith("Oshawa Library")
    assert admin.delete(f"/api/locations/{lid}").status_code == 200
    assert admin.get(f"/api/locations/{lid}").status_code == 404


def test_duplicate_coordinates_rejected(user):
    dup = dict(NEW_LOCATION, latitude=43.945520, longitude=-78.896640)
    r = user.post("/api/locations", dup)
    assert r.status_code == 409
    assert "coordinates" in r.get_json()["error"]["message"]


def test_location_validation(user):
    r = user.post("/api/locations", {"location_name": "", "latitude": 120, "longitude": "abc", "location_type": "castle"})
    assert r.status_code == 400
    d = r.get_json()["error"]["details"]
    assert {"location_name", "street_address", "city", "latitude", "longitude", "location_type"} <= set(d)


def test_delete_referenced_location_conflict(admin):
    r = admin.delete("/api/locations/1")
    assert r.status_code == 409
    assert "still used" in r.get_json()["error"]["message"]


def test_location_search_filter(user):
    r = user.get("/api/locations?q=GO%20Station")
    names = [l["location_name"] for l in r.get_json()["locations"]]
    assert names == ["Oshawa GO Station", "Whitby GO Station"]
    r = user.get("/api/locations?type=school&city=Whitby")
    assert [l["location_id"] for l in r.get_json()["locations"]] == [8]


def test_like_wildcards_are_escaped(user):
    assert user.get("/api/locations?q=%25").get_json()["count"] == 0


# ---- trips & routes -------------------------------------------------------------

def test_trip_full_crud_with_generated_routes(user):
    r = user.post("/api/trips", {"origin_location_id": 2, "destination_location_id": 7,
                                 "departure_time": "2026-12-01T08:15", "generate_routes": True})
    assert r.status_code == 201
    body = r.get_json()
    tid = body["trip"]["trip_id"]
    assert body["trip"]["user_id"] == 2 and body["trip"]["trip_status"] == "planned"
    assert {g["travel_mode"] for g in body["generated_routes"]} == {"driving", "transit", "cycling", "walking"}
    assert all(g["source"] == "heuristic" for g in body["generated_routes"])

    detail = user.get(f"/api/trips/{tid}").get_json()
    ranks = sorted(r["recommendation_rank"] for r in detail["routes"])
    assert ranks[0] == 1 and len(detail["routes"]) == 4
    assert all(r["source"] == "heuristic" for r in detail["routes"])

    r = user.put(f"/api/trips/{tid}", {"trip_status": "completed", "actual_duration_min": 27})
    assert r.status_code == 200 and r.get_json()["trip"]["actual_duration_min"] == 27
    # generating again adds nothing: every mode exists
    r = user.post(f"/api/trips/{tid}/routes/generate")
    assert r.status_code == 201 and r.get_json()["generated_routes"] == []
    assert user.delete(f"/api/trips/{tid}").status_code == 200
    assert user.get(f"/api/trips/{tid}").status_code == 404


def test_trip_validation(user):
    r = user.post("/api/trips", {"origin_location_id": 3, "destination_location_id": 3, "departure_time": "soon"})
    assert r.status_code == 400
    d = r.get_json()["error"]["details"]
    assert "departure_time" in d
    r = user.post("/api/trips", {"origin_location_id": 3, "destination_location_id": 3, "departure_time": "2026-12-01T09:00"})
    assert r.status_code == 400 and "destination_location_id" in r.get_json()["error"]["details"]
    r = user.post("/api/trips", {"origin_location_id": 3, "destination_location_id": 999, "departure_time": "2026-12-01T09:00"})
    assert r.status_code == 400 and "does not exist" in r.get_json()["error"]["message"]
    r = user.post("/api/trips", {"departure_time": "2026-12-01T09:00"})
    assert r.status_code == 400 and {"origin_location_id", "destination_location_id"} <= set(r.get_json()["error"]["details"])


def test_actual_duration_only_for_completed(user):
    r = user.put("/api/trips/2", {"trip_status": "planned", "actual_duration_min": 10})
    assert r.status_code == 400


def test_manual_route_and_selection(user):
    r = user.post("/api/trips/2/routes", {"travel_mode": "cycling", "distance_km": 9.5,
                                          "estimated_duration_min": 33, "toll_cost": 0, "road_name": "Simcoe Trail"})
    assert r.status_code == 201
    route = r.get_json()["route"]
    assert route["option_number"] == 3
    routes = user.get("/api/trips/2/routes").get_json()["routes"]
    manual = next(x for x in routes if x["route_id"] == route["route_id"])
    assert manual["source"] == "manual" and manual["via"] == "Manually entered: Simcoe Trail"
    # select it: exactly one selected route remains
    r = user.post(f"/api/routes/{route['route_id']}/select")
    assert r.status_code == 200
    selected = [x["route_id"] for x in r.get_json()["routes"] if x["is_selected"]]
    assert selected == [route["route_id"]]
    # edit keeps single segment in sync
    assert user.put(f"/api/routes/{route['route_id']}", {"distance_km": 9.9}).status_code == 200
    seg = user.get(f"/api/routes/{route['route_id']}/segments").get_json()["segments"][0]
    assert seg["distance_km"] == pytest.approx(9.9)
    assert user.delete(f"/api/routes/{route['route_id']}").status_code == 200


def test_route_validation(user):
    r = user.post("/api/trips/2/routes", {"travel_mode": "teleport", "distance_km": -1, "estimated_duration_min": 0, "toll_cost": -5})
    assert r.status_code == 400
    assert {"travel_mode", "distance_km", "estimated_duration_min", "toll_cost"} <= set(r.get_json()["error"]["details"])


def test_trip_filters(admin):
    data = admin.get("/api/trips?status=completed").get_json()
    assert {t["trip_id"] for t in data["trips"]} >= {1, 2, 3, 4}
    assert all(t["trip_status"] == "completed" for t in data["trips"])
    assert {t["trip_id"] for t in admin.get("/api/trips?mode=walking").get_json()["trips"]} == {5}
    assert [t["trip_id"] for t in admin.get("/api/trips?trip_id=4").get_json()["trips"]] == [4]
    assert {t["trip_id"] for t in admin.get("/api/trips?from=2026-11-04&to=2026-11-05").get_json()["trips"]} == {5, 6}
    assert {t["trip_id"] for t in admin.get("/api/trips?q=Lakeview").get_json()["trips"]} == {5}
    assert admin.get("/api/trips?from=not-a-date").status_code == 400
    assert admin.get("/api/trips?status=lost").status_code == 400


# ---- ownership isolation -------------------------------------------------------

def test_user_sees_only_own_trips(user, admin):
    assert {t["user_id"] for t in user.get("/api/trips").get_json()["trips"]} == {2}
    assert len(admin.get("/api/trips").get_json()["trips"]) >= 6


@pytest.mark.parametrize("method,url,body", [
    ("get", "/api/trips/3", None),
    ("put", "/api/trips/3", {"trip_status": "cancelled"}),
    ("delete", "/api/trips/3", None),
    ("get", "/api/trips/3/routes", None),
    ("post", "/api/trips/3/routes", {"travel_mode": "walking", "distance_km": 5, "estimated_duration_min": 60}),
    ("put", "/api/routes/5", {"distance_km": 1}),
    ("delete", "/api/routes/5", None),
    ("post", "/api/routes/6/select", {}),
    ("put", "/api/saved-locations/3", {"label": "hacked"}),
    ("delete", "/api/saved-locations/3", None),
    ("put", "/api/feedback/3", {"rating": 1}),
    ("delete", "/api/feedback/3", None),
    ("post", "/api/weather/routes/5", {}),
])
def test_cannot_access_other_users_records(user, method, url, body):
    """User 2 (Jordan) must not read or modify user 3's (Taylor's) records."""
    fn = getattr(user, method)
    r = fn(url) if body is None and method in ("get", "delete") else fn(url, json=body)
    assert r.status_code == 404, (url, r.get_json())


def test_cannot_create_trip_for_someone_else(user):
    r = user.post("/api/trips", {"user_id": 3, "origin_location_id": 1, "destination_location_id": 2,
                                 "departure_time": "2026-12-01T09:00"})
    assert r.status_code == 201 and r.get_json()["trip"]["user_id"] == 2  # user_id ignored for non-admins
    user.delete(f"/api/trips/{r.get_json()['trip']['trip_id']}")


def test_cannot_leave_feedback_on_other_users_trip(user):
    assert user.post("/api/feedback", {"trip_id": 3, "rating": 2}).status_code == 403


def test_saved_and_feedback_lists_are_scoped(user):
    assert {s["user_id"] for s in user.get("/api/saved-locations").get_json()["saved_locations"]} == {2}
    assert {f["user_id"] for f in user.get("/api/feedback").get_json()["feedback"]} == {2}


# ---- preferences, saved locations, feedback --------------------------------------

def test_preference_upsert(user):
    r = user.put("/api/preferences/me", {"preferred_mode": "cycling", "max_walking_km": 3.5, "avoid_tolls": False,
                                         "avoid_highways": True, "prioritize_safety": True})
    assert r.status_code == 200 and r.get_json()["preference"]["preferred_mode"] == "cycling"
    assert user.get("/api/preferences/me").get_json()["preference"]["max_walking_km"] == 3.5
    assert user.put("/api/preferences/me", {"preferred_mode": "flying"}).status_code == 400
    user.put("/api/preferences/me", {"preferred_mode": "transit"})


def test_saved_location_crud_and_duplicate(user):
    r = user.post("/api/saved-locations", {"location_id": 5, "label": "Arena", "is_favourite": True})
    assert r.status_code == 201
    sid = r.get_json()["saved_location"]["saved_location_id"]
    assert user.post("/api/saved-locations", {"location_id": 5, "label": "Again"}).status_code == 409
    assert user.put(f"/api/saved-locations/{sid}", {"is_favourite": False}).get_json()["saved_location"]["is_favourite"] is False
    assert user.delete(f"/api/saved-locations/{sid}").status_code == 200


def test_feedback_crud(user):
    r = user.post("/api/feedback", {"trip_id": 2, "rating": 5, "comments": "Great"})
    assert r.status_code == 409  # seeded feedback for (user 2, trip 2) already exists
    fid = 2
    assert user.put(f"/api/feedback/{fid}", {"rating": 3, "comments": "Edited"}).get_json()["feedback"]["rating"] == 3
    assert user.put(f"/api/feedback/{fid}", {"rating": 9}).status_code == 400
    assert user.delete(f"/api/feedback/{fid}").status_code == 200
    r = user.post("/api/feedback", {"trip_id": 2, "rating": 4, "comments": "Re-added"})
    assert r.status_code == 201


# ---- admin management of users, segments, observations -------------------------

def test_admin_user_crud_and_email_validation(admin):
    assert admin.post("/api/users", {"full_name": "Bad", "email": "bad@", "password": "longenough", "user_role": "user"}).status_code == 400
    assert admin.post("/api/users", {"full_name": "Short", "email": "s@example.com", "password": "123", "user_role": "user"}).status_code == 400
    r = admin.post("/api/users", {"full_name": "Morgan Test", "email": "morgan.test@example.com", "password": "Password1", "user_role": "user"})
    assert r.status_code == 201
    uid = r.get_json()["user"]["user_id"]
    assert "password_hash" not in r.get_json()["user"]
    assert admin.post("/api/users", {"full_name": "Dup", "email": "MORGAN.TEST@example.com", "password": "Password1", "user_role": "user"}).status_code == 409
    users = admin.get("/api/users?q=morgan.test").get_json()["users"]
    assert users[0]["preferred_mode"] == "driving"  # default preference created
    assert all("password_hash" not in u for u in admin.get("/api/users").get_json()["users"])
    assert admin.put(f"/api/users/{uid}", {"user_role": "guest"}).get_json()["user"]["user_role"] == "guest"
    assert admin.delete(f"/api/users/{uid}").status_code == 200


def test_admin_segment_and_observation_crud(admin):
    r = admin.post("/api/routes/1/segments", {"sequence_no": 2, "start_location_id": 3, "end_location_id": 2,
                                              "road_name": "Test Road", "distance_km": 1.5, "estimated_duration_min": 4})
    assert r.status_code == 201
    sid = r.get_json()["segment"]["segment_id"]
    assert admin.post("/api/routes/1/segments", {"sequence_no": 2, "start_location_id": 3, "end_location_id": 2,
                                                 "road_name": "Dup", "distance_km": 1, "estimated_duration_min": 1}).status_code == 409
    r = admin.post("/api/observations", {"segment_id": sid, "observed_at": "2026-11-20T10:00", "condition_type": "closure",
                                         "severity": 5, "description": "Full closure", "source_name": "Test"})
    assert r.status_code == 201
    oid = r.get_json()["observation"]["observation_id"]
    # severity 5 on route 1 lowers its safety score to 0 in View 6
    v6 = admin.get("/api/views/v6?trip_id=1").get_json()["rows"]
    assert next(x for x in v6 if x["route_id"] == 1)["safety_score"] == 0
    assert admin.put(f"/api/observations/{oid}", {"severity": 6}).status_code == 400
    assert admin.put(f"/api/observations/{oid}", {"severity": 1}).status_code == 200
    assert admin.delete(f"/api/observations/{oid}").status_code == 200
    assert admin.put(f"/api/segments/{sid}", {"road_name": "Renamed"}).get_json()["segment"]["road_name"] == "Renamed"
    assert admin.delete(f"/api/segments/{sid}").status_code == 200
    assert admin.delete(f"/api/segments/{sid}").status_code == 404


def test_admin_preference_crud(admin):
    r = admin.post("/api/preferences", {"user_id": 1, "preferred_mode": "walking"})
    assert r.status_code == 409  # one preference per user
    prefs = admin.get("/api/preferences").get_json()["preferences"]
    assert len(prefs) == 6
    assert admin.put("/api/preferences/5", {"preferred_mode": "cycling"}).status_code == 200


def test_observation_filters(user):
    obs = user.get("/api/observations?type=weather").get_json()["observations"]
    assert obs and all(o["condition_type"] == "weather" for o in obs)
    obs = user.get("/api/observations?min_severity=3").get_json()["observations"]
    assert {o["observation_id"] for o in obs} == {3, 7, 12}
    assert user.get("/api/observations?source=Open-Meteo&trip_id=4").get_json()["count"] == 1


# ---- generic error handling ----------------------------------------------------

def test_malformed_json_body(user):
    r = user.c.post("/api/locations", data="{not json", content_type="application/json",
                    headers={"X-CSRFToken": user.token()})
    assert r.status_code == 400 and "JSON" in r.get_json()["error"]["message"]


def test_unknown_api_route_is_json_404(user):
    r = user.get("/api/does-not-exist")
    assert r.status_code == 404 and r.is_json


def test_method_not_allowed_is_json(user):
    r = user.c.patch("/api/trips", headers={"X-CSRFToken": user.token()})
    assert r.status_code == 405 and r.is_json


def test_errors_do_not_leak_internals(user):
    r = user.post("/api/locations", dict(NEW_LOCATION, latitude=43.945520, longitude=-78.896640))
    text = r.get_data(as_text=True)
    assert "Traceback" not in text and "psycopg" not in text and "INSERT" not in text
