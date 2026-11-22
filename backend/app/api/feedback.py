"""/api/feedback — ratings and comments about trip route results."""
from __future__ import annotations

from flask import Blueprint, jsonify

from .. import db
from ..auth import current_user_id, ensure_owner, is_admin, login_required, roles_required
from ..errors import ApiError
from ..validation import Field, arg_int, arg_text, json_body, like, validate
from .common import created, not_found

bp = Blueprint("feedback", __name__, url_prefix="/api/feedback")

FIELDS = [
    Field("trip_id", "int", required=True, min=1, label="Trip"),
    Field("rating", "int", required=True, min=1, max=5),
    Field("comments", "str", max_len=500, nullable=True),
]

SELECT = (
    "SELECT f.feedback_id, f.user_id, u.full_name, f.trip_id, f.rating, f.comments, f.submitted_at, "
    " o.location_name AS origin, d.location_name AS destination "
    "FROM feedback f JOIN app_user u ON u.user_id = f.user_id "
    "JOIN trip t ON t.trip_id = f.trip_id "
    "JOIN location o ON o.location_id = t.origin_location_id "
    "JOIN location d ON d.location_id = t.destination_location_id"
)


def _owned(feedback_id: int) -> dict:
    row = db.query_one("SELECT * FROM feedback WHERE feedback_id = :id", {"id": feedback_id})
    if not row:
        not_found("Feedback")
    ensure_owner(row["user_id"])
    return row


@bp.get("")
@login_required
def list_feedback():
    f = db.Filters()
    if is_admin():
        if uid := arg_int("user_id"):
            f.add("f.user_id = :uid", uid=uid)
    else:
        f.add("f.user_id = :uid", uid=current_user_id() or -1)
    if trip := arg_int("trip_id"):
        f.add("f.trip_id = :trip", trip=trip)
    if rating := arg_int("rating"):
        f.add("f.rating = :rating", rating=rating)
    if q := arg_text("q"):
        f.add("f.comments ILIKE :q", q=like(q))
    rows = db.query(f"{SELECT}{f.where()} ORDER BY f.submitted_at DESC", f.params)
    return jsonify({"feedback": rows, "count": len(rows)})


@bp.post("")
@roles_required("admin", "user")
def create_feedback():
    data = validate(json_body(), FIELDS)
    trip = db.query_one("SELECT user_id FROM trip WHERE trip_id = :id", {"id": data["trip_id"]})
    if not trip:
        raise ApiError(400, "Please correct the highlighted fields.", {"trip_id": "Trip does not exist."})
    if not is_admin() and trip["user_id"] != current_user_id():
        raise ApiError(403, "You can only leave feedback on your own trips.")
    data["user_id"] = current_user_id()
    row = db.insert("feedback", data)
    return created({"feedback": row})


@bp.put("/<int:feedback_id>")
@roles_required("admin", "user")
def update_feedback(feedback_id):
    _owned(feedback_id)
    fields = [f for f in FIELDS if f.name != "trip_id"]
    data = validate(json_body(), fields, partial=True)
    row = db.update("feedback", "feedback_id", feedback_id, data)
    return jsonify({"feedback": row})


@bp.delete("/<int:feedback_id>")
@roles_required("admin", "user")
def delete_feedback(feedback_id):
    _owned(feedback_id)
    db.delete("feedback", "feedback_id", feedback_id)
    return jsonify({"deleted": feedback_id})
