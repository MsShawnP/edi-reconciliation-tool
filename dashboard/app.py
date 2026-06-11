"""EDI Reconciliation Exception Dashboard.

FastAPI + Jinja2 + HTMX application.

Run:
    uvicorn dashboard.app:app --reload

Environment:
    DATABASE_URL   or individual POSTGRES_* vars (see dashboard/routes/db.py)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import dashboard.db as db
from dashboard.shared import templates
from dashboard.routes.exceptions import (
    get_exception_summary,
    get_exceptions,
    get_partners,
    get_997_status,
    _CLASS_LABELS,
)

_ROOT = Path(__file__).parent

app = FastAPI(title="EDI Reconciliation Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(_ROOT / "static")), name="static")


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    partner: str = Query(default=""),
    exception_class: str = Query(default="", alias="class"),
):
    summary = get_exception_summary()
    exceptions = get_exceptions(partner=partner, exception_class=exception_class)
    partners = get_partners()
    db_ok = db.is_configured()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "summary": summary,
        "exceptions": exceptions,
        "partners": partners,
        "selected_partner": partner,
        "selected_class": exception_class,
        "class_labels": _CLASS_LABELS,
        "db_ok": db_ok,
        "active_page": "dashboard",
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
        "request": request,
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
        "acks": acks,
    })


# ---------------------------------------------------------------------------
# Lifecycle visual (U7 stub)
# ---------------------------------------------------------------------------

@app.get("/lifecycle", response_class=HTMLResponse)
async def lifecycle(request: Request):
    return templates.TemplateResponse("lifecycle.html", {
        "request": request,
        "active_page": "lifecycle",
    })
