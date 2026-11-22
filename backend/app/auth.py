"""Session authentication and role-based authorisation.

* Passwords are verified with Werkzeug's salted scrypt hashes stored in
  ``app_user.password_hash``.
* The session stores only the user id (or a guest marker); the user's role
  is re-read from PostgreSQL on every request, so role changes and account
  deletions take effect immediately.
* Authorisation is enforced on the server with the decorators below; the UI
  merely hides what a role cannot use.
"""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, g, jsonify, redirect, request, session, url_for
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash

from . import db
from .errors import ApiError
from .validation import Field, json_body, validate

bp = Blueprint("auth_api", __name__, url_prefix="/api/auth")

# Used to keep login timing similar whether or not the email exists.
_DUMMY_HASH = ("scrypt:32768:8:1$AAAAAAAAAAAAAAAA$"
               "0000000000000000000000000000000000000000000000000000000000000000"
               "0000000000000000000000000000000000000000000000000000000000000000")

ANON_GUEST = {"user_id": None, "full_name": "Guest visitor", "email": None, "user_role": "guest"}


def load_current_user():
    """before_request hook: populate g.user from the session."""
    g.user = None
    if session.get("guest"):
        g.user = dict(ANON_GUEST)
        return
    uid = session.get("user_id")
    if uid is None:
        return
    row = db.query_one(
        "SELECT user_id, full_name, email, user_role FROM app_user WHERE user_id = :id", {"id": uid})
    if row is None:  # account deleted while logged in
        session.clear()
        return
    g.user = row


def current_role() -> str | None:
    return g.user["user_role"] if g.get("user") else None


def current_user_id() -> int | None:
    return g.user["user_id"] if g.get("user") else None


def is_admin() -> bool:
    return current_role() == "admin"


def login_required(fn):
    """Any authenticated session, including guests."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.get("user"):
            raise ApiError(401, "Please sign in to continue.")
        return fn(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    """Restrict an API endpoint to the given roles (401 if anonymous, 403 otherwise)."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not g.get("user"):
                raise ApiError(401, "Please sign in to continue.")
            if g.user["user_role"] not in roles:
                raise ApiError(403, "Your role does not have permission for this action.")
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def page_login_required(*roles):
    """Decorator for HTML pages: redirect to /login, or 403 for the wrong role."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not g.get("user"):
                return redirect(url_for("pages.login", next=request.path))
            if roles and g.user["user_role"] not in roles:
                from flask import abort
                abort(403, "This page is restricted to administrators.")
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def ensure_owner(owner_id: int | None):
    """Admins may access everything; other roles only their own records."""
    if is_admin():
        return
    if owner_id is None or owner_id != current_user_id():
        # 404 rather than 403 so record existence is not disclosed to other users.
        raise ApiError(404, "Record not found.")


def public_user(row: dict) -> dict:
    return {k: row[k] for k in ("user_id", "full_name", "email", "user_role") if k in row}


@bp.get("/csrf")
def csrf_token():
    return jsonify({"csrf_token": generate_csrf()})


@bp.post("/login")
def login():
    data = validate(json_body(), [
        Field("email", "email", required=True, max_len=150),
        Field("password", "str", required=True, max_len=200),
    ])
    row = db.query_one(
        "SELECT user_id, full_name, email, user_role, password_hash FROM app_user WHERE email = :email",
        {"email": data["email"]})
    ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, data["password"])
    if not row or not ok:
        raise ApiError(401, "Invalid email or password.")
    session.clear()  # prevent session fixation
    session.permanent = True
    session["user_id"] = row["user_id"]
    return jsonify({"user": public_user(row), "redirect": url_for("pages.planner")})


@bp.post("/guest")
def guest_login():
    session.clear()
    session.permanent = True
    session["guest"] = True
    return jsonify({"user": ANON_GUEST, "redirect": url_for("pages.explorer")})


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True, "redirect": url_for("pages.login")})


@bp.get("/me")
def me():
    if not g.get("user"):
        return jsonify({"authenticated": False, "user": None})
    return jsonify({"authenticated": True, "user": public_user(g.user)})
