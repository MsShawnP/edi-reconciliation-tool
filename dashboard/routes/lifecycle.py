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
            with
            qty_totals as (
                select
                    coalesce(sum(ordered_qty),             0) as total_ordered,
                    coalesce(sum(shipped_qty_normalized),  0) as total_shipped,
                    coalesce(sum(invoiced_qty_normalized), 0) as total_invoiced
                from {_SCHEMA}.int_four_way_match
            ),
            dollar_totals as (
                select
                    coalesce(sum(invoice_amount), 0) as total_invoiced_dollars,
                    coalesce(sum(paid_amount),    0) as total_paid_dollars
                from (
                    select distinct on (partner_id, invoice_number)
                        invoice_amount, paid_amount
                    from {_SCHEMA}.int_four_way_match
                    where invoice_number is not null
                ) deduped
            )
            select q.*, d.*
            from qty_totals q
            cross join dollar_totals d
        """)
        if not rows:
            return None

        r = rows[0]
        total_ordered          = float(r["total_ordered"])
        total_shipped          = float(r["total_shipped"])
        total_invoiced         = float(r["total_invoiced"])
        total_invoiced_dollars = float(r["total_invoiced_dollars"])
        total_paid_dollars_raw = float(r["total_paid_dollars"])

        # Cap paid at invoiced: PAID > INVOICED is structurally impossible
        # (you cannot pay more than you billed).  The synthetic 820 corpus
        # inflates paid_amount because RMR segments are per-line-item, not
        # per-invoice — payment_agg sums them, producing totals that exceed
        # the invoice document total.  Capping here is correct for any
        # dataset; the upstream generator bug is tracked separately.
        total_paid_dollars = min(total_paid_dollars_raw, total_invoiced_dollars)

        avg_unit_price = (
            total_invoiced_dollars / total_invoiced if total_invoiced > 0 else 0
        )
        cases_paid_equiv = (
            total_paid_dollars / avg_unit_price if avg_unit_price > 0 else 0
        )

        shipped_short   = max(0, total_ordered  - total_shipped)
        invoiced_excess = max(0, total_invoiced - total_shipped)
        short_pay_dlrs  = max(0, total_invoiced_dollars - total_paid_dollars)

        ordered  = int(round(total_ordered))
        shipped  = int(round(total_shipped))
        invoiced = int(round(total_invoiced))
        paid     = int(round(cases_paid_equiv))

        # Server-side sanity: PAID must not exceed INVOICED in case-equiv
        if paid > invoiced:
            paid = invoiced

        return {
            "ordered":           ordered,
            "shipped":           shipped,
            "invoiced":          invoiced,
            "paid":              paid,
            "shipped_short":     int(round(shipped_short)),
            "invoiced_excess":   int(round(invoiced_excess)),
            "short_pay_dollars": round(short_pay_dlrs, 2),
            "source":            "live",
        }
    except Exception:
        logger.exception("get_lifecycle_stats query failed")
        return None
