"""Server-side input validation.

Each endpoint declares a list of ``Field`` objects; ``validate`` returns a
clean dict of typed values or raises ``ApiError(400)`` with a per-field
``details`` map.  This runs independently of the browser's JavaScript
validation and before anything reaches PostgreSQL (whose CHECK constraints
remain the final safety net).
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from flask import request

from .errors import ApiError

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

TRAVEL_MODES = ("driving", "cycling", "walking", "transit")
ROLES = ("admin", "user", "guest")
LOCATION_TYPES = ("home", "work", "school", "public", "other")
TRIP_STATUSES = ("planned", "completed", "cancelled")
CONDITION_TYPES = ("traffic", "weather", "closure", "construction")


class Field:
    def __init__(self, name: str, kind: str = "str", *, required: bool = False,
                 max_len: int | None = None, min_len: int | None = None,
                 min: float | None = None, max: float | None = None,
                 choices: Iterable[str] | None = None, nullable: bool = False,
                 label: str | None = None, places: int | None = None):
        self.name = name
        self.kind = kind
        self.required = required
        self.max_len = max_len
        self.min_len = min_len
        self.min = min
        self.max = max
        self.choices = tuple(choices) if choices else None
        self.nullable = nullable
        self.label = label or name.replace("_", " ").capitalize()
        self.places = places

    def convert(self, value: Any) -> Any:
        k = self.kind
        if k in ("str", "email", "text"):
            if not isinstance(value, str):
                raise ValueError("must be text")
            value = value.strip()
            if self.required and not value:
                raise ValueError("is required")
            if self.min_len and len(value) < self.min_len:
                raise ValueError(f"must be at least {self.min_len} characters")
            if self.max_len and len(value) > self.max_len:
                raise ValueError(f"must be at most {self.max_len} characters")
            if k == "email" and not EMAIL_RE.match(value):
                raise ValueError("must be a valid email address")
            if k == "email":
                value = value.lower()
            if self.choices and value not in self.choices:
                raise ValueError(f"must be one of: {', '.join(self.choices)}")
            return value
        if k == "int":
            if isinstance(value, bool):
                raise ValueError("must be a whole number")
            try:
                if isinstance(value, float) and not value.is_integer():
                    raise ValueError
                value = int(str(value).strip())
            except (TypeError, ValueError):
                raise ValueError("must be a whole number")
            self._range(value)
            return value
        if k == "num":
            if isinstance(value, bool):
                raise ValueError("must be a number")
            try:
                value = Decimal(str(value).strip())
            except (InvalidOperation, ValueError):
                raise ValueError("must be a number")
            if not value.is_finite():
                raise ValueError("must be a number")
            self._range(value)
            if self.places is not None:
                value = value.quantize(Decimal(1).scaleb(-self.places))
            return value
        if k == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in ("true", "false", "1", "0", "yes", "no", "on", "off"):
                return value.lower() in ("true", "1", "yes", "on")
            if value in (0, 1):
                return bool(value)
            raise ValueError("must be true or false")
        if k == "datetime":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("must be a date and time")
            try:
                dt = datetime.fromisoformat(value.strip().replace("Z", ""))
            except ValueError:
                raise ValueError("must be a date and time (YYYY-MM-DDTHH:MM)")
            if not (2000 <= dt.year <= 2100):
                raise ValueError("must be between the years 2000 and 2100")
            return dt.replace(tzinfo=None)
        raise ValueError("has an unsupported type")  # pragma: no cover

    def _range(self, value):
        if self.min is not None and value < self.min:
            raise ValueError(f"must be at least {self.min}")
        if self.max is not None and value > self.max:
            raise ValueError(f"must be at most {self.max}")


def validate(payload: dict | None, fields: list[Field], *, partial: bool = False) -> dict:
    """Validate ``payload`` against ``fields``.

    partial=True (PUT) only validates keys that are present and does not
    enforce ``required``.  Unknown keys are ignored.
    """
    if payload is None or not isinstance(payload, dict):
        raise ApiError(400, "Request body must be a JSON object.")
    clean: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for f in fields:
        present = f.name in payload
        value = payload.get(f.name)
        if not present or value is None or (isinstance(value, str) and value.strip() == ""):
            if f.required and not partial:
                errors[f.name] = f"{f.label} is required."
            elif present and f.nullable:
                clean[f.name] = None
            elif present and f.required and partial:
                errors[f.name] = f"{f.label} cannot be empty."
            continue
        try:
            clean[f.name] = f.convert(value)
        except ValueError as exc:
            errors[f.name] = f"{f.label} {exc}."
    if errors:
        raise ApiError(400, "Please correct the highlighted fields.", errors)
    if partial and not clean:
        raise ApiError(400, "No updatable fields were provided.")
    return clean


def json_body() -> dict:
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        raise ApiError(400, "Request body must be valid JSON (Content-Type: application/json).")
    return data


def arg_int(name: str, *, min_value: int | None = 1) -> int | None:
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(400, f"Query parameter '{name}' must be a whole number.")
    if min_value is not None and value < min_value:
        raise ApiError(400, f"Query parameter '{name}' must be at least {min_value}.")
    return value


def arg_choice(name: str, choices: Iterable[str]) -> str | None:
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    choices = tuple(choices)
    if raw not in choices:
        raise ApiError(400, f"Query parameter '{name}' must be one of: {', '.join(choices)}.")
    return raw


def arg_date(name: str) -> str | None:
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).isoformat()
    except ValueError:
        raise ApiError(400, f"Query parameter '{name}' must be a date (YYYY-MM-DD).")


def arg_text(name: str, max_len: int = 100) -> str | None:
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    if len(raw) > max_len:
        raise ApiError(400, f"Query parameter '{name}' is too long.")
    return raw


def like(term: str) -> str:
    """Escape LIKE wildcards in user input and wrap for a contains-search."""
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
