"""/api/observations — traffic, weather, closure and construction observations."""
from __future__ import annotations

from flask import Blueprint, jsonify

from .. import db
from ..auth import login_required, roles_required
from ..validation import (CONDITION_TYPES, Field, arg_choice, arg_date, arg_int, arg_text,
                          json_body, like, validate)
from .common import created, export_response, not_found

bp = Blueprint("observations", __name__, url_prefix="/api")

FIELDS = [
    Field("segment_id", "int", required=True, min=1, label="Segment"),
    Field("observed_at", "datetime", required=True, label="Observed at"),
    Field("condition_type", "str", required=True, choices=CONDITION_TYPES, label="Condition type"),
    Field("severity", "int", required=True, min=0, max=5),
    Field("description", "str", required=True, max_len=200),
    Field("source_name", "str", required=True, max_len=80, label="Source"),
]

SELECT = """
SELECT c.observation_id, c.segment_id, c.observed_at, c.condition_type, c.severity, c.description,
       c.source_name, s.road_name, s.route_id, r.trip_id, r.travel_mode
FROM condition_observation c
JOIN route_segment s ON s.segment_id = c.segment_id
JOIN route_option r ON r.route_id = s.route_id
"""


def _filters() -> db.Filters:
    f = db.Filters()
    if t := arg_choice("type", CONDITION_TYPES):
        f.add("c.condition_type = :ctype", ctype=t)
    sev = arg_int("min_severity", min_value=0)
    if sev is not None:
        f.add("c.severity >= :sev", sev=sev)
    if src := arg_text("source"):
        f.add("c.source_name ILIKE :src", src=like(src))
    if rid := arg_int("route_id"):
        f.add("s.route_id = :rid", rid=rid)
    if tid := arg_int("trip_id"):
        f.add("r.trip_id = :tid", tid=tid)
    if q := arg_text("q"):
        f.add("(c.description ILIKE :q OR s.road_name ILIKE :q OR c.source_name ILIKE :q)", q=like(q))
    if start := arg_date("from"):
        f.add("c.observed_at >= CAST(:ofrom AS timestamp)", ofrom=start)
    if end := arg_date("to"):
        f.add("c.observed_at < CAST(:oto AS timestamp) + INTERVAL '1 day'", oto=end)
    return f


@bp.get("/observations")
@login_required
def list_observations():
    f = _filters()
    rows = db.query(f"{SELECT}{f.where()} ORDER BY c.observed_at DESC, c.observation_id DESC LIMIT 500",
                    f.params)
    return jsonify({"observations": rows, "count": len(rows)})


@bp.get("/export/observations")
@login_required
def export_observations():
    f = _filters()
    rows = db.query(f"{SELECT}{f.where()} ORDER BY c.observed_at DESC", f.params)
    cols = ["observation_id", "observed_at", "condition_type", "severity", "description",
            "source_name", "road_name", "route_id", "trip_id"]
    return export_response("condition-observations", "Condition observations", cols, rows)


@bp.post("/observations")
@roles_required("admin")
def create_observation():
    data = validate(json_body(), FIELDS)
    return created({"observation": db.insert("condition_observation", data)})


@bp.put("/observations/<int:observation_id>")
@roles_required("admin")
def update_observation(observation_id):
    data = validate(json_body(), FIELDS, partial=True)
    row = db.update("condition_observation", "observation_id", observation_id, data)
    if not row:
        not_found("Observation")
    return jsonify({"observation": row})


@bp.delete("/observations/<int:observation_id>")
@roles_required("admin")
def delete_observation(observation_id):
    if not db.delete("condition_observation", "observation_id", observation_id):
        not_found("Observation")
    return jsonify({"deleted": observation_id})
