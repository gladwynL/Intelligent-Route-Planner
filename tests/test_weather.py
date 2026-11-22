"""External REST/JSON integration (Open-Meteo), routing estimates and failure handling.

Most tests mock the HTTP layer for determinism.  ``test_live_open_meteo`` makes a
real call and is skipped automatically when the network is unavailable.
"""
from __future__ import annotations

import pytest
import requests

from backend.app.services import routing
from backend.app.services import weather as wx


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def open_meteo_payload(code=63, temp=3.2, wind=22.0, gusts=41.0, precip=1.4):
    return {
        "latitude": 43.9, "longitude": -78.88,
        "current": {"time": "2026-11-21T14:00", "interval": 900, "temperature_2m": temp, "precipitation": precip,
                    "weather_code": code, "wind_speed_10m": wind, "wind_gusts_10m": gusts},
    }


@pytest.fixture
def mock_open_meteo(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append({"url": url, "params": params})
        return FakeResponse(open_meteo_payload())
    monkeypatch.setattr(wx.requests, "get", fake_get)
    return calls


# ---- severity mapping (pure function) ----------------------------------------

@pytest.mark.parametrize("code,wind,gusts,temp,expected", [
    (0, 5, 10, 10, 0),       # clear
    (61, 5, 10, 10, 1),      # slight rain
    (63, 5, 10, 10, 2),      # moderate rain
    (75, 5, 10, -5, 4),      # heavy snow
    (99, 5, 10, 20, 5),      # thunderstorm with hail
    (0, 55, 60, 10, 2),      # strong wind raises clear sky to 2
    (0, 30, 80, 10, 3),      # damaging gusts raise to 3
    (0, 5, 10, -20, 2),      # extreme cold raises to 2
    (12345, 5, 10, 10, 1),   # unknown code -> cautious 1
])
def test_severity_mapping(code, wind, gusts, temp, expected):
    sev, _, reasons = wx.map_severity(code, wind, gusts, temp)
    assert sev == expected and reasons


def test_description_fits_column():
    cw = wx.CurrentWeather(43.9, -78.9, __import__("datetime").datetime(2026, 11, 21, 14), 3.2, 1.4, 63,
                           "Moderate rain", 22.0, 41.0, 2, [])
    d = cw.description()
    assert len(d) <= 200 and "Moderate rain" in d and "2/5" in d


# ---- database-connected weather web service ---------------------------------

def test_route_weather_fetches_parses_and_persists(user, mock_open_meteo, pg):
    before = pg.execute("SELECT COUNT(*) FROM condition_observation WHERE source_name = 'Open-Meteo'").fetchone()[0]
    r = user.post("/api/weather/routes/4")  # Jordan's transit route on trip 2
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    # Query 1 supplied the segment midpoint coordinates to the external request
    assert mock_open_meteo[0]["params"]["latitude"] == "43.91840"
    assert mock_open_meteo[0]["params"]["current"].startswith("temperature_2m")
    w = body["weather"][0]["current"]
    assert w["condition"] == "Moderate rain" and w["severity"] == 2 and w["temperature_c"] == 3.2
    # Query 2 persisted a row; Query 3 returned it
    assert len(body["inserted_observation_ids"]) == 1
    new_id = body["inserted_observation_ids"][0]
    assert any(o["observation_id"] == new_id for o in body["stored_observations"])
    pg.rollback()
    row = pg.execute("SELECT condition_type, severity, source_name, description FROM condition_observation "
                     "WHERE observation_id = %s", (new_id,)).fetchone()
    assert row[:3] == ("weather", 2, "Open-Meteo") and "app risk estimate" in row[3]
    after = pg.execute("SELECT COUNT(*) FROM condition_observation WHERE source_name = 'Open-Meteo'").fetchone()[0]
    assert after == before + 1
    # stored result is retrievable through the observations query too
    obs = user.get("/api/observations?source=Open-Meteo&route_id=4").get_json()["observations"]
    assert new_id in [o["observation_id"] for o in obs]
    # refreshed View 6 ranking was returned
    assert any(rt["route_id"] == 4 for rt in body["routes"])


def test_location_weather_display_only(user, mock_open_meteo, pg):
    before = pg.execute("SELECT COUNT(*) FROM condition_observation").fetchone()[0]
    r = user.get("/api/weather/locations/1")
    assert r.status_code == 200 and r.get_json()["stored"] is False
    assert r.get_json()["weather"]["condition"] == "Moderate rain"
    pg.rollback()
    assert pg.execute("SELECT COUNT(*) FROM condition_observation").fetchone()[0] == before


@pytest.mark.parametrize("failure", ["timeout", "http500", "badjson", "missingfields"])
def test_external_api_failures_return_502_and_store_nothing(user, monkeypatch, pg, failure):
    def fake_get(*a, **k):
        if failure == "timeout":
            raise requests.Timeout("timed out")
        if failure == "http500":
            return FakeResponse({"error": True, "reason": "Internal"}, status=500)
        if failure == "badjson":
            return FakeResponse(ValueError("not json"))
        return FakeResponse({"current": {"time": "2026-11-21T14:00"}})
    monkeypatch.setattr(wx.requests, "get", fake_get)
    before = pg.execute("SELECT COUNT(*) FROM condition_observation").fetchone()[0]
    r = user.post("/api/weather/routes/3")
    assert r.status_code == 502
    assert "Weather service unavailable" in r.get_json()["error"]["message"]
    pg.rollback()
    assert pg.execute("SELECT COUNT(*) FROM condition_observation").fetchone()[0] == before


def test_weather_unknown_location_404(user, mock_open_meteo):
    assert user.get("/api/weather/locations/999").status_code == 404


@pytest.mark.network
def test_live_open_meteo(app):
    """Real call to Open-Meteo (skipped if offline)."""
    with app.app_context():
        try:
            cw = wx.fetch_current(43.94552, -78.89664)
        except wx.WeatherServiceError as exc:
            pytest.skip(f"Open-Meteo not reachable: {exc}")
    assert 0 <= cw.severity <= 5 and cw.condition and cw.observed_at.year >= 2024


# ---- routing estimates --------------------------------------------------------

def test_haversine_known_distance():
    # Ontario Tech North Campus -> Oshawa GO Station is about 8.5 km in a straight line
    d = routing.haversine_km(43.94552, -78.89664, 43.87061, -78.88485)
    assert 8.0 < d < 9.0


def test_heuristic_estimates_are_ordered_by_speed(app):
    with app.app_context():
        est = {e.travel_mode: e for e in routing.estimate_alternatives(
            {"latitude": 43.94552, "longitude": -78.89664}, {"latitude": 43.87061, "longitude": -78.88485})}
    assert set(est) == {"driving", "transit", "cycling", "walking"}
    assert est["driving"].duration_min < est["transit"].duration_min < est["cycling"].duration_min < est["walking"].duration_min
    assert all(e.source == "heuristic" for e in est.values())


def test_walking_skipped_for_long_trips(app):
    with app.app_context():
        modes = {e.travel_mode for e in routing.estimate_alternatives(
            {"latitude": 43.9, "longitude": -78.9}, {"latitude": 43.65, "longitude": -79.38})}
    assert "walking" not in modes and "driving" in modes


def test_osrm_used_when_enabled_and_falls_back(app, monkeypatch):
    app.config["ENABLE_OSRM"] = True
    try:
        monkeypatch.setattr(routing.requests, "get", lambda *a, **k: FakeResponse(
            {"code": "Ok", "routes": [{"distance": 10234.0, "duration": 900.0}]}))
        with app.app_context():
            est = routing.osrm_driving({"latitude": 43.9, "longitude": -78.9}, {"latitude": 43.87, "longitude": -78.88})
        assert est.source == "osrm" and est.distance_km == 10.23 and est.duration_min == 15

        def boom(*a, **k):
            raise requests.ConnectionError("down")
        monkeypatch.setattr(routing.requests, "get", boom)
        with app.app_context():
            ests = routing.estimate_alternatives({"latitude": 43.9, "longitude": -78.9},
                                                 {"latitude": 43.87, "longitude": -78.88}, ["driving"])
        assert ests[0].source == "heuristic"
    finally:
        app.config["ENABLE_OSRM"] = False


# ---- database connection failure ---------------------------------------------

def test_database_unavailable_returns_503():
    from backend.app import create_app
    from tests.conftest import ApiClient
    broken = create_app({"TESTING": True, "SECRET_KEY": "x", "WTF_CSRF_ENABLED": False,
                         "DATABASE_URL": "postgresql+psycopg://nobody:nopass@127.0.0.1:1/none"})
    c = broken.test_client()
    r = c.get("/api/health")
    assert r.status_code == 503 and r.get_json()["database"] == "unavailable"
    r = c.post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
    assert r.status_code == 503
    assert "unavailable" in r.get_json()["error"]["message"]
    assert "nopass" not in r.get_data(as_text=True)
