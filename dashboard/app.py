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

_ROOT = Path(__file__).parent

app = FastAPI(title="EDI Reconciliation Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(_ROOT / "static")), name="static")
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
    return templates.TemplateResponse("lifecycle.html", {
        "request":     request,
        "active_page": "lifecycle",
    })


# ---------------------------------------------------------------------------
# API: lifecycle numbers for D3 visual
# ---------------------------------------------------------------------------
# Sums Walmart PO lifecycle quantities for the live D3 chart.
# Falls back to the canonical example (150/138/150/131) when DB is offline
# or the mart tables haven't been populated yet.
_CANONICAL = {"ordered": 150, "shipped": 138, "invoiced": 150, "paid": 131, "source": "canonical"}

_LIFECYCLE_SQL = """
    select
        coalesce(sum(ordered_qty),              0)::int as ordered,
        coalesce(sum(shipped_qty_normalized),   0)::int as shipped,
        coalesce(sum(invoiced_qty_normalized),  0)::int as invoiced,
        coalesce(
            sum(coalesce(paid_amount, 0) / nullif(unit_price, 0)), 0
        )::int                                          as paid
    from edi_marts.int_four_way_match
    where partner_id = 'WALMARTUS'
"""


@app.get("/api/lifecycle")
async def api_lifecycle() -> JSONResponse:
    if not db.is_configured():
        return JSONResponse({**_CANONICAL, "source": "canonical"})
    try:
        rows = db.query(_LIFECYCLE_SQL)
        if rows and rows[0].get("ordered"):
            r = rows[0]
            return JSONResponse({
                "ordered":  int(r["ordered"]),
                "shipped":  int(r["shipped"]),
                "invoiced": int(r["invoiced"]),
                "paid":     int(r["paid"]),
                "source":   "live",
            })
        return JSONResponse({**_CANONICAL, "source": "canonical"})
    except Exception:
        return JSONResponse({**_CANONICAL, "source": "canonical"})
