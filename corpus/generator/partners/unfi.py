"""UNFI distributor X12 corpus generator.

Structural quirks:
- 850 includes SLN sub-line after each PO1 for promo allowance (5%, TD code)
- 3rd order (0-indexed idx==2) produces a credit 810 + rebill 810 pair
- Every 3rd 820 (idx % 3 == 2) omits the REF*PO segment — tests key resolution fallback
- 852 sell-through generated once per order (approximates weekly reporting)
"""
from __future__ import annotations

import random

from corpus.generator import GenerateResult
from corpus.generator.base import CanonicalOrder, CanonicalShipment
from corpus.generator.ledger import DiscrepancyLedger
from corpus.generator.x12_utils import add_days, make_doc, x12_date_long

_UNFI = "UNFI"
_CIN = "CINDERHAVEN"
_PROMO_PCT = 0.05  # 5% promo allowance on 850 lines


class _Counter:
    def __init__(self, start: int) -> None:
        self._n = start

    def next(self) -> int:
        v = self._n
        self._n += 1
        return v


class UnfiGenerator:
    def generate(self, orders: list[CanonicalOrder], seed: int) -> GenerateResult:
        rng = random.Random(seed)  # noqa: F841
        isa = _Counter(2001)
        gs = _Counter(1)
        ledger = DiscrepancyLedger()

        docs: dict[str, list[str]] = {
            "850": [], "856": [], "810": [], "820": [], "852": [], "997": [],
        }

        for idx, order in enumerate(orders):
            # 850 with SLN promo segments
            po_isa = isa.next()
            po_gs = gs.next()
            docs["850"].append(_make_850(order, po_isa, po_gs))

            # 856
            shipments = order.shipments or []
            if shipments:
                ship = shipments[0]
                a_isa = isa.next()
                a_gs = gs.next()
                docs["856"].append(_make_856(order, ship, a_isa, a_gs))
                docs["997"].append(_make_997(_UNFI, _CIN, "SH", a_gs,
                                             isa.next(), gs.next(),
                                             add_days(ship.ship_date, 1)))
                inv_date = add_days(ship.ship_date, 1)
                ship_date = ship.ship_date
            else:
                inv_date = add_days(order.po_date, 7)
                ship_date = order.po_date

            # 810 — credit/rebill for 3rd order; normal otherwise
            if idx == 2:
                # Original invoice
                orig_num = f"UNFI-INV-{isa.next():06d}"
                orig_isa = isa.next()
                orig_gs = gs.next()
                docs["810"].append(_make_810(order, orig_isa, orig_gs, orig_num, inv_date))
                docs["997"].append(_make_997(_UNFI, _CIN, "IN", orig_gs,
                                             isa.next(), gs.next(), add_days(inv_date, 1)))
                # Credit memo (negative)
                cr_num = f"{orig_num}-CR"
                cr_isa = isa.next()
                cr_gs = gs.next()
                docs["810"].append(_make_810_credit(order, cr_isa, cr_gs, cr_num, orig_num, inv_date))
                # Rebill
                rb_num = f"{orig_num}-RB"
                rb_isa = isa.next()
                rb_gs = gs.next()
                docs["810"].append(_make_810(order, rb_isa, rb_gs, rb_num, add_days(inv_date, 2)))
                docs["997"].append(_make_997(_UNFI, _CIN, "IN", rb_gs,
                                             isa.next(), gs.next(), add_days(inv_date, 3)))
                inv_num = rb_num
            else:
                inv_num = f"UNFI-INV-{isa.next():06d}"
                inv_isa = isa.next()
                inv_gs = gs.next()
                docs["810"].append(_make_810(order, inv_isa, inv_gs, inv_num, inv_date))
                docs["997"].append(_make_997(_UNFI, _CIN, "IN", inv_gs,
                                             isa.next(), gs.next(), add_days(inv_date, 1)))

            # 820 — every 3rd omits PO reference (key resolution fallback scenario)
            pay_date = add_days(inv_date, 30)
            omit_po_ref = (idx % 3 == 2)
            docs["820"].append(_make_820(order, isa.next(), gs.next(),
                                         inv_num, pay_date, omit_po_ref))

            # 852 — weekly sell-through (one per order, covers the ship week)
            week_start = ship_date
            week_end = add_days(week_start, 6)
            docs["852"].append(_make_852(order, isa.next(), gs.next(),
                                         week_start, week_end))

        return GenerateResult(partner="unfi", documents=docs, ledger=ledger)


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
        # SLN promo allowance: 5% off each line
        promo = round(line.unit_price * _PROMO_PCT, 4)
        body.append(f"SLN*{i}**A*-{promo:.4f}*PE*TD*PROMO-ALLOW~")
    body.append(f"CTT*{len(order.lines)}~")
    return make_doc(_UNFI, _CIN, "PO", isa_ctrl, gs_ctrl, 1, "850", body, order.po_date)


def _make_856(order: CanonicalOrder, ship: CanonicalShipment,
              isa_ctrl: int, gs_ctrl: int) -> str:
    carrier = ship.carrier or "LTL Freight"
    body = [
        f"BSN*00*{ship.shipment_id}*{x12_date_long(ship.ship_date)}*1200~",
        "HL*1**S~",
        f"TD5**2*RDWY*{carrier}~",
        f"DTM*011*{x12_date_long(ship.ship_date)}~",
        "HL*2*1*O~",
        f"PRF*{order.po_number}~",
    ]
    hl = 3
    for i, line in enumerate(order.lines, 1):
        qty = _distribute(ship.units_shipped, line.units_ordered, order.total_units)
        body += [
            f"HL*{hl}*2*I~",
            f"LIN*{i}*IN*{line.sku}~",
            f"SN1**{qty}*CA~",
        ]
        hl += 1
    body.append(f"CTT*{hl - 1}~")
    return make_doc(_CIN, _UNFI, "SH", isa_ctrl, gs_ctrl, 1, "856", body, ship.ship_date)


def _make_810(order: CanonicalOrder, isa_ctrl: int, gs_ctrl: int,
              inv_num: str, inv_date: str) -> str:
    total = 0.0
    body = [
        f"BIG*{x12_date_long(inv_date)}*{inv_num}**{order.po_number}~",
        "CUR*SE*USD~",
    ]
    for i, line in enumerate(order.lines, 1):
        line_total = line.units_ordered * line.unit_price
        total += line_total
        body.append(f"IT1*{i}*{line.units_ordered}*CA*{line.unit_price:.2f}**IN*{line.sku}~")
    body.append(f"TDS*{int(round(total * 100))}~")
    return make_doc(_CIN, _UNFI, "IN", isa_ctrl, gs_ctrl, 1, "810", body, inv_date)


def _make_810_credit(order: CanonicalOrder, isa_ctrl: int, gs_ctrl: int,
                     cr_num: str, orig_inv_num: str, inv_date: str) -> str:
    """Credit memo: negative TDS, references the original invoice number."""
    total = sum(line.units_ordered * line.unit_price for line in order.lines)
    body = [
        f"BIG*{x12_date_long(inv_date)}*{cr_num}**{order.po_number}~",
        "CUR*SE*USD~",
        f"REF*IV*{orig_inv_num}~",
    ]
    for i, line in enumerate(order.lines, 1):
        body.append(f"IT1*{i}*{line.units_ordered}*CA*{line.unit_price:.2f}**IN*{line.sku}~")
    body.append(f"TDS*-{int(round(total * 100))}~")
    return make_doc(_CIN, _UNFI, "IN", isa_ctrl, gs_ctrl, 1, "810", body, inv_date)


def _make_820(order: CanonicalOrder, isa_ctrl: int, gs_ctrl: int,
              inv_num: str, pay_date: str, omit_po_ref: bool = False) -> str:
    amt = order.total_value
    body = [
        f"BPR*C*{amt:.2f}*C*ACH***01*021000021*DA*123456789*{x12_date_long(pay_date)}~",
        f"TRN*1*TRN{isa_ctrl:09d}*9CINDRH~",
        f"DTM*009*{x12_date_long(pay_date)}~",
        f"REF*IV*{inv_num}~",
    ]
    if not omit_po_ref:
        body.append(f"REF*PO*{order.po_number}~")
    body.append(f"RMR*IV*{inv_num}**{amt:.2f}~")
    return make_doc(_UNFI, _CIN, "RA", isa_ctrl, gs_ctrl, 1, "820", body, pay_date)


def _make_852(order: CanonicalOrder, isa_ctrl: int, gs_ctrl: int,
              week_start: str, week_end: str) -> str:
    report_id = f"UNFI-852-{isa_ctrl:06d}"
    body = [
        f"BIA*00*SS*{report_id}*{x12_date_long(week_start)}~",
        "CUR*SE*USD~",
    ]
    for i, line in enumerate(order.lines, 1):
        sell_qty = _distribute(
            getattr(order.shipments[0], "units_shipped", line.units_ordered)
            if order.shipments else line.units_ordered,
            line.units_ordered,
            order.total_units,
        )
        body += [
            f"LIN*{i}*IN*{line.sku}~",
            f"ZA*S*{sell_qty}*CA~",
            f"DTM*007*{x12_date_long(week_start)}~",
            f"DTM*008*{x12_date_long(week_end)}~",
        ]
    body.append(f"CTT*{len(order.lines)}~")
    return make_doc(_UNFI, _CIN, "PS", isa_ctrl, gs_ctrl, 1, "852", body, week_start)


def _make_997(sender: str, receiver: str, func_id: str, acked_gs: int,
              isa_ctrl: int, gs_ctrl: int, ack_date: str) -> str:
    body = [
        f"AK1*{func_id}*{acked_gs}~",
        "AK9*A*1*1*1~",
    ]
    return make_doc(sender, receiver, "FA", isa_ctrl, gs_ctrl, 1, "997", body, ack_date)


def _distribute(total_qty: int, line_ordered: int, order_total: int) -> int:
    if order_total <= 0:
        return total_qty
    return max(1, round(total_qty * line_ordered / order_total))
