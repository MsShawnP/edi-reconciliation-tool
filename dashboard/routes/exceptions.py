"""Exception dashboard routes.

Queries fct_exceptions and int_997_match from the edi_marts schema.
All routes degrade gracefully when the database is not configured.
"""
from __future__ import annotations

import logging
from typing import Any

import dashboard.db as db

logger = logging.getLogger(__name__)

_SCHEMA = db.MARTS_SCHEMA

# Dollar-ranked exception classes (ops-only class last)
_REVENUE_CLASSES = [
    "ordered_not_asnd",
    "shipped_not_invoiced",
    "short_pay",
    "uom_mismatch",
    "qty_mismatch",
    "852_discrepancy",
]

_CLASS_LABELS = {
    "ordered_not_asnd":      "Ordered, Not ASN'd",
    "shipped_not_invoiced":  "Shipped, Not Invoiced",
    "short_pay":             "Short Pay",
    "uom_mismatch":          "UoM Mismatch",
    "qty_mismatch":          "Quantity Mismatch",
    "852_discrepancy":       "852 Sell-Through Gap",
    "missing_997_ack":       "Missing 997 ACK",
}


def _fmt_dollar(amount: float | None) -> str:
    if amount is None:
        return "—"
    if amount == 0:
        return "$0"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}K"
    return f"${amount:,.2f}"


def get_exception_summary() -> list[dict[str, Any]]:
    """Summary card data: one dict per revenue-affecting exception class."""
    if not db.is_configured():
        return []
    try:
        rows = db.query(f"""
            select
                exception_class,
                count(*)                as exception_count,
                coalesce(sum(dollar_impact), 0) as total_dollar_impact,
                bool_or(dispute_urgent) as any_urgent
            from {_SCHEMA}.fct_exceptions
            where exception_class != 'missing_997_ack'
            group by exception_class
            order by total_dollar_impact desc
        """)
        result = []
        seen = {r["exception_class"] for r in rows}
        for cls in _REVENUE_CLASSES:
            if cls in seen:
                row = next(r for r in rows if r["exception_class"] == cls)
                result.append({
                    "exception_class": cls,
                    "label": _CLASS_LABELS[cls],
                    "total_dollar_impact": float(row["total_dollar_impact"]),
                    "total_fmt": _fmt_dollar(float(row["total_dollar_impact"])),
                    "exception_count": int(row["exception_count"]),
                    "any_urgent": bool(row["any_urgent"]),
                })
            else:
                result.append({
                    "exception_class": cls,
                    "label": _CLASS_LABELS[cls],
                    "total_dollar_impact": 0.0,
                    "total_fmt": "$0",
                    "exception_count": 0,
                    "any_urgent": False,
                })
        return result
    except Exception:
        logger.exception("get_exception_summary query failed")
        return []


def get_exceptions(
    partner: str = "",
    exception_class: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Detail rows for the exception table."""
    if not db.is_configured():
        return []
    try:
        conditions = ["exception_class != 'missing_997_ack'"]
        params: list[Any] = []
        if partner:
            conditions.append("partner_id = %s")
            params.append(partner)
        if exception_class:
            conditions.append("exception_class = %s")
            params.append(exception_class)
        where = " and ".join(conditions)
        params.append(limit)
        rows = db.query(f"""
            select
                partner_id,
                exception_class,
                po_number,
                sku,
                invoice_number,
                dollar_impact,
                dispute_window_days,
                dispute_window_expires_at,
                dispute_urgent,
                match_status
            from {_SCHEMA}.fct_exceptions
            where {where}
            order by dollar_impact desc nulls last
            limit %s
        """, tuple(params))
        for row in rows:
            row["dollar_fmt"] = _fmt_dollar(float(row["dollar_impact"] or 0))
            row["class_label"] = _CLASS_LABELS.get(row["exception_class"], row["exception_class"])
        return rows
    except Exception:
        logger.exception("get_exceptions query failed")
        return []


def get_partners() -> list[str]:
    """Distinct partner IDs for the filter dropdown."""
    if not db.is_configured():
        return []
    try:
        rows = db.query(f"select distinct partner_id from {_SCHEMA}.fct_exceptions order by 1")
        return [r["partner_id"] for r in rows]
    except Exception:
        logger.exception("get_partners query failed")
        return []


def get_997_status() -> list[dict[str, Any]]:
    """Rows for the 997 ACK status section (ops layer)."""
    if not db.is_configured():
        return []
    try:
        rows = db.query(f"""
            select
                partner_id,
                document_type,
                isa_control_number,
                doc_date,
                ack_status,
                ack_date,
                ack_missing_or_late
            from {_SCHEMA}.int_997_match
            where ack_missing_or_late or ack_status in ('rejected', 'accepted_with_errors')
            order by ack_status, partner_id, doc_date desc
            limit 100
        """)
        return rows
    except Exception:
        logger.exception("get_997_status query failed")
        return []
