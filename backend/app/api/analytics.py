"""/api/analytics and /api/health — aggregate SQL for charts and a status check."""
from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy.exc import SQLAlchemyError

from .. import db
from ..auth import login_required

bp = Blueprint("analytics", __name__, url_prefix="/api")

TABLES = ("app_user", "location", "user_preference", "trip", "route_option", "route_segment",
          "condition_observation", "saved_location", "feedback")


@bp.get("/analytics/summary")
@login_required
def summary():
    counts = db.query_one(
        "SELECT " + ", ".join(f"(SELECT COUNT(*) FROM {t}) AS {t}" for t in TABLES))
    by_mode = db.query(
        "SELECT travel_mode, COUNT(*) AS routes, ROUND(AVG(estimated_duration_min), 1) AS avg_duration_min, "
        " ROUND(AVG(distance_km), 2) AS avg_distance_km "
        "FROM route_option GROUP BY travel_mode ORDER BY travel_mode")
    severity = db.query(
        "SELECT s.severity, COALESCE(COUNT(c.observation_id), 0) AS observations "
        "FROM generate_series(0, 5) AS s(severity) "
        "LEFT JOIN condition_observation c ON c.severity = s.severity "
        "GROUP BY s.severity ORDER BY s.severity")
    by_type = db.query(
        "SELECT condition_type, COUNT(*) AS observations, ROUND(AVG(severity), 2) AS avg_severity "
        "FROM condition_observation GROUP BY condition_type ORDER BY condition_type")
    scores = db.query(
        "SELECT trip_id, route_id, travel_mode, total_route_score, recommendation_rank "
        "FROM v6_ranked_route_recommendations ORDER BY trip_id, recommendation_rank, route_id")
    ratings = db.query(
        "SELECT r.rating, COUNT(f.feedback_id) AS count FROM generate_series(1, 5) AS r(rating) "
        "LEFT JOIN feedback f ON f.rating = r.rating GROUP BY r.rating ORDER BY r.rating")
    weather_trend = db.query(
        "SELECT CAST(observed_at AS date) AS day, COUNT(*) AS observations, ROUND(AVG(severity), 2) AS avg_severity "
        "FROM condition_observation WHERE condition_type = 'weather' "
        "GROUP BY CAST(observed_at AS date) ORDER BY day")
    selected_vs_recommended = db.query_one(
        "SELECT COUNT(*) FILTER (WHERE r.is_selected AND v.recommendation_rank = 1) AS matches, "
        " COUNT(*) FILTER (WHERE r.is_selected) AS selected_total "
        "FROM route_option r JOIN v6_ranked_route_recommendations v ON v.route_id = r.route_id")
    return jsonify({
        "table_counts": counts, "duration_by_mode": by_mode, "severity_distribution": severity,
        "conditions_by_type": by_type, "route_scores": scores, "rating_distribution": ratings,
        "weather_trend": weather_trend, "selected_vs_recommended": selected_vs_recommended,
    })


@bp.get("/health")
def health():
    """Public status endpoint: verifies PostgreSQL connectivity and the ten views."""
    try:
        info = db.query_one(
            "SELECT current_setting('server_version') AS server_version, current_database() AS database_name, "
            " (SELECT COUNT(*) FROM information_schema.views WHERE table_schema = 'public' "
            "   AND table_name ~ '^v[0-9]+_') AS view_count, "
            " (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' "
            "   AND table_type = 'BASE TABLE' AND table_name = ANY(:tables)) AS table_count",
            {"tables": list(TABLES)})
    except SQLAlchemyError:
        return jsonify({"status": "degraded", "database": "unavailable"}), 503
    return jsonify({"status": "ok", "database": "connected", **info})
