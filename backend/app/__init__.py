"""Intelligent Route Planning System — Flask application factory."""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from flask import Flask
from flask.json.provider import DefaultJSONProvider
from flask_wtf.csrf import CSRFProtect

from . import auth, db
from .config import ROOT_DIR, Config, finalize
from .errors import register_error_handlers

csrf = CSRFProtect()


class AppJSONProvider(DefaultJSONProvider):
    """Serialise PostgreSQL NUMERIC and TIMESTAMP values cleanly."""
    sort_keys = False

    @staticmethod
    def default(o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, datetime):
            return o.isoformat(timespec="minutes")
        if isinstance(o, date):
            return o.isoformat()
        return DefaultJSONProvider.default(o)


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(ROOT_DIR / "frontend" / "templates"),
        static_folder=str(ROOT_DIR / "frontend" / "static"),
        static_url_path="/static",
    )
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    finalize(app.config)
    app.json = AppJSONProvider(app)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db.init_engine(app)
    csrf.init_app(app)
    register_error_handlers(app)
    app.before_request(auth.load_current_user)

    from .api import analytics, feedback, locations, observations, preferences, saved_locations, trips, \
        users, views_api, weather
    from . import pages

    for bp in (auth.bp, pages.bp, locations.bp, users.bp, preferences.bp, saved_locations.bp,
               feedback.bp, trips.bp, observations.bp, weather.bp, views_api.bp, analytics.bp):
        app.register_blueprint(bp)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if resp.mimetype == "application/json":
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.context_processor
    def inject_user():
        from flask import g
        return {"current_user": g.get("user")}

    return app
