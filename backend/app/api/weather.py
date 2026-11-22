"""External REST/JSON integration: Open-Meteo current weather.

Flow for POST /api/weather/routes/<route_id> (the database-connected web service):
  Query 1  SELECT the route's segments joined to their start/end coordinates (PostgreSQL)
  HTTP     GET Open-Meteo /v1/forecast?current=... for each segment midpoint, parse JSON
  Query 2  INSERT one condition_observation per segment (condition_type='weather',
           source_name='Open-Meteo', severity from the documented mapping)
  Query 3  SELECT the stored Open-Meteo observations for the route, plus the
           refreshed View 6 ranking for the trip, and return them as JSON.

GET /api/weather/locations/<id> performs Query 1 + the HTTP call only (display, no storage).
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from .. import db
from ..auth import login_required, roles_required
from ..errors import ApiError
from ..services import weather as wx
from .trips import _route_owned, routes_for_trip

bp = Blueprint("weather", __name__, url_prefix="/api/weather")

SOURCE = "Open-Meteo"


def _fetch(lat, lon) -> wx.CurrentWeather:
    try:
        return wx.fetch_current(lat, lon)
    except wx.WeatherServiceError as exc:
        raise ApiError(502, f"Weather service unavailable: {exc}") from exc


@bp.get("/locations/<int:location_id>")
@login_required
def location_weather(location_id):
    loc = db.query_one(
        "SELECT location_id, location_name, city, latitude, longitude FROM location WHERE location_id = :id",
        {"id": location_id})
    if not loc:
        raise ApiError(404, "Location not found.")
    current = _fetch(loc["latitude"], loc["longitude"])
    return jsonify({"location": loc, "weather": current.to_dict(), "stored": False,
                    "source": SOURCE, "disclaimer": "Severity is an application-defined risk estimate."})


@bp.post("/routes/<int:route_id>")
@roles_required("admin", "user")
def route_weather(route_id):
    route = _route_owned(route_id)

    # Query 1: segment coordinates needed for the external request.
    segments = db.query(
        """
        SELECT s.segment_id, s.sequence_no, s.road_name,
               (sl.latitude + el.latitude) / 2.0  AS mid_lat,
               (sl.longitude + el.longitude) / 2.0 AS mid_lon,
               sl.location_name AS start_location, el.location_name AS end_location
        FROM route_segment s
        JOIN location sl ON sl.location_id = s.start_location_id
        JOIN location el ON el.location_id = s.end_location_id
        WHERE s.route_id = :r
        ORDER BY s.sequence_no
        """, {"r": route_id})
    if not segments:
        raise ApiError(400, "This route has no segments to check weather for.")

    # External REST/JSON calls (one per distinct midpoint).
    cache: dict[tuple, wx.CurrentWeather] = {}
    results = []
    for seg in segments:
        key = (round(float(seg["mid_lat"]), 4), round(float(seg["mid_lon"]), 4))
        if key not in cache:
            cache[key] = _fetch(*key)
        results.append((seg, cache[key]))

    # Query 2: persist each observation (single transaction).
    inserted = []
    with db.transaction() as conn:
        for seg, cur in results:
            inserted.append(db.insert("condition_observation", {
                "segment_id": seg["segment_id"],
                "observed_at": cur.observed_at,
                "condition_type": "weather",
                "severity": cur.severity,
                "description": cur.description(),
                "source_name": SOURCE,
            }, "observation_id", conn)["observation_id"])

    # Query 3: read back the stored external results for display.
    stored = db.query(
        """
        SELECT c.observation_id, c.segment_id, s.road_name, c.observed_at, c.severity, c.description, c.source_name
        FROM condition_observation c JOIN route_segment s ON s.segment_id = c.segment_id
        WHERE s.route_id = :r AND c.source_name = :src
        ORDER BY c.observed_at DESC, c.observation_id DESC
        """, {"r": route_id, "src": SOURCE})

    return jsonify({
        "route_id": route_id,
        "trip_id": route["trip_id"],
        "weather": [{"segment": s, "current": c.to_dict()} for s, c in results],
        "inserted_observation_ids": inserted,
        "stored_observations": stored,
        "routes": routes_for_trip(route["trip_id"]),
        "source": SOURCE,
        "disclaimer": "Severity is an application-defined risk estimate, not an official road-safety rating.",
    }), 201
