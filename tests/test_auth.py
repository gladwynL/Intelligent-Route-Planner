"""Authentication, sessions, CSRF and role-based authorisation."""
from __future__ import annotations

import pytest


def test_login_success_returns_user_without_hash(client):
    r = client.post("/api/auth/login", {"email": "avery.morgan@example.com", "password": "Admin#2026"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["user"]["user_role"] == "admin"
    assert "password_hash" not in body["user"]
    me = client.get("/api/auth/me").get_json()
    assert me["authenticated"] and me["user"]["email"] == "avery.morgan@example.com"


def test_login_email_is_case_insensitive(client):
    r = client.post("/api/auth/login", {"email": "Jordan.Rivera@Example.com", "password": "User#2026"})
    assert r.status_code == 200


@pytest.mark.parametrize("email,password", [
    ("avery.morgan@example.com", "wrong-password"),
    ("nobody@example.com", "Admin#2026"),
])
def test_login_invalid_credentials(client, email, password):
    r = client.post("/api/auth/login", {"email": email, "password": password})
    assert r.status_code == 401
    assert r.get_json()["error"]["message"] == "Invalid email or password."


def test_login_validation_errors(client):
    r = client.post("/api/auth/login", {"email": "not-an-email", "password": ""})
    assert r.status_code == 400
    details = r.get_json()["error"]["details"]
    assert "email" in details and "password" in details


def test_login_requires_csrf_token(client):
    r = client.post("/api/auth/login", {"email": "avery.morgan@example.com", "password": "Admin#2026"}, csrf=False)
    assert r.status_code == 400
    assert "Security token" in r.get_json()["error"]["message"]


def test_mutation_requires_csrf_even_when_logged_in(user):
    r = user.post("/api/locations", {"location_name": "X"}, csrf=False)
    assert r.status_code == 400


def test_logout_clears_session(user):
    assert user.get("/api/trips").status_code == 200
    assert user.post("/api/auth/logout").status_code == 200
    assert user.get("/api/trips").status_code == 401
    assert user.get("/api/auth/me").get_json()["authenticated"] is False


def test_session_cookie_flags(client):
    r = client.post("/api/auth/login", {"email": "avery.morgan@example.com", "password": "Admin#2026"})
    cookie = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_security_headers(client):
    for url in ["/login", "/api/health"]:
        h = client.get(url).headers
        # Origin-only Referer on cross-site requests (needed by OpenStreetMap tile servers).
        assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert h["X-Content-Type-Options"] == "nosniff"
        assert h["X-Frame-Options"] == "DENY"
    assert client.get("/api/health").headers["Cache-Control"] == "no-store"


def test_unauthenticated_api_returns_401(client):
    for url in ["/api/trips", "/api/locations", "/api/views", "/api/observations", "/api/analytics/summary"]:
        assert client.get(url).status_code == 401, url


def test_unauthenticated_page_redirects_to_login(client):
    r = client.get("/planner")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_health_is_public(client):
    body = client.get("/api/health").get_json()
    assert body["status"] == "ok" and body["table_count"] == 9 and body["view_count"] == 10


# ---- role pages -------------------------------------------------------------

def test_admin_page_access_by_role(admin, user, guest):
    assert admin.get("/admin").status_code == 200
    assert user.get("/admin").status_code == 403
    assert guest.get("/admin").status_code == 403


def test_navigation_differs_by_role(admin, user, guest):
    a, u, g = (c.get("/planner").get_data(as_text=True) for c in (admin, user, guest))
    assert 'href="/admin"' in a and 'href="/admin"' not in u and 'href="/admin"' not in g
    assert 'href="/profile"' in u and 'href="/profile"' not in g
    assert 'id="plan-form"' in u and 'id="plan-form"' not in g


def test_guest_profile_page_forbidden(guest):
    assert guest.get("/profile").status_code == 403


# ---- API authorisation --------------------------------------------------------

@pytest.mark.parametrize("method,url", [
    ("get", "/api/users"), ("post", "/api/users"), ("put", "/api/users/2"), ("delete", "/api/users/2"),
    ("put", "/api/locations/1"), ("delete", "/api/locations/1"),
    ("post", "/api/observations"), ("delete", "/api/observations/1"),
    ("get", "/api/segments"), ("get", "/api/routes"), ("get", "/api/preferences"),
])
def test_admin_only_endpoints_forbidden_for_user(user, method, url):
    r = getattr(user, method)(url, json={}) if method != "get" else user.get(url)
    assert r.status_code == 403


@pytest.mark.parametrize("method,url,body", [
    ("post", "/api/trips", {"origin_location_id": 1, "destination_location_id": 2, "departure_time": "2026-12-01T09:00"}),
    ("post", "/api/locations", {"location_name": "G", "street_address": "1 St", "city": "Oshawa", "latitude": 43, "longitude": -78, "location_type": "home"}),
    ("post", "/api/saved-locations", {"location_id": 2, "label": "x"}),
    ("post", "/api/feedback", {"trip_id": 6, "rating": 5}),
    ("put", "/api/preferences/me", {"preferred_mode": "walking"}),
    ("post", "/api/weather/routes/11", {}),
    ("delete", "/api/trips/6", None),
])
def test_guest_cannot_mutate(guest, anon_guest, method, url, body):
    for c in (guest, anon_guest):
        r = getattr(c, method)(url, json=body) if body is not None else getattr(c, method)(url)
        assert r.status_code == 403, (url, r.get_json())


def test_guest_can_read_public_data(anon_guest):
    assert anon_guest.get("/api/locations").status_code == 200
    assert anon_guest.get("/api/views/v6").status_code == 200
    assert anon_guest.get("/api/analytics/summary").status_code == 200
    assert anon_guest.get("/api/trips").get_json()["count"] == 0


def test_role_change_takes_effect_immediately(app, admin):
    c = __import__("tests.conftest", fromlist=["ApiClient"]).ApiClient(app).login("user3")
    assert c.get("/api/trips").status_code == 200
    assert admin.put("/api/users/3", {"user_role": "guest"}).status_code == 200
    assert c.post("/api/locations", {}).status_code == 403
    assert admin.put("/api/users/3", {"user_role": "user"}).status_code == 200


def test_admin_cannot_demote_or_delete_self(admin):
    assert admin.put("/api/users/1", {"user_role": "user"}).status_code == 400
    assert admin.delete("/api/users/1").status_code == 400
