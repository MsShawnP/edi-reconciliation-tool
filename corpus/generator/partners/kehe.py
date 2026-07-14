"""KeHE distributor X12 corpus generator.

Structural quirks:
- 810 carries REF*IA segment with KeHE-assigned distributor invoice number
- 856 uses multi-HL structure: consecutive order pairs share one 856 with
  two O-level HL loops (multi-stop shipment). Odd final order gets single-stop.
- 852 sell-through generated once per order
"""
from __future__ import annotations

import random

from corpus.generator import GenerateResult
from corpus.generator.base import CanonicalOrder, CanonicalShipment
from corpus.generator.ledger import DiscrepancyLedger
from corpus.generator.x12_utils import add_days, make_doc, x12_date_long

_KEHE = "KEHE"
_CIN = "CINDERHAVEN"


class _Counter:
    def __init__(self, start: int) -> None:
        self._n = start

    def next(self) -> int:
        v = self._n
        self._n += 1
        return v


class KeheGenerator:
    def generate(self, orders: list[CanonicalOrder], seed: int) -> GenerateResult:
        rng = random.Random(seed)  # noqa: F841
        isa = _Counter(3001)
        gs = _Counter(1)
        ledger = DiscrepancyLedger()

        docs: dict[str, list[str]] = {
            "850": [], "856": [], "810": [], "820": [], "852": [], "997": [],
        }

        # Process orders in pairs for multi-stop 856s
        i = 0
        while i < len(orders):
            order = orders[i]

            # 850 for this order
            po_isa = isa.next()
            po_gs = gs.next()
            docs["850"].append(_make_850(order, po_isa, po_gs))

            # 856 — pair with next order if available (multi-stop)
            next_order = orders[i + 1] if (i + 1) < len(orders) else None
            if next_order is not None:
                docs["850"].append(_make_850(next_order, isa.next(), gs.next()))

            ship1 = order.shipments[0] if order.shipments else None
            ship2 = next_order.shipments[0] if (next_order and next_order.shipments) else None

            if ship1 and next_order and ship2:
                a_isa = isa.next()
                a_gs = gs.next()
                docs["856"].append(_make_856_multi(order, ship1, next_order, ship2, a_isa, a_gs))
                docs["997"].append(_make_997(_KEHE, _CIN, "SH", a_isa,
                                             isa.next(), gs.next(),
                                             add_days(ship1.ship_date, 1)))
                inv_date1 = add_days(ship1.ship_date, 1)
                inv_date2 = add_days(ship2.ship_date, 1)
            elif ship1:
                a_isa = isa.next()
                a_gs = gs.next()
                docs["856"].append(_make_856_single(order, ship1, a_isa, a_gs))
                docs["997"].append(_make_997(_KEHE, _CIN, "SH", a_isa,
                                             isa.next(), gs.next(),
                                             add_days(ship1.ship_date, 1)))
                inv_date1 = add_days(ship1.ship_date, 1)
                inv_date2 = add_days(order.po_date, 8) if next_order else None
            else:
                inv_date1 = add_days(order.po_date, 7)
                inv_date2 = add_days(order.po_date, 8) if next_order else None

            # 810 and 820 for order
            inv_num1 = f"KEHE-INV-{order.po_number.split('-')[-1]}"
            kehe_dist_num1 = f"KH-{order.po_number.split('-')[-1]}"
            inv_isa = isa.next()
            inv_gs = gs.next()
            docs["810"].append(_make_810(order, inv_isa, inv_gs, inv_num1, kehe_dist_num1, inv_date1))
            docs["997"].append(_make_997(_KEHE, _CIN, "IN", inv_isa,
                                         isa.next(), gs.next(), add_days(inv_date1, 1)))
            pay_date1 = add_days(inv_date1, 30)
            docs["820"].append(_make_820(order, isa.next(), gs.next(), inv_num1, pay_date1))

            # 852 for order
            week_end1 = add_days(inv_date1, 6)
            docs["852"].append(_make_852(order, isa.next(), gs.next(), inv_date1, week_end1))

            # 810, 820, 852 for paired order
            if next_order is not None:
                inv_num2 = f"KEHE-INV-{next_order.po_number.split('-')[-1]}"
                kehe_dist_num2 = f"KH-{next_order.po_number.split('-')[-1]}"
                inv_isa2 = isa.next()
                inv_gs2 = gs.next()
                _inv_date2 = inv_date2 or add_days(next_order.po_date, 7)
                docs["810"].append(_make_810(next_order, inv_isa2, inv_gs2,
                                             inv_num2, kehe_dist_num2, _inv_date2))
                docs["997"].append(_make_997(_KEHE, _CIN, "IN", inv_isa2,
                                             isa.next(), gs.next(), add_days(_inv_date2, 1)))
                pay_date2 = add_days(_inv_date2, 30)
                docs["820"].append(_make_820(next_order, isa.next(), gs.next(), inv_num2, pay_date2))
                week_end2 = add_days(_inv_date2, 6)
                docs["852"].append(_make_852(next_order, isa.next(), gs.next(), _inv_date2, week_end2))
                i += 2
            else:
                i += 1

        return GenerateResult(partner="kehe", documents=docs, ledger=ledger)


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
    return make_doc(_KEHE, _CIN, "PO", isa_ctrl, gs_ctrl, 1, "850", body, order.po_date)


def _make_856_single(order: CanonicalOrder, ship: CanonicalShipment,
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
        body += [f"HL*{hl}*2*I~", f"LIN*{i}*IN*{line.sku}~", f"SN1**{qty}*CA~"]
        hl += 1
    body.append(f"CTT*{hl - 1}~")
    return make_doc(_CIN, _KEHE, "SH", isa_ctrl, gs_ctrl, 1, "856", body, ship.ship_date)


def _make_856_multi(
    order1: CanonicalOrder, ship1: CanonicalShipment,
    order2: CanonicalOrder, ship2: CanonicalShipment,
    isa_ctrl: int, gs_ctrl: int,
) -> str:
    """Two O-level HL loops in one 856 (multi-stop delivery)."""
    carrier = ship1.carrier or "LTL Freight"
    body = [
        f"BSN*00*{ship1.shipment_id}*{x12_date_long(ship1.ship_date)}*1200~",
        "HL*1**S~",
        f"TD5**2*RDWY*{carrier}~",
        f"DTM*011*{x12_date_long(ship1.ship_date)}~",
        # Stop 1
        "HL*2*1*O~",
        f"PRF*{order1.po_number}~",
    ]
    hl = 3
    for i, line in enumerate(order1.lines, 1):
        qty = _distribute(ship1.units_shipped, line.units_ordered, order1.total_units)
        body += [f"HL*{hl}*2*I~", f"LIN*{i}*IN*{line.sku}~", f"SN1**{qty}*CA~"]
        hl += 1
    # Stop 2
    stop2_parent = hl
    body.append(f"HL*{hl}*1*O~")
    body.append(f"PRF*{order2.po_number}~")
    hl += 1
    for i, line in enumerate(order2.lines, 1):
        qty = _distribute(ship2.units_shipped, line.units_ordered, order2.total_units)
        body += [f"HL*{hl}*{stop2_parent}*I~", f"LIN*{i}*IN*{line.sku}~", f"SN1**{qty}*CA~"]
        hl += 1
    body.append(f"CTT*{hl - 1}~")
    return make_doc(_CIN, _KEHE, "SH", isa_ctrl, gs_ctrl, 1, "856", body, ship1.ship_date)


def _make_810(order: CanonicalOrder, isa_ctrl: int, gs_ctrl: int,
              inv_num: str, kehe_dist_inv: str, inv_date: str) -> str:
    total = 0.0
    body = [
        f"BIG*{x12_date_long(inv_date)}*{inv_num}**{order.po_number}~",
        "CUR*SE*USD~",
        f"REF*IA*{kehe_dist_inv}~",  # KeHE-required distributor invoice number
    ]
    for i, line in enumerate(order.lines, 1):
        line_total = line.units_ordered * line.unit_price
        total += line_total
        body.append(f"IT1*{i}*{line.units_ordered}*CA*{line.unit_price:.2f}**IN*{line.sku}~")
    body.append(f"TDS*{int(round(total * 100))}~")
    return make_doc(_CIN, _KEHE, "IN", isa_ctrl, gs_ctrl, 1, "810", body, inv_date)


def _make_820(order: CanonicalOrder, isa_ctrl: int, gs_ctrl: int,
              inv_num: str, pay_date: str) -> str:
    amt = order.total_value
    body = [
        f"BPR*C*{amt:.2f}*C*ACH***01*021000021*DA*123456789*{x12_date_long(pay_date)}~",
        f"TRN*1*TRN{isa_ctrl:09d}*9CINDRH~",
        f"DTM*009*{x12_date_long(pay_date)}~",
        f"REF*IV*{inv_num}~",
        f"RMR*IV*{inv_num}**{amt:.2f}~",
    ]
    return make_doc(_KEHE, _CIN, "RA", isa_ctrl, gs_ctrl, 1, "820", body, pay_date)


def _make_852(order: CanonicalOrder, isa_ctrl: int, gs_ctrl: int,
              week_start: str, week_end: str) -> str:
    report_id = f"KEHE-852-{isa_ctrl:06d}"
    body = [
        f"BIA*00*SS*{report_id}*{x12_date_long(week_start)}~",
        "CUR*SE*USD~",
    ]
    shipped = order.shipments[0].units_shipped if order.shipments else order.total_units
    for i, line in enumerate(order.lines, 1):
        qty = _distribute(shipped, line.units_ordered, order.total_units)
        body += [
            f"LIN*{i}*IN*{line.sku}~",
            f"ZA*S*{qty}*CA~",
            f"DTM*007*{x12_date_long(week_start)}~",
            f"DTM*008*{x12_date_long(week_end)}~",
        ]
    body.append(f"CTT*{len(order.lines)}~")
    return make_doc(_KEHE, _CIN, "PS", isa_ctrl, gs_ctrl, 1, "852", body, week_start)


def _make_997(sender: str, receiver: str, func_id: str, acked_gs: int,
              isa_ctrl: int, gs_ctrl: int, ack_date: str) -> str:
    body = [f"AK1*{func_id}*{acked_gs}~", "AK9*A*1*1*1~"]
    return make_doc(sender, receiver, "FA", isa_ctrl, gs_ctrl, 1, "997", body, ack_date)


def _distribute(total_qty: int, line_ordered: int, order_total: int) -> int:
    if order_total <= 0:
        return total_qty
    return max(1, round(total_qty * line_ordered / order_total))
