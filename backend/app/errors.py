"""Uniform JSON error handling for the REST API (and HTML error pages)."""
from __future__ import annotations

import logging

from flask import jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)

# PostgreSQL SQLSTATE codes -> (HTTP status, user-facing message)
PG_ERRORS = {
    "23505": (409, "A record with the same unique value already exists."),
    "23503": (409, "The operation conflicts with related records (foreign key)."),
    "23514": (400, "A value is outside the allowed range (check constraint)."),
    "23502": (400, "A required value is missing."),
    "22P02": (400, "A value has an invalid format."),
    "22003": (400, "A numeric value is out of range."),
    "22001": (400, "A text value is too long."),
    "22007": (400, "A date/time value has an invalid format."),
    "22008": (400, "A date/time value is out of range."),
}

# Friendlier messages for specific named constraints.
CONSTRAINT_MESSAGES = {
    "app_user_email_key": "That email address is already registered.",
    "location_latitude_longitude_key": "A location with these coordinates already exists.",
    "user_preference_user_id_key": "This user already has a preference profile.",
    "route_option_trip_id_option_number_key": "That option number is already used for this trip.",
    "one_selected_route_per_trip": "Another route is already selected for this trip.",
    "route_segment_route_id_sequence_no_key": "That sequence number is already used for this route.",
    "saved_location_user_id_location_id_key": "This location is already in the saved list.",
    "feedback_user_id_trip_id_key": "Feedback for this trip already exists; edit it instead.",
    "trip_check": "Origin and destination must be different locations.",
    "route_segment_check": "Segment start and end must be different locations.",
}


class ApiError(Exception):
    """Raised by API code to return a controlled JSON error."""

    def __init__(self, status: int, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details or {}


def error_response(status: int, message: str, details: dict | None = None):
    body = {"error": {"status": status, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def _wants_json() -> bool:
    return request.path.startswith("/api/")


def _db_error(exc: DBAPIError):
    """Translate a PostgreSQL error into (status, message, details) without leaking internals."""
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None)
    diag = getattr(orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None) if diag else None
    status, message = PG_ERRORS.get(code, (400, "The database rejected this request."))
    if code == "23503":
        detail = (getattr(diag, "message_detail", "") or "") if diag else ""
        if "is not present" in detail:
            status, message = 400, "A referenced record does not exist."
        elif "is still referenced" in detail:
            status, message = 409, "This record is still used by other records and cannot be removed."
    if constraint in CONSTRAINT_MESSAGES:
        message = CONSTRAINT_MESSAGES[constraint]
    details = {"constraint": constraint} if constraint else None
    return status, message, details


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return error_response(exc.status, exc.message, exc.details)

    @app.errorhandler(CSRFError)
    def _csrf(exc):
        return error_response(400, "Security token missing or expired. Refresh the page and try again.")

    @app.errorhandler(OperationalError)
    def _db_down(exc):
        log.error("Database operational error: %s", exc.__class__.__name__)
        if _wants_json():
            return error_response(503, "The database is currently unavailable. Please try again shortly.")
        return render_template("error.html", status=503,
                               message="The database is currently unavailable. Please try again shortly."), 503

    @app.errorhandler(DBAPIError)
    def _dbapi(exc):
        orig = getattr(exc, "orig", None)
        state = getattr(orig, "sqlstate", "") or ""
        if state[:2] in {"22", "23"}:
            return error_response(*_db_error(exc))
        log.exception("Database error")
        return error_response(500, "A database error occurred.")

    @app.errorhandler(SQLAlchemyError)
    def _sqla(exc):
        log.exception("SQLAlchemy error")
        return error_response(500, "A database error occurred.")

    @app.errorhandler(HTTPException)
    def _http(exc: HTTPException):
        if _wants_json():
            return error_response(exc.code or 500, exc.description or exc.name)
        return render_template("error.html", status=exc.code, message=exc.description), exc.code

    @app.errorhandler(Exception)
    def _unhandled(exc):
        log.exception("Unhandled error")
        if _wants_json():
            return error_response(500, "An unexpected error occurred.")
        return render_template("error.html", status=500, message="An unexpected error occurred."), 500
