"""Trips, route options and route segments.

/api/trips                      GET (search/filter), POST
/api/trips/<id>                 GET (detail incl. ranked routes), PUT, DELETE
/api/trips/<id>/routes          GET, POST (manually entered alternative)
/api/trips/<id>/routes/generate POST (estimated alternatives for missing modes)
/api/routes/<id>                PUT, DELETE
/api/routes/<id>/select         POST (user's chosen route; one per trip)
/api/routes/<id>/segments       GET, POST
/api/segments                   GET (admin listing)
/api/segments/<id>              PUT, DELETE
/api/export/trips               GET ?format=csv|pdf

Recommendation scores always come from View 6 (v6_ranked_route_recommendations)
so the weighting lives in exactly one place: the database.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from .. import db
from ..auth import current_user_id, ensure_owner, is_admin, login_required, roles_required
from ..errors import ApiError
from ..services import routing
from ..validation import (TRAVEL_MODES, TRIP_STATUSES, Field, arg_choice, arg_date, arg_int,
                          arg_text, json_body, like, validate)
from .common import created, export_response, not_found

bp = Blueprint("trips", __name__, url_prefix="/api")

TRIP_FIELDS = [
    Field("origin_location_id", "int", required=True, min=1, label="Origin"),
    Field("destination_location_id", "int", required=True, min=1, label="Destination"),
    Field("departure_time", "datetime", required=True, label="Departure time"),
    Field("trip_status", "str", choices=TRIP_STATUSES, label="Status"),
    Field("actual_duration_min", "int", min=1, max=100000, nullable=True, label="Actual duration"),
]
ROUTE_FIELDS = [
    Field("travel_mode", "str", required=True, choices=TRAVEL_MODES, label="Travel mode"),
    Field("distance_km", "num", required=True, min=0.01, max=99999.99, places=2, label="Distance"),
    Field("estimated_duration_min", "int", required=True, min=1, max=100000, label="Estimated duration"),
    Field("toll_cost", "num", min=0, max=99999.99, places=2, label="Toll cost"),
]
SEGMENT_FIELDS = [
    Field("sequence_no", "int", required=True, min=1, max=1000, label="Sequence number"),
    Field("start_location_id", "int", required=True, min=1, label="Start location"),
    Field("end_location_id", "int", required=True, min=1, label="End location"),
    Field("road_name", "str", required=True, max_len=120, label="Road / service name"),
    Field("distance_km", "num", required=True, min=0.01, max=99999.99, places=2, label="Distance"),
    Field("estimated_duration_min", "int", required=True, min=1, max=100000, label="Estimated duration"),
]

TRIP_SELECT = """
SELECT t.trip_id, t.user_id, u.full_name, t.origin_location_id, o.location_name AS origin,
       t.destination_location_id, d.location_name AS destination, t.requested_at, t.departure_time,
       t.trip_status, t.actual_duration_min,
       (SELECT COUNT(*) FROM route_option r WHERE r.trip_id = t.trip_id) AS route_count,
       (SELECT r.travel_mode FROM route_option r WHERE r.trip_id = t.trip_id AND r.is_selected) AS selected_mode,
       (SELECT v.travel_mode FROM v6_ranked_route_recommendations v
         WHERE v.trip_id = t.trip_id AND v.recommendation_rank = 1
         ORDER BY v.route_id LIMIT 1) AS recommended_mode
FROM trip t
JOIN app_user u ON u.user_id = t.user_id
JOIN location o ON o.location_id = t.origin_location_id
JOIN location d ON d.location_id = t.destination_location_id
"""

ROUTES_SELECT = """
SELECT r.route_id, r.trip_id, r.option_number, r.travel_mode, r.distance_km, r.estimated_duration_min,
       r.toll_cost, r.is_selected, r.generated_at,
       v.time_score, v.distance_score, v.safety_score, v.toll_score, v.preference_score,
       v.total_route_score, v.recommendation_rank,
       k.observation_count, k.average_severity, k.maximum_severity,
       (SELECT string_agg(s.road_name, ' / ' ORDER BY s.sequence_no)
          FROM route_segment s WHERE s.route_id = r.route_id) AS via
FROM route_option r
LEFT JOIN v6_ranked_route_recommendations v ON v.route_id = r.route_id
LEFT JOIN v7_condition_risk_by_route k ON k.route_id = r.route_id
WHERE r.trip_id = :trip_id
ORDER BY v.recommendation_rank NULLS LAST, r.option_number
"""


def _source_of(via: str | None) -> str:
    """Classify where a stored route came from, for honest labelling in the UI."""
    if not via:
        return "stored"
    if via.startswith("OSRM"):
        return "osrm"
    if via.startswith("Heuristic estimate"):
        return "heuristic"
    if via.startswith("Manually entered"):
        return "manual"
    return "stored"


def _trip_owned(trip_id: int) -> dict:
    row = db.query_one("SELECT * FROM trip WHERE trip_id = :id", {"id": trip_id})
    if not row:
        not_found("Trip")
    ensure_owner(row["user_id"])
    return row


def _route_owned(route_id: int) -> dict:
    row = db.query_one(
        "SELECT r.*, t.user_id, t.origin_location_id, t.destination_location_id "
        "FROM route_option r JOIN trip t ON t.trip_id = r.trip_id WHERE r.route_id = :id", {"id": route_id})
    if not row:
        not_found("Route")
    ensure_owner(row["user_id"])
    return row


def routes_for_trip(trip_id: int) -> list[dict]:
    rows = db.query(ROUTES_SELECT, {"trip_id": trip_id})
    for r in rows:
        r["source"] = _source_of(r.get("via"))
    return rows


def _trip_filters() -> db.Filters:
    f = db.Filters()
    if is_admin():
        if uid := arg_int("user_id"):
            f.add("t.user_id = :uid", uid=uid)
    else:
        f.add("t.user_id = :uid", uid=current_user_id() or -1)
    if tid := arg_int("trip_id"):
        f.add("t.trip_id = :tid", tid=tid)
    if status := arg_choice("status", TRIP_STATUSES):
        f.add("t.trip_status = :status", status=status)
    if mode := arg_choice("mode", TRAVEL_MODES):
        f.add("EXISTS (SELECT 1 FROM route_option r WHERE r.trip_id = t.trip_id AND r.travel_mode = :mode)",
              mode=mode)
    if q := arg_text("q"):
        f.add("(o.location_name ILIKE :q OR d.location_name ILIKE :q OR u.full_name ILIKE :q)", q=like(q))
    if loc := arg_int("location_id"):
        f.add("(t.origin_location_id = :loc OR t.destination_location_id = :loc)", loc=loc)
    if start := arg_date("from"):
        f.add("t.departure_time >= CAST(:dfrom AS timestamp)", dfrom=start)
    if end := arg_date("to"):
        f.add("t.departure_time < CAST(:dto AS timestamp) + INTERVAL '1 day'", dto=end)
    return f


# ---- trips -------------------------------------------------------------------

@bp.get("/trips")
@login_required
def list_trips():
    f = _trip_filters()
    rows = db.query(f"{TRIP_SELECT}{f.where()} ORDER BY t.departure_time DESC, t.trip_id DESC", f.params)
    return jsonify({"trips": rows, "count": len(rows)})


@bp.get("/export/trips")
@login_required
def export_trips():
    f = _trip_filters()
    rows = db.query(f"{TRIP_SELECT}{f.where()} ORDER BY t.departure_time DESC", f.params)
    cols = ["trip_id", "full_name", "origin", "destination", "departure_time", "trip_status",
            "actual_duration_min", "route_count", "selected_mode", "recommended_mode"]
    return export_response("trips", "Trips", cols, rows)


@bp.get("/trips/<int:trip_id>")
@login_required
def get_trip(trip_id):
    _trip_owned(trip_id)
    trip = db.query_one(f"{TRIP_SELECT} WHERE t.trip_id = :id", {"id": trip_id})
    coords = db.query(
        "SELECT location_id, location_name, latitude, longitude FROM location "
        "WHERE location_id IN (:o, :d)", {"o": trip["origin_location_id"], "d": trip["destination_location_id"]})
    pref = db.query_one("SELECT preferred_mode FROM user_preference WHERE user_id = :u", {"u": trip["user_id"]})
    return jsonify({
        "trip": trip,
        "routes": routes_for_trip(trip_id),
        "locations": coords,
        "preferred_mode": pref["preferred_mode"] if pref else None,
    })


def _check_locations_differ(data: dict, existing: dict | None = None):
    o = data.get("origin_location_id", existing and existing["origin_location_id"])
    d = data.get("destination_location_id", existing and existing["destination_location_id"])
    if o is not None and o == d:
        raise ApiError(400, "Please correct the highlighted fields.",
                       {"destination_location_id": "Destination must differ from the origin."})


def _check_completed(data: dict, existing: dict | None = None):
    status = data.get("trip_status", existing and existing["trip_status"])
    if status != "completed" and data.get("actual_duration_min"):
        raise ApiError(400, "Please correct the highlighted fields.",
                       {"actual_duration_min": "Actual duration can only be recorded for completed trips."})


@bp.post("/trips")
@roles_required("admin", "user")
def create_trip():
    body = json_body()
    fields = TRIP_FIELDS + ([Field("user_id", "int", min=1, label="User")] if is_admin() else [])
    data = validate(body, fields)
    _check_locations_differ(data)
    data.setdefault("trip_status", "planned")
    _check_completed(data)
    data["user_id"] = data.get("user_id") or current_user_id()
    generate = bool(body.get("generate_routes"))
    with db.transaction() as conn:
        data["requested_at"] = db.query_one("SELECT LOCALTIMESTAMP(0) AS now", None, conn)["now"]
        trip = db.insert("trip", data, "*", conn)
        generated = _generate_routes(trip, conn) if generate else []
    return created({"trip": trip, "generated_routes": generated})


@bp.put("/trips/<int:trip_id>")
@roles_required("admin", "user")
def update_trip(trip_id):
    existing = _trip_owned(trip_id)
    data = validate(json_body(), TRIP_FIELDS, partial=True)
    _check_locations_differ(data, existing)
    _check_completed(data, existing)
    if data.get("trip_status") in ("planned", "cancelled"):
        data["actual_duration_min"] = None
    row = db.update("trip", "trip_id", trip_id, data)
    return jsonify({"trip": row})


@bp.delete("/trips/<int:trip_id>")
@roles_required("admin", "user")
def delete_trip(trip_id):
    _trip_owned(trip_id)
    db.delete("trip", "trip_id", trip_id)
    return jsonify({"deleted": trip_id})


# ---- route options -----------------------------------------------------------

@bp.get("/trips/<int:trip_id>/routes")
@login_required
def list_routes(trip_id):
    _trip_owned(trip_id)
    return jsonify({"routes": routes_for_trip(trip_id)})


def _next_option(trip_id: int, conn) -> int:
    return db.query_one("SELECT COALESCE(MAX(option_number), 0) + 1 AS n FROM route_option WHERE trip_id = :t",
                        {"t": trip_id}, conn)["n"]


def _add_route(trip: dict, values: dict, road_name: str, conn) -> dict:
    """Insert a route_option plus a single origin->destination segment."""
    route = db.insert("route_option", {
        "trip_id": trip["trip_id"],
        "option_number": _next_option(trip["trip_id"], conn),
        "travel_mode": values["travel_mode"],
        "distance_km": values["distance_km"],
        "estimated_duration_min": values["estimated_duration_min"],
        "toll_cost": values.get("toll_cost", 0),
    }, "*", conn)
    db.insert("route_segment", {
        "route_id": route["route_id"], "sequence_no": 1,
        "start_location_id": trip["origin_location_id"], "end_location_id": trip["destination_location_id"],
        "road_name": road_name[:120], "distance_km": values["distance_km"],
        "estimated_duration_min": values["estimated_duration_min"],
    }, "segment_id", conn)
    return route


def _generate_routes(trip: dict, conn) -> list[dict]:
    """Create estimated alternatives for every travel mode the trip does not have yet."""
    locs = {r["location_id"]: r for r in db.query(
        "SELECT location_id, latitude, longitude FROM location WHERE location_id IN (:o, :d)",
        {"o": trip["origin_location_id"], "d": trip["destination_location_id"]}, conn)}
    existing = {r["travel_mode"] for r in db.query(
        "SELECT travel_mode FROM route_option WHERE trip_id = :t", {"t": trip["trip_id"]}, conn)}
    missing = [m for m in TRAVEL_MODES if m not in existing]
    out = []
    for est in routing.estimate_alternatives(locs[trip["origin_location_id"]],
                                             locs[trip["destination_location_id"]], missing):
        route = _add_route(trip, {"travel_mode": est.travel_mode, "distance_km": est.distance_km,
                                  "estimated_duration_min": est.duration_min, "toll_cost": 0},
                           est.label, conn)
        route["source"] = est.source
        out.append(route)
    return out


@bp.post("/trips/<int:trip_id>/routes")
@roles_required("admin", "user")
def create_route(trip_id):
    trip = _trip_owned(trip_id)
    body = json_body()
    data = validate(body, ROUTE_FIELDS + [Field("road_name", "str", max_len=90, label="Road / service name")])
    road = data.pop("road_name", None)
    label = f"Manually entered: {road}" if road else "Manually entered route"
    with db.transaction() as conn:
        route = _add_route(trip, data, label, conn)
    return created({"route": route})


@bp.post("/trips/<int:trip_id>/routes/generate")
@roles_required("admin", "user")
def generate_routes(trip_id):
    trip = _trip_owned(trip_id)
    with db.transaction() as conn:
        generated = _generate_routes(trip, conn)
    msg = (f"Added {len(generated)} estimated alternative(s)." if generated
           else "All supported travel modes already have an alternative for this trip.")
    return created({"generated_routes": generated, "message": msg, "routes": routes_for_trip(trip_id)})


@bp.put("/routes/<int:route_id>")
@roles_required("admin", "user")
def update_route(route_id):
    _route_owned(route_id)
    data = validate(json_body(), ROUTE_FIELDS, partial=True)
    with db.transaction() as conn:
        row = db.update("route_option", "route_id", route_id, data, conn)
        # Keep a single-segment route consistent with its parent option.
        seg_vals = {k: data[k] for k in ("distance_km", "estimated_duration_min") if k in data}
        if seg_vals:
            segs = db.query("SELECT segment_id FROM route_segment WHERE route_id = :r", {"r": route_id}, conn)
            if len(segs) == 1:
                db.update("route_segment", "segment_id", segs[0]["segment_id"], seg_vals, conn)
    return jsonify({"route": row})


@bp.delete("/routes/<int:route_id>")
@roles_required("admin", "user")
def delete_route(route_id):
    _route_owned(route_id)
    db.delete("route_option", "route_id", route_id)
    return jsonify({"deleted": route_id})


@bp.post("/routes/<int:route_id>/select")
@roles_required("admin", "user")
def select_route(route_id):
    route = _route_owned(route_id)
    with db.transaction() as conn:
        # Clear first, then set: respects the one_selected_route_per_trip partial unique index.
        db.execute("UPDATE route_option SET is_selected = FALSE WHERE trip_id = :t AND is_selected",
                   {"t": route["trip_id"]}, conn)
        db.execute("UPDATE route_option SET is_selected = TRUE WHERE route_id = :r", {"r": route_id}, conn)
    return jsonify({"selected_route_id": route_id, "routes": routes_for_trip(route["trip_id"])})


# ---- route segments ----------------------------------------------------------

SEGMENT_SELECT = """
SELECT s.*, sl.location_name AS start_location, el.location_name AS end_location, r.trip_id, r.travel_mode
FROM route_segment s
JOIN route_option r ON r.route_id = s.route_id
JOIN location sl ON sl.location_id = s.start_location_id
JOIN location el ON el.location_id = s.end_location_id
"""


@bp.get("/routes")
@roles_required("admin")
def all_routes():
    f = db.Filters()
    if tid := arg_int("trip_id"):
        f.add("r.trip_id = :tid", tid=tid)
    if mode := arg_choice("mode", TRAVEL_MODES):
        f.add("r.travel_mode = :mode", mode=mode)
    rows = db.query(
        "SELECT r.*, v.total_route_score, v.recommendation_rank FROM route_option r "
        f"LEFT JOIN v6_ranked_route_recommendations v ON v.route_id = r.route_id{f.where()} "
        "ORDER BY r.trip_id, r.option_number", f.params)
    return jsonify({"routes": rows, "count": len(rows)})


@bp.get("/routes/<int:route_id>/segments")
@login_required
def list_segments(route_id):
    _route_owned(route_id)
    rows = db.query(f"{SEGMENT_SELECT} WHERE s.route_id = :r ORDER BY s.sequence_no", {"r": route_id})
    return jsonify({"segments": rows})


@bp.get("/segments")
@roles_required("admin")
def all_segments():
    f = db.Filters()
    if rid := arg_int("route_id"):
        f.add("s.route_id = :rid", rid=rid)
    if tid := arg_int("trip_id"):
        f.add("r.trip_id = :tid", tid=tid)
    if q := arg_text("q"):
        f.add("s.road_name ILIKE :q", q=like(q))
    rows = db.query(f"{SEGMENT_SELECT}{f.where()} ORDER BY s.route_id, s.sequence_no", f.params)
    return jsonify({"segments": rows, "count": len(rows)})


@bp.post("/routes/<int:route_id>/segments")
@roles_required("admin")
def create_segment(route_id):
    _route_owned(route_id)
    data = validate(json_body(), SEGMENT_FIELDS)
    if data["start_location_id"] == data["end_location_id"]:
        raise ApiError(400, "Please correct the highlighted fields.",
                       {"end_location_id": "End location must differ from the start."})
    data["route_id"] = route_id
    return created({"segment": db.insert("route_segment", data)})


@bp.put("/segments/<int:segment_id>")
@roles_required("admin")
def update_segment(segment_id):
    data = validate(json_body(), SEGMENT_FIELDS, partial=True)
    row = db.update("route_segment", "segment_id", segment_id, data)
    if not row:
        not_found("Segment")
    return jsonify({"segment": row})


@bp.delete("/segments/<int:segment_id>")
@roles_required("admin")
def delete_segment(segment_id):
    if not db.delete("route_segment", "segment_id", segment_id):
        not_found("Segment")
    return jsonify({"deleted": segment_id})
