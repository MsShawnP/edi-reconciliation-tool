"""U7 dashboard route and visual asset tests.

Unit tests (no DB required):
- GET /lifecycle returns 200
- GET / returns 200
- dashboard/static/js/lifecycle.js exists
- get_lifecycle_stats() returns None when DB not configured
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from dashboard.app import app
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Route smoke tests (no DB — routes must degrade gracefully)
# ---------------------------------------------------------------------------

def test_lifecycle_route_ok(client):
    r = client.get("/lifecycle")
    assert r.status_code == 200
    assert "lifecycle-visual" in r.text
    assert "lifecycle-data" in r.text


def test_dashboard_route_ok(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "exception" in r.text.lower()


def test_api_lifecycle_ok(client):
    """Canonical fallback is served when no DB is configured."""
    r = client.get("/api/lifecycle")
    assert r.status_code == 200
    body = r.json()
    assert body["ordered"] == 150
    assert body["source"] == "canonical"


def test_exceptions_partial_ok(client):
    r = client.get("/exceptions")
    assert r.status_code == 200


def test_ack_status_partial_ok(client):
    r = client.get("/ack-status")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Static asset existence
# ---------------------------------------------------------------------------

def test_lifecycle_js_exists():
    js = _REPO / "dashboard" / "static" / "js" / "lifecycle.js"
    assert js.is_file(), "dashboard/static/js/lifecycle.js not found"


def test_lifecycle_js_has_canonical_fallback():
    js = (_REPO / "dashboard" / "static" / "js" / "lifecycle.js").read_text(encoding="utf-8")
    assert "CANONICAL" in js
    assert "150" in js
    assert "lifecycle-visual" in js


# ---------------------------------------------------------------------------
# get_lifecycle_stats() unit test (no DB)
# ---------------------------------------------------------------------------

def test_get_lifecycle_stats_returns_none_without_db(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    from dashboard.routes.lifecycle import get_lifecycle_stats
    assert get_lifecycle_stats() is None


# ---------------------------------------------------------------------------
# U8: Failure pattern catalog
# ---------------------------------------------------------------------------

def test_catalog_route_ok(client):
    r = client.get("/catalog")
    assert r.status_code == 200
    assert "Failure Pattern Catalog" in r.text


def test_catalog_has_all_seven_patterns(client):
    r = client.get("/catalog")
    body = r.text
    for key in (
        "ordered_not_asnd",
        "shipped_not_invoiced",
        "short_pay",
        "uom_mismatch",
        "qty_mismatch",
        "852_discrepancy",
        "missing_997_ack",
    ):
        assert key in body, f"Pattern key {key!r} not found in /catalog response"


def test_catalog_997_ack_is_ops_not_revenue(client):
    r = client.get("/catalog")
    assert "operational" in r.text.lower() or "$0" in r.text
