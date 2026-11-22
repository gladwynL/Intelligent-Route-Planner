"""Database-level tests run directly against PostgreSQL (no Flask)."""
from __future__ import annotations

from decimal import Decimal

import psycopg
import pytest

TABLES = ["app_user", "location", "user_preference", "trip", "route_option", "route_segment",
          "condition_observation", "saved_location", "feedback"]

# Expected row counts of each view on the seeded Phase II data (matches the Phase II appendix).
EXPECTED_VIEW_ROWS = {
    "v1_trip_route_details": 12,
    "v2_faster_than_all_mode_averages": 4,
    "v3_faster_than_trip_average": 6,
    "v4_users_and_feedback": 8,
    "v5_relevant_locations": 8,
    "v6_ranked_route_recommendations": 12,
    "v7_condition_risk_by_route": 12,
    "v8_favourite_saved_locations": 4,
    "v9_low_carbon_alternatives": 7,
    "v10_user_feedback_summary": 6,
}


def scalar(conn, sql, params=None):
    return conn.execute(sql, params).fetchone()[0]


def test_postgresql_server(pg):
    version = scalar(pg, "SHOW server_version_num")
    assert int(version) >= 140000, "PostgreSQL 14+ required"


@pytest.mark.parametrize("table", TABLES)
def test_table_exists_with_at_least_six_rows(pg, table):
    assert scalar(pg, "SELECT to_regclass(%s) IS NOT NULL", (table,))
    assert scalar(pg, f"SELECT COUNT(*) FROM {table}") >= 6


@pytest.mark.parametrize("view,expected", EXPECTED_VIEW_ROWS.items())
def test_view_executes_and_returns_expected_rows(pg, view, expected):
    assert scalar(pg, "SELECT COUNT(*) FROM information_schema.views WHERE table_name = %s", (view,)) == 1
    rows = pg.execute(f"SELECT * FROM {view}").fetchall()
    assert len(rows) == expected


@pytest.mark.parametrize("view,pattern", [
    ("v1_trip_route_details", "JOIN"),
    ("v2_faster_than_all_mode_averages", "ALL ("),
    ("v2_faster_than_all_mode_averages", "GROUP BY"),
    ("v3_faster_than_trip_average", "r2.trip_id = r.trip_id"),
    ("v4_users_and_feedback", "FULL JOIN"),
    ("v5_relevant_locations", "UNION"),
    ("v6_ranked_route_recommendations", "dense_rank()"),
])
def test_required_sql_patterns_present(pg, view, pattern):
    definition = scalar(pg, "SELECT pg_get_viewdef(%s::regclass, true)", (view,))
    assert pattern.lower() in definition.lower()


def test_v1_joins_at_least_three_tables(pg):
    deps = scalar(pg, """
        SELECT COUNT(DISTINCT source_table.relname) FROM pg_depend d
        JOIN pg_rewrite r ON r.oid = d.objid
        JOIN pg_class view_cls ON view_cls.oid = r.ev_class
        JOIN pg_class source_table ON source_table.oid = d.refobjid
        WHERE view_cls.relname = 'v1_trip_route_details' AND source_table.relname <> 'v1_trip_route_details'
    """)
    assert deps >= 3


def test_v2_all_operator_semantics(pg):
    """Every returned route is faster than the smallest per-mode average."""
    min_avg = scalar(pg, "SELECT MIN(a) FROM (SELECT AVG(estimated_duration_min) a FROM route_option GROUP BY travel_mode) s")
    rows = pg.execute("SELECT estimated_duration_min FROM v2_faster_than_all_mode_averages").fetchall()
    assert rows and all(r[0] < min_avg for r in rows)


def test_v3_correlated_semantics(pg):
    rows = pg.execute("""
        SELECT v.route_id FROM v3_faster_than_trip_average v
        WHERE v.estimated_duration_min >= (SELECT AVG(estimated_duration_min) FROM route_option WHERE trip_id = v.trip_id)
    """).fetchall()
    assert rows == []


def test_v4_full_join_keeps_users_without_feedback(pg):
    nulls = pg.execute("SELECT full_name FROM v4_users_and_feedback WHERE feedback_id IS NULL ORDER BY user_id").fetchall()
    assert [r[0] for r in nulls] == ["Aisha Khan", "Daniel Chen"]


def test_v5_union_matches_saved_or_destination(pg):
    expected = scalar(pg, "SELECT COUNT(*) FROM (SELECT location_id FROM saved_location UNION SELECT destination_location_id FROM trip) s")
    assert scalar(pg, "SELECT COUNT(*) FROM v5_relevant_locations") == expected


# ---- recommendation algorithm (View 6) --------------------------------------

def test_v6_scores_match_phase_ii_weighting(pg):
    """Independently recompute every component and the weighted total in Python."""
    routes = pg.execute("""
        SELECT r.route_id, r.trip_id, r.travel_mode, r.distance_km, r.estimated_duration_min, r.toll_cost,
               p.preferred_mode,
               COALESCE((SELECT MAX(c.severity) FROM route_segment s JOIN condition_observation c
                         ON c.segment_id = s.segment_id WHERE s.route_id = r.route_id), 0) AS sev
        FROM route_option r JOIN trip t ON t.trip_id = r.trip_id JOIN user_preference p ON p.user_id = t.user_id
    """).fetchall()
    view = {r[0]: r for r in pg.execute(
        "SELECT route_id, time_score, distance_score, safety_score, toll_score, preference_score, "
        "total_route_score, recommendation_rank FROM v6_ranked_route_recommendations").fetchall()}
    by_trip = {}
    for r in routes:
        by_trip.setdefault(r[1], []).append(r)
    for trip_routes in by_trip.values():
        fastest = min(r[4] for r in trip_routes)
        shortest = min(r[3] for r in trip_routes)
        totals = {}
        for rid, _, mode, dist, dur, toll, pref, sev in trip_routes:
            time_s = round(Decimal(100) * fastest / dur, 2)
            dist_s = round(Decimal(100) * shortest / dist, 2)
            safety = Decimal(100 - sev * 20)
            toll_s = max(Decimal(0), Decimal(100) - toll * 20)
            pref_s = Decimal(100 if mode == pref else 50)
            total = round(Decimal("0.45") * time_s + Decimal("0.25") * dist_s + Decimal("0.15") * safety
                          + Decimal("0.10") * toll_s + Decimal("0.05") * pref_s, 2)
            v = view[rid]
            assert (v[1], v[2], v[3], v[4], v[5], v[6]) == (time_s, dist_s, safety, toll_s, pref_s, total)
            totals[rid] = total
        best = max(totals.values())
        for rid, t in totals.items():
            assert (view[rid][7] == 1) == (t == best)


def test_v6_known_phase_ii_results(pg):
    rows = dict(pg.execute("SELECT route_id, total_route_score FROM v6_ranked_route_recommendations").fetchall())
    assert rows[1] == Decimal("94.00")
    assert rows[2] == Decimal("76.20")
    assert rows[7] == Decimal("83.00")
    assert rows[9] == Decimal("69.17")


# ---- constraints ------------------------------------------------------------

def expect_violation(pg, sql, params, sqlstate):
    with pytest.raises(psycopg.Error) as exc:
        pg.execute(sql, params)
    pg.rollback()
    assert exc.value.sqlstate == sqlstate


def test_unique_email(pg):
    expect_violation(pg, "INSERT INTO app_user (full_name, email, password_hash) VALUES ('X', %s, 'h')",
                     ("avery.morgan@example.com",), "23505")


def test_check_user_role(pg):
    expect_violation(pg, "INSERT INTO app_user (full_name, email, password_hash, user_role) VALUES ('X','x@example.com','h','root')",
                     None, "23514")


def test_fk_trip_requires_existing_location(pg):
    expect_violation(pg, "INSERT INTO trip (user_id, origin_location_id, destination_location_id, requested_at, departure_time, trip_status) "
                         "VALUES (1, 1, 999, now(), now(), 'planned')", None, "23503")


def test_check_origin_differs_from_destination(pg):
    expect_violation(pg, "INSERT INTO trip (user_id, origin_location_id, destination_location_id, requested_at, departure_time, trip_status) "
                         "VALUES (1, 2, 2, now(), now(), 'planned')", None, "23514")


def test_check_rating_range(pg):
    expect_violation(pg, "INSERT INTO feedback (user_id, trip_id, rating) VALUES (3, 1, 6)", None, "23514")


def test_check_severity_range(pg):
    expect_violation(pg, "INSERT INTO condition_observation (segment_id, observed_at, condition_type, severity, description, source_name) "
                         "VALUES (1, now(), 'weather', 9, 'x', 'y')", None, "23514")


def test_check_negative_toll(pg):
    expect_violation(pg, "UPDATE route_option SET toll_cost = -1 WHERE route_id = 1", None, "23514")


def test_check_latitude_range(pg):
    expect_violation(pg, "INSERT INTO location (location_name, street_address, city, latitude, longitude, location_type) "
                         "VALUES ('x','y','z', 95, 0, 'home')", None, "23514")


def test_unique_trip_option_number(pg):
    expect_violation(pg, "INSERT INTO route_option (trip_id, option_number, travel_mode, distance_km, estimated_duration_min) "
                         "VALUES (1, 1, 'walking', 5, 60)", None, "23505")


def test_unique_saved_location_per_user(pg):
    expect_violation(pg, "INSERT INTO saved_location (user_id, location_id, label) VALUES (1, 1, 'dup')", None, "23505")


def test_one_selected_route_per_trip(pg):
    expect_violation(pg, "UPDATE route_option SET is_selected = TRUE WHERE route_id = 2", None, "23505")


def test_restrict_delete_of_referenced_location(pg):
    expect_violation(pg, "DELETE FROM location WHERE location_id = 1", None, "23503")


def test_cascade_delete_trip(pg):
    pg.execute("DELETE FROM trip WHERE trip_id = 1")
    assert scalar(pg, "SELECT COUNT(*) FROM route_option WHERE trip_id = 1") == 0
    assert scalar(pg, "SELECT COUNT(*) FROM feedback WHERE trip_id = 1") == 0
    assert scalar(pg, "SELECT COUNT(*) FROM route_segment WHERE route_id IN (1, 2)") == 0
    pg.rollback()


def test_identity_sequences_advanced_after_seed(pg):
    new_id = scalar(pg, "INSERT INTO location (location_name, street_address, city, latitude, longitude, location_type) "
                        "VALUES ('Seq test','1 Test St','Oshawa', 43.1, -78.1, 'other') RETURNING location_id")
    assert new_id > 8  # seeded IDs 1..8 are never reused
    pg.rollback()
