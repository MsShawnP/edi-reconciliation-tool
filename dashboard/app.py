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
from dashboard.routes.lifecycle import (
    get_lifecycle_stats,
    get_lifecycle_partners,
    get_lifecycle_drilldown,
    get_callout_stats,
)
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
async def lifecycle_page(
    request: Request,
    partner: str = Query(default=""),
):
    stats = get_lifecycle_stats(partner=partner)
    partners = get_lifecycle_partners()
    callouts = get_callout_stats(partner=partner)
    lifecycle_json = json.dumps(
        {**stats, "callouts": callouts, "source": "live"} if stats else {}
    )
    return templates.TemplateResponse(request, "lifecycle.html", {
        "active_page":       "lifecycle",
        "db_ok":             db.is_configured(),
        "lifecycle_json":    lifecycle_json,
        "partners":          partners,
        "selected_partner":  partner,
    })


# ---------------------------------------------------------------------------
# Failure pattern catalog (U8)
# ---------------------------------------------------------------------------

@app.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    partner: str = Query(default=""),
    date_start: str = Query(default=""),
    date_end: str = Query(default=""),
):
    partners = get_partners()
    bounds = get_date_range_bounds()

    active_label = ""
    if bounds and not date_start and not date_end:
        active_label = f"{bounds['min_fmt']} – {bounds['max_fmt']} (full corpus)"
    elif date_start or date_end:
        from datetime import date as date_cls
        try:
            s = date_cls.fromisoformat(date_start) if date_start else None
            e = date_cls.fromisoformat(date_end) if date_end else None
            parts = []
            if s:
                parts.append(s.strftime("%b %d, %Y"))
            if e:
                parts.append(e.strftime("%b %d, %Y"))
            active_label = " – ".join(parts)
        except ValueError:
            active_label = f"{date_start} – {date_end}"

    return templates.TemplateResponse(request, "catalog.html", {
        "active_page":      "catalog",
        "patterns":         get_patterns(),
        "partners":         partners,
        "selected_partner": partner,
        "date_bounds":      bounds,
        "date_start":       date_start,
        "date_end":         date_end,
        "active_label":     active_label,
    })


# ---------------------------------------------------------------------------
# API: lifecycle numbers for the D3 visual (JSON endpoint)
# ---------------------------------------------------------------------------

@app.get("/api/catalog/drilldown")
async def api_catalog_drilldown(
    exception_class: str = Query(default="", alias="class"),
    partner: str = Query(default=""),
    date_start: str = Query(default=""),
    date_end: str = Query(default=""),
    limit: int = Query(default=100),
) -> JSONResponse:
    """Return exception rows for a specific failure pattern class."""
    if not exception_class or not db.is_configured():
        return JSONResponse([])
    from dashboard.routes.exceptions import _CLASS_LABELS, _date_where
    try:
        conditions = ["exception_class = %s"]
        params: list = [exception_class]
        if partner:
            conditions.append("partner_id = %s")
            params.append(partner)
        date_frag, date_params = _date_where(date_start, date_end)
        if date_frag:
            conditions.append(date_frag)
            params.extend(date_params)
        where = " and ".join(conditions)
        params.append(limit)
        rows = db.query(f"""
            select
                partner_id, exception_class, po_number, sku,
                invoice_number, dollar_impact,
                dispute_window_days, dispute_window_expires_at, dispute_urgent
            from {db.MARTS_SCHEMA}.fct_exceptions
            where {where}
            order by dollar_impact desc nulls last
            limit %s
        """, tuple(params))
        total_dollars = 0.0
        still_open = 0
        expired = 0
        for row in rows:
            amt = float(row["dollar_impact"] or 0)
            total_dollars += amt
            row["dollar_fmt"] = _fmt_dollar(amt)
            row["class_label"] = _CLASS_LABELS.get(
                row["exception_class"], row["exception_class"]
            )
            if row["dispute_window_expires_at"]:
                row["dispute_window_expires_at"] = str(row["dispute_window_expires_at"])
            if row["dispute_urgent"]:
                still_open += 1
            elif row["dispute_window_days"] is not None:
                expired += 1
        return JSONResponse({
            "rows": rows,
            "summary": {
                "total": len(rows),
                "total_dollars_fmt": _fmt_dollar(total_dollars),
                "still_open": still_open,
                "expired": expired,
            },
        })
    except Exception:
        return JSONResponse({"rows": [], "summary": None})


@app.get("/api/lifecycle")
async def api_lifecycle(partner: str = Query(default="")) -> JSONResponse:
    stats = get_lifecycle_stats(partner=partner)
    if stats:
        callouts = get_callout_stats(partner=partner)
        return JSONResponse({**stats, "callouts": callouts, "source": "live"})
    return JSONResponse({
        "ordered": 150, "shipped": 138, "invoiced": 150, "paid": 131,
        "callouts": [
            {"count": 12, "dollars": 1800.0},
            {"count": 12, "dollars": 2100.0},
            {"count": 19, "dollars": 2400.0},
        ],
        "source": "canonical",
    })


@app.get("/api/lifecycle/drilldown")
async def api_lifecycle_drilldown(
    callout: str = Query(default=""),
    partner: str = Query(default=""),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    result = get_lifecycle_drilldown(
        callout_index=callout, partner=partner, offset=offset
    )
    return JSONResponse(result)
