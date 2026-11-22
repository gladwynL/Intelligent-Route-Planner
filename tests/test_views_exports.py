"""SQL-view endpoints, view authorisation/scoping, search/sort and CSV/PDF exports."""
from __future__ import annotations

import csv
import io

import pytest

EXPECTED = {"v1": 12, "v2": 4, "v3": 6, "v4": 8, "v5": 8, "v6": 12, "v7": 12, "v8": 4, "v9": 7, "v10": 6}


def test_catalog_lists_all_ten_views_for_admin(admin):
    body = admin.get("/api/views").get_json()
    assert [v["key"] for v in body["views"]] == list(EXPECTED)


@pytest.mark.parametrize("key,count", EXPECTED.items())
def test_each_view_returns_rows_for_admin(admin, key, count):
    body = admin.get(f"/api/views/{key}").get_json()
    assert body["count"] == count and len(body["rows"]) == count
    assert list(body["rows"][0].keys()) == body["view"]["columns"]
    assert body["sql"].startswith("CREATE VIEW")


def test_guest_sees_only_non_personal_views(anon_guest):
    keys = [v["key"] for v in anon_guest.get("/api/views").get_json()["views"]]
    assert keys == ["v2", "v3", "v5", "v6", "v7", "v9"]
    for k in ("v1", "v4", "v8", "v10"):
        assert anon_guest.get(f"/api/views/{k}").status_code == 403
        assert anon_guest.get(f"/api/views/{k}/export?format=csv").status_code == 403


def test_user_personal_views_are_scoped(user):
    v1 = user.get("/api/views/v1").get_json()
    assert v1["view"]["scoped_to_current_user"] is True
    assert {r["trip_id"] for r in v1["rows"]} == {2}
    assert {r["user_id"] for r in user.get("/api/views/v4").get_json()["rows"]} == {2}
    assert user.get("/api/views/v8").get_json()["rows"] == []  # Jordan has no favourites
    v10 = user.get("/api/views/v10").get_json()["rows"]
    assert len(v10) == 1 and v10[0]["full_name"] == "Jordan Rivera"


def test_unknown_view_is_404(admin):
    assert admin.get("/api/views/v11").status_code == 404
    assert admin.get("/api/views/app_user").status_code == 404


def test_view_filters_keyword_and_sort(admin):
    rows = admin.get("/api/views/v6?travel_mode=driving").get_json()["rows"]
    assert rows and all(r["travel_mode"] == "driving" for r in rows)
    rows = admin.get("/api/views/v6?recommendation_rank=1&sort=total_route_score&dir=desc").get_json()["rows"]
    assert len(rows) == 6
    scores = [r["total_route_score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    rows = admin.get("/api/views/v1?q=Lakeview").get_json()["rows"]
    assert {r["trip_id"] for r in rows} == {5}
    rows = admin.get("/api/views/v1?is_selected=true").get_json()["rows"]
    assert len(rows) == 6 and all(r["is_selected"] for r in rows)
    rows = admin.get("/api/views/v5?city=whitby").get_json()["rows"]
    assert {r["location_id"] for r in rows} == {6, 8}


def test_view_filter_validation(admin):
    assert admin.get("/api/views/v6?trip_id=abc").status_code == 400
    assert admin.get("/api/views/v6?travel_mode=boat").status_code == 400
    assert admin.get("/api/views/v6?sort=password_hash").status_code == 400
    assert admin.get("/api/views/v1?is_selected=maybe").status_code == 400


def test_sql_injection_attempts_are_inert(admin):
    r = admin.get("/api/views/v1?q=' OR 1=1; DROP TABLE trip; --")
    assert r.status_code == 200 and r.get_json()["rows"] == []
    assert admin.get("/api/views/v1").get_json()["count"] == 12
    assert admin.get("/api/views/v6?sort=trip_id;DROP TABLE trip").status_code == 400


# ---- exports -------------------------------------------------------------------

def test_csv_export_contains_view_rows(admin):
    r = admin.get("/api/views/v1/export?format=csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert "attachment" in r.headers["Content-Disposition"] and ".csv" in r.headers["Content-Disposition"]
    text = r.data.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["trip_id", "full_name", "origin", "destination", "route_id", "travel_mode",
                       "distance_km", "estimated_duration_min", "is_selected"]
    assert len(rows) == 13
    assert rows[1][1] == "Avery Morgan"


def test_csv_export_respects_filters_and_escapes_special_chars(admin):
    admin.put("/api/feedback/1", {"comments": 'Says "hi", then =1+1'})
    r = admin.get("/api/views/v4/export?format=csv&user_id=1")
    rows = list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    assert len(rows) == 3
    comments = {row[5] for row in rows[1:]}
    assert 'Says "hi", then =1+1' in comments


def test_csv_formula_injection_neutralised(admin):
    admin.put("/api/feedback/1", {"comments": "=HYPERLINK(\"http://evil\")"})
    r = admin.get("/api/views/v4/export?format=csv&user_id=1")
    assert "'=HYPERLINK" in r.data.decode("utf-8-sig")


def test_pdf_export_is_valid_pdf(admin):
    r = admin.get("/api/views/v6/export?format=pdf&trip_id=1")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    assert r.data[:5] == b"%PDF-" and r.data.rstrip().endswith(b"%%EOF")
    assert len(r.data) > 1500


def test_trip_and_observation_exports(user, admin):
    r = user.get("/api/export/trips?format=csv")
    rows = list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    assert len(rows) == 2 and rows[1][0] == "2"  # only Jordan's trip
    r = admin.get("/api/export/observations?format=pdf&type=weather")
    assert r.data[:5] == b"%PDF-"


def test_export_format_validation(admin):
    r = admin.get("/api/views/v1/export?format=xlsx")
    assert r.status_code == 400 and "csv" in r.get_json()["error"]["message"]


def test_export_with_no_rows(admin):
    r = admin.get("/api/views/v1/export?format=pdf&q=zzzz-no-match")
    assert r.status_code == 200 and r.data[:5] == b"%PDF-"


def test_analytics_summary(admin):
    a = admin.get("/api/analytics/summary").get_json()
    assert a["table_counts"]["route_option"] >= 12
    assert {m["travel_mode"] for m in a["duration_by_mode"]} == {"driving", "transit", "cycling", "walking"}
    assert [s["severity"] for s in a["severity_distribution"]] == [0, 1, 2, 3, 4, 5]
    assert sum(r["count"] for r in a["rating_distribution"]) == a["table_counts"]["feedback"]
