"""Database access helpers built on SQLAlchemy Core.

All SQL is written explicitly with bound parameters (``:name``).  Identifiers
(table / column names) only ever come from constants defined in code, never
from user input.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from flask import current_app
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine


def init_engine(app) -> Engine:
    eng = create_engine(
        app.config["DATABASE_URL"],
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={
            "connect_timeout": 5,
            # All TIMESTAMP defaults (CURRENT_TIMESTAMP) are evaluated in one documented zone.
            "options": f"-c timezone={app.config['DB_TIMEZONE']}",
        },
    )
    app.extensions["db_engine"] = eng
    return eng


def engine() -> Engine:
    return current_app.extensions["db_engine"]


def _rows(result) -> list[dict]:
    return [dict(r._mapping) for r in result]


def query(sql: str, params: dict | None = None, conn: Connection | None = None) -> list[dict]:
    """Run a SELECT and return a list of dict rows."""
    if conn is not None:
        return _rows(conn.execute(text(sql), params or {}))
    with engine().connect() as c:
        return _rows(c.execute(text(sql), params or {}))


def query_one(sql: str, params: dict | None = None, conn: Connection | None = None) -> dict | None:
    rows = query(sql, params, conn)
    return rows[0] if rows else None


@contextmanager
def transaction():
    """Yield a connection inside a transaction (commit on success, rollback on error)."""
    with engine().begin() as conn:
        yield conn


def execute(sql: str, params: dict | None = None, conn: Connection | None = None) -> list[dict]:
    """Run a data-modifying statement; returns RETURNING rows if any."""
    def _run(c):
        res = c.execute(text(sql), params or {})
        return _rows(res) if res.returns_rows else []
    if conn is not None:
        return _run(conn)
    with engine().begin() as c:
        return _run(c)


def insert(table: str, data: dict, returning: str = "*", conn: Connection | None = None) -> dict:
    cols = list(data)
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) "
           f"VALUES ({', '.join(':' + c for c in cols)}) RETURNING {returning}")
    return execute(sql, data, conn)[0]


def update(table: str, pk: str, pk_value: Any, data: dict, conn: Connection | None = None) -> dict | None:
    if not data:
        return query_one(f"SELECT * FROM {table} WHERE {pk} = :_pk", {"_pk": pk_value}, conn)
    sets = ", ".join(f"{c} = :{c}" for c in data)
    params = dict(data)
    params["_pk"] = pk_value
    rows = execute(f"UPDATE {table} SET {sets} WHERE {pk} = :_pk RETURNING *", params, conn)
    return rows[0] if rows else None


def delete(table: str, pk: str, pk_value: Any, conn: Connection | None = None) -> bool:
    rows = execute(f"DELETE FROM {table} WHERE {pk} = :_pk RETURNING {pk}", {"_pk": pk_value}, conn)
    return bool(rows)


class Filters:
    """Accumulates parameterised WHERE clauses for search/filter endpoints."""

    def __init__(self):
        self.clauses: list[str] = []
        self.params: dict[str, Any] = {}

    def add(self, clause: str, **params) -> "Filters":
        self.clauses.append(clause)
        self.params.update(params)
        return self

    def where(self) -> str:
        return (" WHERE " + " AND ".join(self.clauses)) if self.clauses else ""
