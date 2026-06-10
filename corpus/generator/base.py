"""Cinderhaven canonical data reader for the EDI corpus generator.

Connects to the Cinderhaven Postgres instance via DATABASE_URL and yields
normalized CanonicalOrder records. Partner-specific generators consume these
records to produce synthetic X12 documents.

Schema reference: raw.retailer_orders / raw.distributor_orders and their
related lines and shipments tables in cinderhaven-data-platform.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


_RETAILER_MAP = {
    "walmart": "RET-WALMART",
}
_DISTRIBUTOR_MAP = {
    "unfi": "DIST-UNFI",
    "kehe": "DIST-KEHE",
}

SUPPORTED_PARTNERS = frozenset(["walmart", "unfi", "kehe"])


class CorpusError(Exception):
    """Raised when canonical data cannot satisfy corpus generation requirements."""


@dataclass
class CanonicalOrderLine:
    sku: str
    units_ordered: int
    unit_price: float
    line_total: float


@dataclass
class CanonicalShipment:
    shipment_id: str
    ship_date: str
    delivery_date: str | None
    carrier: str | None
    bol_number: str | None
    units_shipped: int


@dataclass
class CanonicalOrder:
    order_id: str
    partner: str
    partner_id: str
    po_number: str
    po_date: str
    total_units: int
    total_value: float
    lines: list[CanonicalOrderLine] = field(default_factory=list)
    shipments: list[CanonicalShipment] = field(default_factory=list)


def _connect():
    """Open a psycopg2 connection using DATABASE_URL from the environment."""
    try:
        import psycopg2
    except ImportError as exc:
        raise CorpusError(
            "psycopg2 is required. Install it with: pip install psycopg2-binary"
        ) from exc

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise CorpusError(
            "DATABASE_URL environment variable is not set. "
            "Set it to the Cinderhaven Postgres connection string before generating the corpus."
        )
    try:
        return psycopg2.connect(db_url)
    except psycopg2.OperationalError as exc:
        raise CorpusError(f"Could not connect to Cinderhaven Postgres: {exc}") from exc


def _read_retailer_orders(cur, partner: str, retailer_id: str) -> list[CanonicalOrder]:
    cur.execute(
        """
        SELECT order_id, po_number, po_date::text, total_units, total_value
        FROM raw.retailer_orders
        WHERE retailer_id = %s
        ORDER BY po_date
        """,
        (retailer_id,),
    )
    rows = cur.fetchall()
    if not rows:
        raise CorpusError(
            f"No retailer orders found for '{retailer_id}' in Cinderhaven. "
            "Verify the Postgres instance is seeded and the partner ID is correct."
        )

    orders: dict[str, CanonicalOrder] = {}
    for order_id, po_number, po_date, total_units, total_value in rows:
        orders[order_id] = CanonicalOrder(
            order_id=order_id,
            partner=partner,
            partner_id=retailer_id,
            po_number=po_number,
            po_date=po_date,
            total_units=total_units,
            total_value=float(total_value),
        )

    order_ids = list(orders.keys())
    cur.execute(
        """
        SELECT order_id, sku, units_ordered, unit_price, line_total
        FROM raw.retailer_order_lines
        WHERE order_id = ANY(%s)
        """,
        (order_ids,),
    )
    for order_id, sku, units_ordered, unit_price, line_total in cur.fetchall():
        if order_id in orders:
            orders[order_id].lines.append(CanonicalOrderLine(
                sku=sku,
                units_ordered=units_ordered,
                unit_price=float(unit_price),
                line_total=float(line_total),
            ))

    cur.execute(
        """
        SELECT order_id, shipment_id, ship_date::text,
               delivery_date::text, carrier, bol_number, units_shipped
        FROM raw.retailer_shipments
        WHERE order_id = ANY(%s)
        """,
        (order_ids,),
    )
    for order_id, shipment_id, ship_date, delivery_date, carrier, bol_number, units_shipped in cur.fetchall():
        if order_id in orders:
            orders[order_id].shipments.append(CanonicalShipment(
                shipment_id=shipment_id,
                ship_date=ship_date,
                delivery_date=delivery_date,
                carrier=carrier,
                bol_number=bol_number,
                units_shipped=units_shipped,
            ))

    result = list(orders.values())
    if not any(o.shipments for o in result):
        raise CorpusError(
            f"No shipments found for retailer '{retailer_id}' in Cinderhaven. "
            "A corpus cannot be generated without shipment records."
        )
    return result


def _read_distributor_orders(cur, partner: str, distributor_id: str) -> list[CanonicalOrder]:
    cur.execute(
        """
        SELECT order_id, po_number, po_date::text, total_units, total_value
        FROM raw.distributor_orders
        WHERE distributor_id = %s
        ORDER BY po_date
        """,
        (distributor_id,),
    )
    rows = cur.fetchall()
    if not rows:
        raise CorpusError(
            f"No distributor orders found for '{distributor_id}' in Cinderhaven. "
            "Verify the Postgres instance is seeded and the partner ID is correct."
        )

    orders: dict[str, CanonicalOrder] = {}
    for order_id, po_number, po_date, total_units, total_value in rows:
        orders[order_id] = CanonicalOrder(
            order_id=order_id,
            partner=partner,
            partner_id=distributor_id,
            po_number=po_number,
            po_date=po_date,
            total_units=total_units,
            total_value=float(total_value),
        )

    order_ids = list(orders.keys())
    cur.execute(
        """
        SELECT order_id, sku, units_ordered, unit_price, line_total
        FROM raw.distributor_order_lines
        WHERE order_id = ANY(%s)
        """,
        (order_ids,),
    )
    for order_id, sku, units_ordered, unit_price, line_total in cur.fetchall():
        if order_id in orders:
            orders[order_id].lines.append(CanonicalOrderLine(
                sku=sku,
                units_ordered=units_ordered,
                unit_price=float(unit_price),
                line_total=float(line_total),
            ))

    cur.execute(
        """
        SELECT order_id, shipment_id, ship_date::text,
               delivery_date::text, carrier, units_shipped
        FROM raw.distributor_shipments
        WHERE order_id = ANY(%s)
        """,
        (order_ids,),
    )
    for order_id, shipment_id, ship_date, delivery_date, carrier, units_shipped in cur.fetchall():
        if order_id in orders:
            orders[order_id].shipments.append(CanonicalShipment(
                shipment_id=shipment_id,
                ship_date=ship_date,
                delivery_date=delivery_date,
                carrier=carrier,
                bol_number=None,
                units_shipped=units_shipped,
            ))

    result = list(orders.values())
    if not any(o.shipments for o in result):
        raise CorpusError(
            f"No shipments found for distributor '{distributor_id}' in Cinderhaven. "
            "A corpus cannot be generated without shipment records."
        )
    return result


def read_partner_orders(partner: str) -> list[CanonicalOrder]:
    """Read canonical orders and shipments for a trading partner from Cinderhaven.

    Args:
        partner: One of "walmart", "unfi", or "kehe".

    Returns:
        List of CanonicalOrder records with lines and shipments populated.

    Raises:
        CorpusError: DATABASE_URL missing, connection fails, unsupported partner,
                     or no records found.
    """
    if partner not in SUPPORTED_PARTNERS:
        raise CorpusError(
            f"Unsupported partner '{partner}'. "
            f"Must be one of: {sorted(SUPPORTED_PARTNERS)}"
        )

    conn = _connect()
    try:
        with conn.cursor() as cur:
            if partner in _RETAILER_MAP:
                return _read_retailer_orders(cur, partner, _RETAILER_MAP[partner])
            return _read_distributor_orders(cur, partner, _DISTRIBUTOR_MAP[partner])
    finally:
        conn.close()


if __name__ == "__main__":
    total = 0
    for p in sorted(SUPPORTED_PARTNERS):
        try:
            orders = read_partner_orders(p)
            print(f"{p}: {len(orders)} canonical orders")
            total += len(orders)
        except CorpusError as e:
            print(f"{p}: ERROR — {e}")
    print(f"Total: {total} orders across {len(SUPPORTED_PARTNERS)} partners")
