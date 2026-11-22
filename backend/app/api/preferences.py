"""/api/preferences — one routing-preference profile per user."""
from __future__ import annotations

from flask import Blueprint, jsonify

from .. import db
from ..auth import current_user_id, login_required, roles_required
from ..errors import ApiError
from ..validation import TRAVEL_MODES, Field, json_body, validate
from .common import created, not_found

bp = Blueprint("preferences", __name__, url_prefix="/api/preferences")

FIELDS = [
    Field("preferred_mode", "str", required=True, choices=TRAVEL_MODES, label="Preferred mode"),
    Field("max_walking_km", "num", min=0, max=999.9, places=1, label="Maximum walking distance"),
    Field("avoid_tolls", "bool", label="Avoid tolls"),
    Field("avoid_highways", "bool", label="Avoid highways"),
    Field("prioritize_safety", "bool", label="Prioritise safety"),
]


@bp.get("/me")
@login_required
def my_preference():
    uid = current_user_id()
    row = db.query_one("SELECT * FROM user_preference WHERE user_id = :u", {"u": uid}) if uid else None
    return jsonify({"preference": row})


@bp.put("/me")
@roles_required("admin", "user")
def upsert_my_preference():
    data = validate(json_body(), FIELDS)
    data["user_id"] = current_user_id()
    data.setdefault("max_walking_km", 2.0)
    data.setdefault("avoid_tolls", False)
    data.setdefault("avoid_highways", False)
    data.setdefault("prioritize_safety", True)
    row = db.execute(
        "INSERT INTO user_preference (user_id, preferred_mode, max_walking_km, avoid_tolls, "
        " avoid_highways, prioritize_safety) "
        "VALUES (:user_id, :preferred_mode, :max_walking_km, :avoid_tolls, :avoid_highways, :prioritize_safety) "
        "ON CONFLICT (user_id) DO UPDATE SET preferred_mode = EXCLUDED.preferred_mode, "
        " max_walking_km = EXCLUDED.max_walking_km, avoid_tolls = EXCLUDED.avoid_tolls, "
        " avoid_highways = EXCLUDED.avoid_highways, prioritize_safety = EXCLUDED.prioritize_safety "
        "RETURNING *", data)[0]
    return jsonify({"preference": row})


# ---- administrator CRUD over every profile ---------------------------------

@bp.get("")
@roles_required("admin")
def list_preferences():
    rows = db.query(
        "SELECT p.*, u.full_name FROM user_preference p JOIN app_user u ON u.user_id = p.user_id "
        "ORDER BY p.preference_id")
    return jsonify({"preferences": rows, "count": len(rows)})


@bp.post("")
@roles_required("admin")
def create_preference():
    data = validate(json_body(), [Field("user_id", "int", required=True, min=1, label="User")] + FIELDS)
    row = db.insert("user_preference", data)
    return created({"preference": row})


@bp.put("/<int:preference_id>")
@roles_required("admin")
def update_preference(preference_id):
    data = validate(json_body(), FIELDS, partial=True)
    row = db.update("user_preference", "preference_id", preference_id, data)
    if not row:
        not_found("Preference")
    return jsonify({"preference": row})


@bp.delete("/<int:preference_id>")
@roles_required("admin")
def delete_preference(preference_id):
    if not db.delete("user_preference", "preference_id", preference_id):
        not_found("Preference")
    return jsonify({"deleted": preference_id})
