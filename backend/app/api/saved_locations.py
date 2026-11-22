"""/api/saved-locations — a user's labelled and favourite places."""
from __future__ import annotations

from flask import Blueprint, jsonify

from .. import db
from ..auth import current_user_id, ensure_owner, is_admin, login_required, roles_required
from ..validation import Field, arg_int, arg_text, json_body, like, validate
from .common import created, not_found

bp = Blueprint("saved_locations", __name__, url_prefix="/api/saved-locations")

FIELDS = [
    Field("location_id", "int", required=True, min=1, label="Location"),
    Field("label", "str", required=True, max_len=50),
    Field("is_favourite", "bool", label="Favourite"),
]

SELECT = (
    "SELECT sl.saved_location_id, sl.user_id, u.full_name, sl.location_id, sl.label, sl.is_favourite, "
    " sl.saved_at, l.location_name, l.street_address, l.city, l.latitude, l.longitude "
    "FROM saved_location sl JOIN location l ON l.location_id = sl.location_id "
    "JOIN app_user u ON u.user_id = sl.user_id"
)


def _owned(saved_id: int) -> dict:
    row = db.query_one("SELECT * FROM saved_location WHERE saved_location_id = :id", {"id": saved_id})
    if not row:
        not_found("Saved location")
    ensure_owner(row["user_id"])
    return row


@bp.get("")
@login_required
def list_saved():
    f = db.Filters()
    if is_admin():
        if uid := arg_int("user_id"):
            f.add("sl.user_id = :uid", uid=uid)
    else:
        f.add("sl.user_id = :uid", uid=current_user_id() or -1)
    if q := arg_text("q"):
        f.add("(sl.label ILIKE :q OR l.location_name ILIKE :q OR l.city ILIKE :q)", q=like(q))
    rows = db.query(f"{SELECT}{f.where()} ORDER BY sl.is_favourite DESC, sl.label", f.params)
    return jsonify({"saved_locations": rows, "count": len(rows)})


@bp.post("")
@roles_required("admin", "user")
def create_saved():
    fields = FIELDS + ([Field("user_id", "int", min=1, label="User")] if is_admin() else [])
    data = validate(json_body(), fields)
    data["user_id"] = data.get("user_id") or current_user_id()
    data.setdefault("is_favourite", False)
    row = db.insert("saved_location", data)
    return created({"saved_location": row})


@bp.put("/<int:saved_id>")
@roles_required("admin", "user")
def update_saved(saved_id):
    _owned(saved_id)
    data = validate(json_body(), FIELDS, partial=True)
    row = db.update("saved_location", "saved_location_id", saved_id, data)
    return jsonify({"saved_location": row})


@bp.delete("/<int:saved_id>")
@roles_required("admin", "user")
def delete_saved(saved_id):
    _owned(saved_id)
    db.delete("saved_location", "saved_location_id", saved_id)
    return jsonify({"deleted": saved_id})
