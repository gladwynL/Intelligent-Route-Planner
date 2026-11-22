"""Server-rendered HTML page shells.  Data is loaded by JavaScript via the REST API."""
from __future__ import annotations

from flask import Blueprint, g, redirect, render_template, request, url_for

from .auth import page_login_required

bp = Blueprint("pages", __name__)


def _safe_next(target: str | None) -> str | None:
    # Only allow local, absolute-path redirects (prevents open redirects).
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


@bp.get("/")
def index():
    if g.get("user"):
        return redirect(url_for("pages.planner"))
    return redirect(url_for("pages.login"))


@bp.get("/login")
def login():
    if g.get("user"):
        return redirect(url_for("pages.planner"))
    return render_template("login.html", next_url=_safe_next(request.args.get("next")))


@bp.get("/planner")
@page_login_required()
def planner():
    return render_template("planner.html", page="planner")


@bp.get("/places")
@page_login_required()
def places():
    return render_template("places.html", page="places")


@bp.get("/explorer")
@page_login_required()
def explorer():
    return render_template("explorer.html", page="explorer")


@bp.get("/conditions")
@page_login_required()
def conditions():
    return render_template("conditions.html", page="conditions")


@bp.get("/profile")
@page_login_required("admin", "user")
def profile():
    return render_template("profile.html", page="profile")


@bp.get("/admin")
@page_login_required("admin")
def admin():
    return render_template("admin.html", page="admin")
