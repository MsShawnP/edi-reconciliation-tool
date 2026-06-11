"""Lifecycle visual data — four-way match funnel stats for the D3 embed."""
from __future__ import annotations

import logging
from typing import Any

import dashboard.db as db

logger = logging.getLogger(__name__)

_SCHEMA = db.MARTS_SCHEMA


def get_lifecycle_stats() -> dict[str, Any] | None:
    """Aggregate funnel stats from int_four_way_match for the PO lifecycle visual.

    Returns None when the database is not configured or the query fails.
    """
    if not db.is_configured():
        return None
    try:
        rows = db.query(f"""
            select
                coalesce(sum(ordered_qty),             0) as total_ordered,
                coalesce(sum(shipped_qty_normalized),  0) as total_shipped,
                coalesce(sum(invoiced_qty_normalized), 0) as total_invoiced,
                coalesce(sum(invoice_amount),          0) as total_invoiced_dollars,
                coalesce(sum(paid_amount),             0) as total_paid_dollars
            from {_SCHEMA}.int_four_way_match
        """)
        if not rows:
            return None

        r = rows[0]
        total_ordered          = float(r["total_ordered"])
        total_shipped          = float(r["total_shipped"])
        total_invoiced         = float(r["total_invoiced"])
        total_invoiced_dollars = float(r["total_invoiced_dollars"])
        total_paid_dollars     = float(r["total_paid_dollars"])

        # Estimate cases-equivalent paid from dollar amounts
        avg_unit_price = (
            total_invoiced_dollars / total_invoiced if total_invoiced > 0 else 0
        )
        cases_paid_equiv = (
            total_paid_dollars / avg_unit_price if avg_unit_price > 0 else 0
        )

        shipped_short   = max(0, total_ordered  - total_shipped)
        invoiced_excess = max(0, total_invoiced - total_shipped)
        short_pay_dlrs  = max(0, total_invoiced_dollars - total_paid_dollars)

        return {
            "ordered":           int(round(total_ordered)),
            "shipped":           int(round(total_shipped)),
            "invoiced":          int(round(total_invoiced)),
            "paid":              int(round(cases_paid_equiv)),
            "shipped_short":     int(round(shipped_short)),
            "invoiced_excess":   int(round(invoiced_excess)),
            "short_pay_dollars": round(short_pay_dlrs, 2),
        }
    except Exception:
        logger.exception("get_lifecycle_stats query failed")
        return None
