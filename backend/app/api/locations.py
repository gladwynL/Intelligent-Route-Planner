"""/api/locations — shared geographic locations (origins, destinations, places)."""
from __future__ import annotations

from flask import Blueprint, jsonify

from .. import db
from ..auth import login_required, roles_required
from ..validation import LOCATION_TYPES, Field, arg_choice, arg_text, json_body, like, validate
from .common import created, not_found

bp = Blueprint("locations", __name__, url_prefix="/api/locations")

FIELDS = [
    Field("location_name", "str", required=True, max_len=120, label="Location name"),
    Field("street_address", "str", required=True, max_len=180, label="Street address"),
    Field("city", "str", required=True, max_len=80),
    Field("latitude", "num", required=True, min=-90, max=90, places=6),
    Field("longitude", "num", required=True, min=-180, max=180, places=6),
    Field("location_type", "str", required=True, choices=LOCATION_TYPES, label="Location type"),
]


@bp.get("")
@login_required
def list_locations():
    f = db.Filters()
    if q := arg_text("q"):
        f.add("(location_name ILIKE :q OR street_address ILIKE :q OR city ILIKE :q)", q=like(q))
    if city := arg_text("city"):
        f.add("city ILIKE :city", city=city)
    if t := arg_choice("type", LOCATION_TYPES):
        f.add("location_type = :t", t=t)
    rows = db.query(
        "SELECT l.*, "
        " (SELECT COUNT(*) FROM trip t WHERE t.origin_location_id = l.location_id "
        "     OR t.destination_location_id = l.location_id) AS trip_count "
        f"FROM location l{f.where()} ORDER BY location_name", f.params)
    return jsonify({"locations": rows, "count": len(rows)})


@bp.get("/<int:location_id>")
@login_required
def get_location(location_id):
    row = db.query_one("SELECT * FROM location WHERE location_id = :id", {"id": location_id})
    if not row:
        not_found("Location")
    return jsonify({"location": row})


@bp.post("")
@roles_required("admin", "user")
def create_location():
    data = validate(json_body(), FIELDS)
    row = db.insert("location", data)
    return created({"location": row})


@bp.put("/<int:location_id>")
@roles_required("admin")
def update_location(location_id):
    data = validate(json_body(), FIELDS, partial=True)
    row = db.update("location", "location_id", location_id, data)
    if not row:
        not_found("Location")
    return jsonify({"location": row})


@bp.delete("/<int:location_id>")
@roles_required("admin")
def delete_location(location_id):
    if not db.delete("location", "location_id", location_id):
        not_found("Location")
    return jsonify({"deleted": location_id})
