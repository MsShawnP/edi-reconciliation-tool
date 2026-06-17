"""EDI Reconciliation Exception Dashboard.

FastAPI + Jinja2 + HTMX application.

Run:
    uvicorn dashboard.app:app --reload

Environment:
    DATABASE_URL   or individual POSTGRES_* vars (see dashboard/db.py)
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import dashboard.db as db
from dashboard.routes.exceptions import (
    get_exception_summary,
    get_exceptions,
    get_partners,
    get_997_status,
    get_corpus_date_range,
    get_date_range_bounds,
    _CLASS_LABELS,
    _fmt_dollar,
)
from dashboard.routes.lifecycle import get_lifecycle_stats
from dashboard.routes.catalog import get_patterns

_ROOT = Path(__file__).parent

app = FastAPI(title="EDI Reconciliation Dashboard", docs_url=None, redoc_url=None)
app.mount("/static",  StaticFiles(directory=str(_ROOT / "static")),         name="static")
# Starlette 1.0+ requires request as the first argument to TemplateResponse.
templates = Jinja2Templates(directory=str(_ROOT / "templates"))


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    partner: str = Query(default=""),
    exception_class: str = Query(default="", alias="class"),
    date_start: str = Query(default=""),
    date_end: str = Query(default=""),
):
    bounds     = get_date_range_bounds()
    summary, total_exposure = get_exception_summary(
        date_start=date_start, date_end=date_end,
    )
    exceptions = get_exceptions(
        partner=partner, exception_class=exception_class,
        date_start=date_start, date_end=date_end,
    )
    partners   = get_partners()
    db_ok      = db.is_configured()

    active_start = date_start or (bounds["min_iso"] if bounds else "")
    active_end   = date_end or (bounds["max_iso"] if bounds else "")
    active_label = ""
    if bounds and not date_start and not date_end:
        active_label = f"{bounds['min_fmt']} – {bounds['max_fmt']} (full corpus)"
    elif active_start and active_end:
        from datetime import date as date_cls
        try:
            s = date_cls.fromisoformat(active_start)
            e = date_cls.fromisoformat(active_end)
            active_label = f"{s.strftime('%b %d, %Y')} – {e.strftime('%b %d, %Y')}"
        except ValueError:
            active_label = f"{active_start} – {active_end}"

    return templates.TemplateResponse(request, "dashboard.html", {
        "summary":          summary,
        "total_exposure":   total_exposure,
        "total_exposure_fmt": _fmt_dollar(total_exposure),
        "exceptions":       exceptions,
        "partners":         partners,
        "selected_partner": partner,
        "selected_class":   exception_class,
        "class_labels":     _CLASS_LABELS,
        "db_ok":            db_ok,
        "date_bounds":      bounds,
        "date_start":       date_start,
        "date_end":         date_end,
        "active_start":     active_start,
        "active_end":       active_end,
        "active_label":     active_label,
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
    date_start: str = Query(default=""),
    date_end: str = Query(default=""),
):
    exceptions = get_exceptions(
        partner=partner, exception_class=exception_class,
        date_start=date_start, date_end=date_end,
    )
    return templates.TemplateResponse(request, "_exception_rows.html", {
        "exceptions": exceptions,
    })


# ---------------------------------------------------------------------------
# 997 ACK status section (HTMX partial)
# ---------------------------------------------------------------------------

@app.get("/ack-status", response_class=HTMLResponse)
async def ack_status(request: Request):
    acks = get_997_status()
    return templates.TemplateResponse(request, "_ack_rows.html", {
        "acks": acks,
    })


# ---------------------------------------------------------------------------
# Lifecycle visual page (U7)
# ---------------------------------------------------------------------------

@app.get("/lifecycle", response_class=HTMLResponse)
async def lifecycle_page(request: Request):
    stats = get_lifecycle_stats()
    # json.dumps with ensure_ascii=True is safe to embed in <script type="application/json">.
    # Include 'source' so the JS subtitle can distinguish live vs canonical data.
    lifecycle_json = json.dumps({**stats, "source": "live"} if stats else {})
    return templates.TemplateResponse(request, "lifecycle.html", {
        "active_page":    "lifecycle",
        "db_ok":          db.is_configured(),
        "lifecycle_json": lifecycle_json,
    })


# ---------------------------------------------------------------------------
# Failure pattern catalog (U8)
# ---------------------------------------------------------------------------

@app.get("/catalog", response_class=HTMLResponse)
async def catalog_page(request: Request):
    return templates.TemplateResponse(request, "catalog.html", {
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
