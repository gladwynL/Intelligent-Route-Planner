"""Application configuration loaded from environment variables (.env)."""
from __future__ import annotations

import os
import secrets
import warnings
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or ""
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://route_planner:route_planner_dev@localhost:5433/route_planner",
    )

    # Time zone used for PostgreSQL session timestamps (project area: Durham Region, Ontario)
    DB_TIMEZONE = os.getenv("DB_TIMEZONE", "America/Toronto")

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE")
    SESSION_COOKIE_NAME = "route_planner_session"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # CSRF (Flask-WTF): tokens are bound to the session; sent in the X-CSRFToken header.
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_SSL_STRICT = False

    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1 MB request bodies are plenty for this API

    # External services
    OPEN_METEO_URL = os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
    OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org")
    ENABLE_OSRM = _flag("ENABLE_OSRM", "1")
    EXTERNAL_TIMEOUT_SECONDS = float(os.getenv("EXTERNAL_TIMEOUT_SECONDS", "8"))

    TESTING = False


def finalize(config: dict) -> None:
    """Fill in a throwaway secret key in development if none was configured."""
    key = config.get("SECRET_KEY") or ""
    if not key or key.startswith("change-me"):
        warnings.warn("SECRET_KEY is not set; using a temporary random key (sessions reset on restart).")
        config["SECRET_KEY"] = secrets.token_hex(32)
