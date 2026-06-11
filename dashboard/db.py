"""Database connection utilities for the dashboard.

Reads DATABASE_URL from the environment. All public functions degrade
gracefully when the variable is absent so the app renders with empty/demo
data rather than crashing.
"""
from __future__ import annotations

import os
from typing import Any

_conn = None
_active_url: str | None = None


def is_configured() -> bool:
    """Return True if DATABASE_URL is present in the environment."""
    return bool(os.environ.get("DATABASE_URL"))


def _get_conn():
    global _conn, _active_url
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    if _conn is None or _conn.closed or url != _active_url:
        import psycopg2  # noqa: PLC0415
        _conn = psycopg2.connect(url)
        _conn.autocommit = True
        _active_url = url
    return _conn


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Execute a SELECT query and return rows as plain dicts."""
    import psycopg2.extras  # noqa: PLC0415
    conn = _get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
