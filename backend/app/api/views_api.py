"""/api/views — allowlisted access to the ten Phase II SQL views.

Only view names from VIEW_CATALOG can ever be queried; filters are limited to
declared columns and all values are bound parameters.  Views that expose
personal data are restricted by role and, for regular users, scoped to their
own rows.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .. import db
from ..auth import current_role, current_user_id, login_required
from ..errors import ApiError
from ..validation import TRAVEL_MODES, LOCATION_TYPES, like
from .common import export_response

bp = Blueprint("views_api", __name__, url_prefix="/api/views")

ALL_ROLES = ("admin", "user", "guest")
MEMBERS = ("admin", "user")

# filter kinds: int | text (case-insensitive equality) | bool | choice:<tuple>
VIEW_CATALOG = {
    "v1": dict(
        name="v1_trip_route_details", title="Trip route details",
        feature="Join of five tables (trip, app_user, location x2, route_option)",
        description="Every trip with its traveller, origin, destination and each alternative route.",
        columns=["trip_id", "full_name", "origin", "destination", "route_id", "travel_mode",
                 "distance_km", "estimated_duration_min", "is_selected"],
        filters={"trip_id": "int", "travel_mode": TRAVEL_MODES, "is_selected": "bool"},
        roles=MEMBERS, scope="trip"),
    "v2": dict(
        name="v2_faster_than_all_mode_averages", title="Faster than all mode averages",
        feature="Nested query with ALL and GROUP BY",
        description="Routes whose duration is below the average duration of every travel mode.",
        columns=["route_id", "trip_id", "travel_mode", "estimated_duration_min"],
        filters={"trip_id": "int", "travel_mode": TRAVEL_MODES}, roles=ALL_ROLES, scope=None),
    "v3": dict(
        name="v3_faster_than_trip_average", title="Faster than trip average",
        feature="Correlated nested query",
        description="Alternatives faster than the average duration of their own trip.",
        columns=["route_id", "trip_id", "travel_mode", "estimated_duration_min"],
        filters={"trip_id": "int", "travel_mode": TRAVEL_MODES}, roles=ALL_ROLES, scope=None),
    "v4": dict(
        name="v4_users_and_feedback", title="Users and feedback",
        feature="FULL JOIN",
        description="Every user and every feedback record, keeping users who have not left feedback.",
        columns=["user_id", "full_name", "feedback_id", "trip_id", "rating", "comments"],
        filters={"user_id": "int", "rating": "int"}, roles=MEMBERS, scope="user"),
    "v5": dict(
        name="v5_relevant_locations", title="Relevant locations",
        feature="Nested query with UNION",
        description="Locations that are saved by a user or used as a trip destination.",
        columns=["location_id", "location_name", "city", "location_type"],
        filters={"city": "text", "location_type": LOCATION_TYPES}, roles=ALL_ROLES, scope=None),
    "v6": dict(
        name="v6_ranked_route_recommendations", title="Ranked route recommendations",
        feature="CTEs, window functions, weighted scoring (45/25/15/10/5)",
        description="Explainable component scores, weighted total and rank for each alternative.",
        columns=["route_id", "trip_id", "travel_mode", "distance_km", "estimated_duration_min",
                 "time_score", "distance_score", "safety_score", "toll_score", "preference_score",
                 "total_route_score", "recommendation_rank"],
        filters={"trip_id": "int", "travel_mode": TRAVEL_MODES, "recommendation_rank": "int"},
        roles=ALL_ROLES, scope=None),
    "v7": dict(
        name="v7_condition_risk_by_route", title="Condition risk by route",
        feature="LEFT JOIN and aggregation",
        description="Number, average and maximum severity of observations for every route.",
        columns=["route_id", "trip_id", "observation_count", "average_severity", "maximum_severity"],
        filters={"trip_id": "int", "maximum_severity": "int"}, roles=ALL_ROLES, scope=None),
    "v8": dict(
        name="v8_favourite_saved_locations", title="Favourite saved locations",
        feature="Three-table join with filter",
        description="Users' favourite saved places with readable addresses.",
        columns=["user_id", "full_name", "label", "location_name", "street_address", "city"],
        filters={"user_id": "int", "city": "text"}, roles=MEMBERS, scope="user"),
    "v9": dict(
        name="v9_low_carbon_alternatives", title="Low-carbon alternatives",
        feature="Filtering (IN list, toll = 0)",
        description="No-toll walking, cycling and transit alternatives.",
        columns=["route_id", "trip_id", "travel_mode", "distance_km", "estimated_duration_min"],
        filters={"trip_id": "int", "travel_mode": ("walking", "cycling", "transit")},
        roles=ALL_ROLES, scope=None),
    "v10": dict(
        name="v10_user_feedback_summary", title="User feedback summary",
        feature="LEFT JOIN and aggregation",
        description="Feedback count, average rating and latest feedback date for every user.",
        columns=["user_id", "full_name", "feedback_count", "average_rating", "most_recent_feedback"],
        filters={"user_id": "int"}, roles=MEMBERS, scope="user"),
}


def _meta(key: str, v: dict, role: str) -> dict:
    scoped = v["scope"] is not None and role != "admin"
    return {"key": key, "name": v["name"], "title": v["title"], "feature": v["feature"],
            "description": v["description"], "columns": v["columns"],
            "filters": {k: (list(t) if isinstance(t, tuple) else t) for k, t in v["filters"].items()},
            "scoped_to_current_user": scoped}


def _get_view(key: str) -> dict:
    v = VIEW_CATALOG.get(key)
    if not v:
        raise ApiError(404, "Unknown view.")
    if current_role() not in v["roles"]:
        raise ApiError(403, "Your role cannot access this view.")
    return v


def _build_query(v: dict) -> tuple[str, dict]:
    f = db.Filters()
    # Row scoping for regular users on views that contain personal data.
    if current_role() != "admin":
        if v["scope"] == "user":
            f.add("v.user_id = :scope_uid", scope_uid=current_user_id() or -1)
        elif v["scope"] == "trip":
            f.add("v.trip_id IN (SELECT trip_id FROM trip WHERE user_id = :scope_uid)",
                  scope_uid=current_user_id() or -1)
    for i, (col, kind) in enumerate(v["filters"].items()):
        raw = request.args.get(col, "").strip()
        if not raw:
            continue
        p = f"f{i}"
        if kind == "int":
            try:
                f.add(f"v.{col} = :{p}", **{p: int(raw)})
            except ValueError:
                raise ApiError(400, f"Filter '{col}' must be a whole number.")
        elif kind == "bool":
            if raw.lower() not in ("true", "false"):
                raise ApiError(400, f"Filter '{col}' must be true or false.")
            f.add(f"v.{col} = :{p}", **{p: raw.lower() == "true"})
        elif kind == "text":
            f.add(f"v.{col} ILIKE :{p}", **{p: raw})
        else:  # tuple of allowed values
            if raw not in kind:
                raise ApiError(400, f"Filter '{col}' must be one of: {', '.join(kind)}.")
            f.add(f"v.{col} = :{p}", **{p: raw})
    q = request.args.get("q", "").strip()
    if q:
        if len(q) > 100:
            raise ApiError(400, "Search text is too long.")
        f.add("CAST(v AS text) ILIKE :kw", kw=like(q))  # keyword search across every column
    sort = request.args.get("sort", "").strip()
    order = ""
    if sort:
        if sort not in v["columns"]:
            raise ApiError(400, "Unknown sort column.")
        direction = "DESC" if request.args.get("dir", "asc").lower() == "desc" else "ASC"
        order = f" ORDER BY v.{sort} {direction} NULLS LAST"
    sql = f"SELECT {', '.join('v.' + c for c in v['columns'])} FROM {v['name']} AS v{f.where()}{order} LIMIT 1000"
    return sql, f.params


@bp.get("")
@login_required
def catalog():
    role = current_role()
    views = [_meta(k, v, role) for k, v in VIEW_CATALOG.items() if role in v["roles"]]
    return jsonify({"views": views, "total_views": len(VIEW_CATALOG)})


@bp.get("/<key>")
@login_required
def run_view(key):
    v = _get_view(key)
    sql, params = _build_query(v)
    rows = db.query(sql, params)
    definition = db.query_one("SELECT pg_get_viewdef(CAST(:n AS regclass), true) AS def", {"n": v["name"]})
    return jsonify({"view": _meta(key, v, current_role()), "rows": rows, "count": len(rows),
                    "sql": f"CREATE VIEW {v['name']} AS\n{definition['def']}"})


@bp.get("/<key>/export")
@login_required
def export_view(key):
    v = _get_view(key)
    sql, params = _build_query(v)
    rows = db.query(sql, params)
    subtitle = f"View {key[1:]} - {v['name']} ({v['feature']})"
    return export_response(v["name"], f"View {key[1:]}: {v['title']}", v["columns"], rows, subtitle)
