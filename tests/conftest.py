"""Shared pytest fixtures.

Tests run against a SEPARATE PostgreSQL database (TEST_DATABASE_URL, default
``route_planner_test``), which is created if missing and re-initialised from
database/*.sql before every test module that mutates data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

import init_db  # noqa: E402  (scripts/init_db.py)

TEST_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://route_planner:route_planner_dev@localhost:5433/route_planner_test",
)
if TEST_URL == os.getenv("DATABASE_URL"):
    raise RuntimeError("TEST_DATABASE_URL must differ from DATABASE_URL so tests never touch app data.")

ACCOUNTS = {
    "admin": ("avery.morgan@example.com", "Admin#2026", 1),
    "user": ("jordan.rivera@example.com", "User#2026", 2),
    "user3": ("taylor.brooks@example.com", "User#2026", 3),
    "guest": ("daniel.chen@example.com", "Guest#2026", 6),
}


def reset_database():
    conninfo = init_db.to_libpq(TEST_URL)
    init_db.ensure_database(conninfo)
    init_db.run_scripts(conninfo)


@pytest.fixture(scope="session")
def conninfo():
    return init_db.to_libpq(TEST_URL)


@pytest.fixture(scope="module", autouse=True)
def fresh_db():
    """Every test module starts from the seeded Phase II data."""
    reset_database()
    yield


@pytest.fixture
def pg(conninfo):
    """Raw psycopg connection for database-level tests (rolled back afterwards)."""
    with psycopg.connect(conninfo) as conn:
        yield conn
        conn.rollback()


@pytest.fixture(scope="session")
def app():
    from backend.app import create_app
    application = create_app({
        "TESTING": True,
        "DATABASE_URL": TEST_URL,
        "SECRET_KEY": "test-secret-key",
        "ENABLE_OSRM": False,          # deterministic heuristic estimates in tests
        "WTF_CSRF_ENABLED": True,      # CSRF stays ON: clients send the token like the browser does
    })
    return application


class ApiClient:
    """Test client wrapper that behaves like the frontend: JSON + CSRF header."""

    def __init__(self, app):
        self.c = app.test_client()
        self._token = None

    def token(self):
        if not self._token:
            self._token = self.c.get("/api/auth/csrf").get_json()["csrf_token"]
        return self._token

    def _send(self, method, url, json=None, csrf=True, **kw):
        headers = kw.pop("headers", {})
        if csrf:
            headers["X-CSRFToken"] = self.token()
        return self.c.open(url, method=method, json=json, headers=headers, **kw)

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, **kw):
        return self._send("POST", url, json=json if json is not None else {}, **kw)

    def put(self, url, json=None, **kw):
        return self._send("PUT", url, json=json, **kw)

    def delete(self, url, **kw):
        return self._send("DELETE", url, **kw)

    def login(self, role):
        email, pw, _ = ACCOUNTS[role]
        r = self.post("/api/auth/login", {"email": email, "password": pw})
        assert r.status_code == 200, r.get_json()
        self._token = None  # session was cleared on login -> new CSRF token
        return self


@pytest.fixture
def client(app):
    return ApiClient(app)


@pytest.fixture
def admin(app):
    return ApiClient(app).login("admin")


@pytest.fixture
def user(app):
    return ApiClient(app).login("user")


@pytest.fixture
def other_user(app):
    return ApiClient(app).login("user3")


@pytest.fixture
def guest(app):
    return ApiClient(app).login("guest")


@pytest.fixture
def anon_guest(app):
    c = ApiClient(app)
    assert c.post("/api/auth/guest").status_code == 200
    c._token = None
    return c
