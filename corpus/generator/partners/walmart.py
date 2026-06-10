"""Walmart direct-to-retailer X12 corpus generator.

Structural quirks:
- 850 PO lines in cases (CA); 810 invoice lines in eaches (EA) — UoM structural difference
- First order's shipment is split into two 856 ASNs (60 / 40 partial shipment)
- 997 ACKs arrive within 24 hours of the inbound document
"""
from __future__ import annotations

import random

from corpus.generator import GenerateResult
from corpus.generator.base import CanonicalOrder, CanonicalShipment
from corpus.generator.ledger import DiscrepancyLedger
from corpus.generator.x12_utils import (
    CASE_PACK,
    _DEFAULT_CASE_PACK,
    add_days,
    make_doc,
    x12_date_long,
)

_WMT = "WALMARTUS"
_CIN = "CINDERHAVEN"
_SCAC = "FXFE"


class _Counter:
    def __init__(self, start: int) -> None:
        self._n = start

    def next(self) -> int:
        v = self._n
        self._n += 1
        return v


class WalmartGenerator:
    def generate(self, orders: list[CanonicalOrder], seed: int) -> GenerateResult:
        rng = random.Random(seed)  # noqa: F841 — kept for future stochastic quirks
        isa = _Counter(1001)
        gs = _Counter(1)
        ledger = DiscrepancyLedger()

        docs: dict[str, list[str]] = {
            "850": [], "856": [], "810": [], "820": [], "997": [],
        }

        for idx, order in enumerate(orders):
            # 850 — Walmart sends PO to Cinderhaven
            po_isa = isa.next()
            po_gs = gs.next()
            docs["850"].append(_make_850(order, po_isa, po_gs))

            # 856 — Cinderhaven sends ASN(s) to Walmart
            shipments = order.shipments or []
            if idx == 0 and shipments:
                # Partial shipment: split first shipment 60/40 into two 856s
                ship = shipments[0]
                total = ship.units_shipped
                qty1 = max(1, int(total * 0.6))
                qty2 = total - qty1
                for qty in (qty1, qty2):
                    a_isa = isa.next()
                    a_gs = gs.next()
                    docs["856"].append(_make_856(order, ship, qty, a_isa, a_gs))
                    docs["997"].append(_make_997(_WMT, _CIN, "SH", a_gs,
                                                 isa.next(), gs.next(),
                                                 add_days(ship.ship_date, 1)))
                inv_date = add_days(shipments[0].ship_date, 1)
            elif shipments:
                for ship in shipments:
                    a_isa = isa.next()
                    a_gs = gs.next()
                    docs["856"].append(_make_856(order, ship, ship.units_shipped, a_isa, a_gs))
                    docs["997"].append(_make_997(_WMT, _CIN, "SH", a_gs,
                                                 isa.next(), gs.next(),
                                                 add_days(ship.ship_date, 1)))
                inv_date = add_days(shipments[0].ship_date, 1)
            else:
                inv_date = add_days(order.po_date, 7)

            # 810 — Cinderhaven invoices Walmart in EACHES (structural UoM quirk)
            inv_num = f"WMT-INV-{isa.next():06d}"
            inv_isa = isa.next()
            inv_gs = gs.next()
            docs["810"].append(_make_810_eaches(order, inv_isa, inv_gs, inv_num, inv_date))
            docs["997"].append(_make_997(_WMT, _CIN, "IN", inv_gs,
                                         isa.next(), gs.next(),
                                         add_days(inv_date, 1)))

            # 820 — Walmart remits payment (net 30 from invoice)
            pay_date = add_days(inv_date, 30)
            docs["820"].append(_make_820(order, isa.next(), gs.next(), inv_num, pay_date))

        return GenerateResult(partner="walmart", documents=docs, ledger=ledger)


# ---------------------------------------------------------------------------
# Document builders
# ---------------------------------------------------------------------------

def _make_850(order: CanonicalOrder, isa_ctrl: int, gs_ctrl: int) -> str:
    body = [
        f"BEG*00*SA*{order.po_number}**{x12_date_long(order.po_date)}~",
        "CUR*BY*USD~",
    ]
    for i, line in enumerate(order.lines, 1):
        body.append(f"PO1*{i}*{line.units_ordered}*CA*{line.unit_price:.2f}**IN*{line.sku}~")
    body.append(f"CTT*{len(order.lines)}~")
    return make_doc(_WMT, _CIN, "PO", isa_ctrl, gs_ctrl, 1, "850", body, order.po_date)


def _make_856(
    order: CanonicalOrder,
    ship: CanonicalShipment,
    total_qty: int,
    isa_ctrl: int,
    gs_ctrl: int,
) -> str:
    bol = ship.bol_number or f"BOL{isa_ctrl:06d}"
    carrier = ship.carrier or "FedEx"
    body = [
        f"BSN*00*{ship.shipment_id}*{x12_date_long(ship.ship_date)}*1200~",
        "HL*1**S~",
        f"TD5**2*{_SCAC}*{carrier}~",
        f"REF*BM*{bol}~",
        f"DTM*011*{x12_date_long(ship.ship_date)}~",
        "HL*2*1*O~",
        f"PRF*{order.po_number}~",
    ]
    hl = 3
    for i, line in enumerate(order.lines, 1):
        line_qty = _distribute(total_qty, line.units_ordered, order.total_units)
        body += [
            f"HL*{hl}*2*I~",
            f"LIN*{i}*IN*{line.sku}~",
            f"SN1**{line_qty}*CA~",
        ]
        hl += 1
    body.append(f"CTT*{hl - 1}~")
    return make_doc(_CIN, _WMT, "SH", isa_ctrl, gs_ctrl, 1, "856", body, ship.ship_date)


def _make_810_eaches(
    order: CanonicalOrder,
    isa_ctrl: int,
    gs_ctrl: int,
    inv_num: str,
    inv_date: str,
) -> str:
    total = 0.0
    body = [
        f"BIG*{x12_date_long(inv_date)}*{inv_num}**{order.po_number}~",
        "CUR*SE*USD~",
    ]
    for i, line in enumerate(order.lines, 1):
        cp = CASE_PACK.get(line.sku, _DEFAULT_CASE_PACK)
        qty_ea = line.units_ordered * cp
        price_ea = line.unit_price / cp
        line_total = qty_ea * price_ea
        total += line_total
        body.append(f"IT1*{i}*{qty_ea}*EA*{price_ea:.4f}**IN*{line.sku}~")
    body.append(f"TDS*{int(round(total * 100))}~")
    return make_doc(_CIN, _WMT, "IN", isa_ctrl, gs_ctrl, 1, "810", body, inv_date)


def _make_820(
    order: CanonicalOrder,
    isa_ctrl: int,
    gs_ctrl: int,
    inv_num: str,
    pay_date: str,
) -> str:
    amt = order.total_value
    body = [
        f"BPR*C*{amt:.2f}*C*ACH***01*021000021*DA*123456789*{x12_date_long(pay_date)}~",
        f"TRN*1*TRN{isa_ctrl:09d}*9CINDRH~",
        f"DTM*009*{x12_date_long(pay_date)}~",
        f"REF*IV*{inv_num}~",
        f"RMR*IV*{inv_num}**{amt:.2f}~",
    ]
    return make_doc(_WMT, _CIN, "RA", isa_ctrl, gs_ctrl, 1, "820", body, pay_date)


def _make_997(
    sender: str,
    receiver: str,
    func_id: str,
    acked_gs: int,
    isa_ctrl: int,
    gs_ctrl: int,
    ack_date: str,
) -> str:
    body = [
        f"AK1*{func_id}*{acked_gs}~",
        "AK9*A*1*1*1~",
    ]
    return make_doc(sender, receiver, "FA", isa_ctrl, gs_ctrl, 1, "997", body, ack_date)


def _distribute(total_qty: int, line_ordered: int, order_total: int) -> int:
    """Proportionally distribute total_qty across a line based on its share of order_total."""
    if order_total <= 0:
        return total_qty
    return max(1, round(total_qty * line_ordered / order_total))
