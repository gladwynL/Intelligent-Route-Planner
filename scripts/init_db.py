"""Create (if needed) and initialise the project's PostgreSQL database.

Runs database/schema.sql, database/seed.sql and database/views.sql in order,
then prints a verification summary (row counts per table, rows per view).

Usage (from the project root, with the virtual environment active):
    python scripts/init_db.py                 # uses DATABASE_URL from .env
    python scripts/init_db.py --test          # uses TEST_DATABASE_URL
    python scripts/init_db.py --url postgresql://user:pw@host:5432/dbname

Safety: the script only CREATEs the target database when it does not exist.
It never drops a database; schema.sql drops/recreates only this project's
nine tables and ten views inside the target database.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "database"
SQL_FILES = ("schema.sql", "seed.sql", "views.sql")

TABLES = (
    "app_user", "location", "user_preference", "trip", "route_option",
    "route_segment", "condition_observation", "saved_location", "feedback",
)
VIEWS = (
    "v1_trip_route_details", "v2_faster_than_all_mode_averages",
    "v3_faster_than_trip_average", "v4_users_and_feedback",
    "v5_relevant_locations", "v6_ranked_route_recommendations",
    "v7_condition_risk_by_route", "v8_favourite_saved_locations",
    "v9_low_carbon_alternatives", "v10_user_feedback_summary",
)


def to_libpq(url: str) -> str:
    """Accept SQLAlchemy-style URLs (postgresql+psycopg://) as well as libpq ones."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def ensure_database(conninfo: str) -> None:
    params = conninfo_to_dict(conninfo)
    dbname = params.get("dbname")
    if not dbname:
        raise SystemExit("The database URL must include a database name.")
    admin = make_conninfo(conninfo, dbname="postgres")
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
            print(f"Created database '{dbname}'.")
        else:
            print(f"Database '{dbname}' already exists; re-initialising project objects.")


def run_scripts(conninfo: str, files=SQL_FILES) -> None:
    # autocommit: each script runs as its own implicit transaction (seed.sql
    # additionally wraps its inserts in an explicit BEGIN/COMMIT).
    with psycopg.connect(conninfo, autocommit=True) as conn:
        for name in files:
            text = (SQL_DIR / name).read_text(encoding="utf-8")
            conn.execute(text)  # simple-query protocol: multi-statement scripts are allowed
            print(f"  applied {name}")


def verify(conninfo: str) -> dict:
    summary = {"tables": {}, "views": {}}
    with psycopg.connect(conninfo) as conn:
        version = conn.execute("SHOW server_version").fetchone()[0]
        summary["server_version"] = version
        for t in TABLES:
            summary["tables"][t] = conn.execute(
                sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(t))).fetchone()[0]
        for v in VIEWS:
            summary["views"][v] = conn.execute(
                sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(v))).fetchone()[0]
    return summary


def main(argv=None) -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="Database URL (overrides .env)")
    ap.add_argument("--test", action="store_true", help="Use TEST_DATABASE_URL")
    ap.add_argument("--verify-only", action="store_true", help="Only print verification summary")
    args = ap.parse_args(argv)

    url = args.url or os.getenv("TEST_DATABASE_URL" if args.test else "DATABASE_URL")
    if not url:
        print("No database URL. Copy .env.example to .env or pass --url.", file=sys.stderr)
        return 2
    conninfo = to_libpq(url)
    try:
        if not args.verify_only:
            ensure_database(conninfo)
            run_scripts(conninfo)
        s = verify(conninfo)
    except psycopg.OperationalError as exc:
        print(f"Could not connect to PostgreSQL: {exc}".strip(), file=sys.stderr)
        print("Is PostgreSQL running and is DATABASE_URL correct? (docker compose up -d)", file=sys.stderr)
        return 1

    print(f"\nPostgreSQL server version: {s['server_version']}")
    print("\nTable row counts:")
    for t, n in s["tables"].items():
        print(f"  {t:<24} {n:>4}")
    print("\nView row counts:")
    for v, n in s["views"].items():
        print(f"  {v:<36} {n:>4}")
    ok = all(n >= 6 for n in s["tables"].values()) and all(n > 0 for n in s["views"].values())
    print("\nVerification:", "PASS (9 tables >= 6 rows, 10 views non-empty)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
