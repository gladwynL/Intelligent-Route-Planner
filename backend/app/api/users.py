"""/api/users — administrator management of accounts and roles."""
from __future__ import annotations

from flask import Blueprint, jsonify
from werkzeug.security import generate_password_hash

from .. import db
from ..auth import current_user_id, roles_required
from ..errors import ApiError
from ..validation import ROLES, Field, arg_choice, arg_text, json_body, like, validate
from .common import created, not_found

bp = Blueprint("users", __name__, url_prefix="/api/users")

SAFE_COLUMNS = "user_id, full_name, email, user_role, created_at"

CREATE_FIELDS = [
    Field("full_name", "str", required=True, max_len=100, label="Full name"),
    Field("email", "email", required=True, max_len=150),
    Field("password", "str", required=True, min_len=8, max_len=128),
    Field("user_role", "str", required=True, choices=ROLES, label="Role"),
]
UPDATE_FIELDS = [
    Field("full_name", "str", required=True, max_len=100, label="Full name"),
    Field("email", "email", required=True, max_len=150),
    Field("password", "str", min_len=8, max_len=128),
    Field("user_role", "str", required=True, choices=ROLES, label="Role"),
]


@bp.get("")
@roles_required("admin")
def list_users():
    f = db.Filters()
    if q := arg_text("q"):
        f.add("(u.full_name ILIKE :q OR u.email ILIKE :q)", q=like(q))
    if role := arg_choice("role", ROLES):
        f.add("u.user_role = :role", role=role)
    rows = db.query(
        "SELECT u.user_id, u.full_name, u.email, u.user_role, u.created_at, "
        " (SELECT COUNT(*) FROM trip t WHERE t.user_id = u.user_id) AS trip_count, "
        " p.preferred_mode "
        "FROM app_user u LEFT JOIN user_preference p ON p.user_id = u.user_id"
        f"{f.where()} ORDER BY u.user_id", f.params)
    return jsonify({"users": rows, "count": len(rows)})


@bp.get("/<int:user_id>")
@roles_required("admin")
def get_user(user_id):
    row = db.query_one(f"SELECT {SAFE_COLUMNS} FROM app_user WHERE user_id = :id", {"id": user_id})
    if not row:
        not_found("User")
    return jsonify({"user": row})


@bp.post("")
@roles_required("admin")
def create_user():
    data = validate(json_body(), CREATE_FIELDS)
    data["password_hash"] = generate_password_hash(data.pop("password"))
    with db.transaction() as conn:
        user = db.insert("app_user", data, SAFE_COLUMNS, conn)
        # Every account gets a default preference profile so View 6 can score its trips.
        db.insert("user_preference", {"user_id": user["user_id"], "preferred_mode": "driving"},
                  "preference_id", conn)
    return created({"user": user})


@bp.put("/<int:user_id>")
@roles_required("admin")
def update_user(user_id):
    data = validate(json_body(), UPDATE_FIELDS, partial=True)
    if user_id == current_user_id() and data.get("user_role", "admin") != "admin":
        raise ApiError(400, "You cannot remove your own administrator role.")
    if "password" in data:
        data["password_hash"] = generate_password_hash(data.pop("password"))
    sets = ", ".join(f"{c} = :{c}" for c in data)
    rows = db.execute(f"UPDATE app_user SET {sets} WHERE user_id = :_pk RETURNING {SAFE_COLUMNS}",
                      {**data, "_pk": user_id})
    if not rows:
        not_found("User")
    return jsonify({"user": rows[0]})


@bp.delete("/<int:user_id>")
@roles_required("admin")
def delete_user(user_id):
    if user_id == current_user_id():
        raise ApiError(400, "You cannot delete the account you are signed in with.")
    if not db.delete("app_user", "user_id", user_id):
        not_found("User")
    return jsonify({"deleted": user_id})
