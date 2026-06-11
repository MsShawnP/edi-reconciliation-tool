"""EDI Reconciliation Exception Dashboard.

FastAPI + Jinja2 + HTMX application.

Run:
    uvicorn dashboard.app:app --reload

Environment:
    DATABASE_URL   or individual POSTGRES_* vars (see dashboard/routes/db.py)
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import dashboard.routes.db as db
from dashboard.routes.exceptions import (
    get_exception_summary,
    get_exceptions,
    get_partners,
    get_997_status,
    _CLASS_LABELS,
)
from dashboard.routes.lifecycle import get_lifecycle_stats
from dashboard.routes.catalog import get_patterns

_ROOT = Path(__file__).parent

app = FastAPI(title="EDI Reconciliation Dashboard", docs_url=None, redoc_url=None)
app.mount("/static",  StaticFiles(directory=str(_ROOT / "static")),         name="static")
app.mount("/visuals", StaticFiles(directory=str(_ROOT.parent / "visuals")), name="visuals")
templates = Jinja2Templates(directory=str(_ROOT / "templates"))


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    partner: str = Query(default=""),
    exception_class: str = Query(default="", alias="class"),
):
    summary    = get_exception_summary()
    exceptions = get_exceptions(partner=partner, exception_class=exception_class)
    partners   = get_partners()
    db_ok      = db.is_configured()

    return templates.TemplateResponse("dashboard.html", {
        "request":          request,
        "summary":          summary,
        "exceptions":       exceptions,
        "partners":         partners,
        "selected_partner": partner,
        "selected_class":   exception_class,
        "class_labels":     _CLASS_LABELS,
        "db_ok":            db_ok,
        "active_page":      "dashboard",
    })


# ---------------------------------------------------------------------------
# HTMX partial — exception table rows only
# ---------------------------------------------------------------------------

@app.get("/exceptions", response_class=HTMLResponse)
async def exception_rows(
    request: Request,
    partner: str = Query(default=""),
    exception_class: str = Query(default="", alias="class"),
):
    exceptions = get_exceptions(partner=partner, exception_class=exception_class)
    return templates.TemplateResponse("_exception_rows.html", {
        "request":    request,
        "exceptions": exceptions,
    })


# ---------------------------------------------------------------------------
# 997 ACK status section (HTMX partial)
# ---------------------------------------------------------------------------

@app.get("/ack-status", response_class=HTMLResponse)
async def ack_status(request: Request):
    acks = get_997_status()
    return templates.TemplateResponse("_ack_rows.html", {
        "request": request,
        "acks":    acks,
    })


# ---------------------------------------------------------------------------
# Lifecycle visual page (U7)
# ---------------------------------------------------------------------------

@app.get("/lifecycle", response_class=HTMLResponse)
async def lifecycle_page(request: Request):
    stats = get_lifecycle_stats()
    # json.dumps with ensure_ascii=True is safe to embed in <script type="application/json">
    lifecycle_json = json.dumps(stats or {})
    return templates.TemplateResponse("lifecycle.html", {
        "request":        request,
        "active_page":    "lifecycle",
        "db_ok":          db.is_configured(),
        "lifecycle_json": lifecycle_json,
    })


# ---------------------------------------------------------------------------
# Failure pattern catalog (U8)
# ---------------------------------------------------------------------------

@app.get("/catalog", response_class=HTMLResponse)
async def catalog_page(request: Request):
    return templates.TemplateResponse("catalog.html", {
        "request":     request,
        "active_page": "catalog",
        "patterns":    get_patterns(),
    })


# ---------------------------------------------------------------------------
# API: lifecycle numbers for the D3 visual (JSON endpoint)
# ---------------------------------------------------------------------------

@app.get("/api/lifecycle")
async def api_lifecycle() -> JSONResponse:
    stats = get_lifecycle_stats()
    if stats:
        return JSONResponse({**stats, "source": "live"})
    return JSONResponse({
        "ordered": 150, "shipped": 138, "invoiced": 150, "paid": 131,
        "shipped_short": 12, "invoiced_excess": 12, "short_pay_dollars": 2400.0,
        "source": "canonical",
    })
