"""X12 parser extension for edi-reconciliation-tool.

Reuses edi-preflight's tokenizer and envelope parser rather than
replacing them. Adds extractors for the four doc types Pre-flight
does not handle: 810, 820, 852, 997.

Pre-flight is imported via sys.path rather than a formal package
install — the repos are siblings under ~/projects/ and Pre-flight
has no setup.py yet. Use the EDI_PREFLIGHT_ROOT env var to override.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Union

# ── Pre-flight import path ────────────────────────────────────────────────
_PREFLIGHT_ROOT = Path(os.environ.get(
    "EDI_PREFLIGHT_ROOT",
    str(Path(__file__).resolve().parents[3] / "published" / "edi-preflight"),
))
if str(_PREFLIGHT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PREFLIGHT_ROOT))

from src.x12_tokenizer import tokenize, TokenizeError   # noqa: E402
from src.envelope import parse_envelope                 # noqa: E402

from parser.models import (  # noqa: E402
    AsnItem,
    ActivityLine,
    FuncAck,
    Invoice,
    InvoiceLine,
    PoLine,
    ProductActivity,
    PurchaseOrder,
    Remittance,
    RemittanceLine,
    ShipNotice,
    X12ParseError,
)

ParsedDocument = Union[
    PurchaseOrder, ShipNotice, Invoice, Remittance, ProductActivity, FuncAck
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_document(raw: str) -> ParsedDocument:
    """Parse a single-transaction X12 interchange into a typed dataclass.

    Raises X12ParseError for structural problems (missing IEA, unknown type,
    malformed segments). Uses Pre-flight's tokenizer and envelope parser for
    the outer structure, then dispatches to a type-specific extractor.
    """
    try:
        result = tokenize(raw)
    except TokenizeError as exc:
        raise X12ParseError(str(exc), context=raw[:120]) from exc

    # Validate IEA is present before going further
    iea_segs = [s for s in result.segments if s.segment_id == "IEA"]
    if not iea_segs:
        last_idx = len(result.segments) - 1
        raise X12ParseError(
            "Missing IEA trailer — interchange envelope is not closed.",
            segment_index=last_idx,
            context=result.segments[last_idx].raw if result.segments else "",
        )

    # Detect transaction set type from ST01
    tx_id = ""
    st_idx = -1
    for i, seg in enumerate(result.segments):
        if seg.segment_id == "ST":
            tx_id = seg.element(1).strip()
            st_idx = i
            break

    if not tx_id:
        raise X12ParseError(
            "No ST segment found — cannot determine transaction type.",
            segment_index=-1,
        )

    envelope = parse_envelope(result)
    if not envelope.transactions:
        raise X12ParseError(
            f"No transaction set found for type {tx_id!r}.",
            segment_index=st_idx,
        )

    tx = envelope.transactions[0]
    segments = tx.segments

    # Extract ISA fields — control number and partner IDs
    isa_ctrl = envelope.interchange.control_number
    sender_id = envelope.interchange.sender_id.strip()
    receiver_id = envelope.interchange.receiver_id.strip()
    isa_date = envelope.interchange.date.strip()

    try:
        if tx_id == "850":
            return _extract_850(segments, isa_ctrl, sender_id)
        elif tx_id == "856":
            return _extract_856(segments, isa_ctrl, receiver_id)
        elif tx_id == "810":
            return _extract_810(segments, isa_ctrl, receiver_id)
        elif tx_id == "820":
            return _extract_820(segments, isa_ctrl, sender_id)
        elif tx_id == "852":
            return _extract_852(segments, isa_ctrl, sender_id)
        elif tx_id == "997":
            return _extract_997(segments, isa_ctrl, sender_id, isa_date)
        else:
            raise X12ParseError(
                f"Unsupported transaction set ID: {tx_id!r}.",
                segment_index=st_idx,
            )
    except X12ParseError:
        raise
    except Exception as exc:
        raise X12ParseError(
            f"Unexpected error parsing {tx_id}: {exc}",
            segment_index=-1,
            context=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# 850 — Purchase Order
# ---------------------------------------------------------------------------

def _extract_850(segments: list, isa_ctrl: str, partner_id: str) -> PurchaseOrder:
    po_number = ""
    po_date = ""
    lines: list[PoLine] = []
    current_line: PoLine | None = None

    for idx, seg in enumerate(segments):
        sid = seg.segment_id

        if sid == "BEG":
            po_number = seg.element(3).strip()
            po_date = seg.element(5).strip()

        elif sid == "PO1":
            sku = _extract_sku_from_product_ids(seg, start=6)
            current_line = PoLine(
                line_number=seg.element(1).strip(),
                sku=sku,
                quantity=_float(seg.element(2)),
                unit_of_measure=seg.element(3).strip(),
                unit_price=_float(seg.element(4)),
            )
            lines.append(current_line)

        elif sid == "SLN" and current_line is not None:
            # UNFI promo allowance: SLN04 is negative price (e.g. -0.4250), SLN05 = PE (percent)
            raw_amt = seg.element(4).strip().lstrip("-")
            current_line.promo_allowance = _float(raw_amt)

    if not po_number:
        raise X12ParseError("850 missing BEG segment — po_number not found.", segment_index=0)

    return PurchaseOrder(
        isa_control_number=isa_ctrl,
        partner_id=partner_id,
        po_number=po_number,
        po_date=po_date,
        lines=lines,
    )


# ---------------------------------------------------------------------------
# 856 — Ship Notice / Manifest
# ---------------------------------------------------------------------------

def _extract_856(segments: list, isa_ctrl: str, partner_id: str) -> ShipNotice:
    shipment_id = ""
    ship_date = ""
    bol_number = ""
    po_number = ""
    items: list[AsnItem] = []

    current_po: str = ""       # PRF in the current O-level HL
    current_hl_id: str = ""
    current_sku: str = ""
    current_line_num: str = ""

    for seg in segments:
        sid = seg.segment_id

        if sid == "BSN":
            shipment_id = seg.element(2).strip()
            ship_date = seg.element(3).strip()

        elif sid == "REF":
            if seg.element(1).strip() == "BM":
                bol_number = seg.element(2).strip()

        elif sid == "HL":
            current_hl_id = seg.element(1).strip()
            hl_type = seg.element(3).strip()
            if hl_type == "O":
                current_po = ""    # new order loop; PRF will set it
            elif hl_type == "I":
                current_sku = ""   # new item loop; LIN will set it
                current_line_num = ""

        elif sid == "PRF":
            # PO reference in an O-level HL
            current_po = seg.element(1).strip()
            if not po_number:
                po_number = current_po   # first PRF is the primary anchor

        elif sid == "LIN":
            current_line_num = seg.element(1).strip()
            current_sku = _extract_sku_from_product_ids(seg, start=2)

        elif sid == "SN1" and current_sku:
            item = AsnItem(
                line_number=current_line_num,
                sku=current_sku,
                quantity=_float(seg.element(2)),
                unit_of_measure=seg.element(3).strip(),
                hl_id=current_hl_id,
                po_number=current_po,
            )
            items.append(item)

    return ShipNotice(
        isa_control_number=isa_ctrl,
        partner_id=partner_id,
        shipment_id=shipment_id,
        ship_date=ship_date,
        bol_number=bol_number,
        po_number=po_number,
        items=items,
    )


# ---------------------------------------------------------------------------
# 810 — Invoice
# ---------------------------------------------------------------------------

def _extract_810(segments: list, isa_ctrl: str, partner_id: str) -> Invoice:
    invoice_number = ""
    invoice_date = ""
    po_number = ""
    total_amount = 0.0
    original_inv_num = ""
    dist_inv_num = ""
    lines: list[InvoiceLine] = []
    current_line: InvoiceLine | None = None

    for seg in segments:
        sid = seg.segment_id

        if sid == "BIG":
            invoice_date = seg.element(1).strip()
            invoice_number = seg.element(2).strip()
            po_number = seg.element(4).strip()

        elif sid == "REF":
            qualifier = seg.element(1).strip()
            value = seg.element(2).strip()
            if qualifier == "IA":
                dist_inv_num = value          # KeHE distributor invoice number
            elif qualifier == "IV":
                original_inv_num = value      # credit memo: reference to original

        elif sid == "IT1":
            sku = _extract_sku_from_product_ids(seg, start=6)
            current_line = InvoiceLine(
                line_number=seg.element(1).strip(),
                sku=sku,
                quantity=_float(seg.element(2)),
                unit_of_measure=seg.element(3).strip(),
                unit_price=_float(seg.element(4)),
            )
            lines.append(current_line)

        elif sid == "TDS":
            # TDS01 is amount in cents (integer); negative for credit memos
            raw = seg.element(1).strip()
            total_amount = _float(raw) / 100.0

    is_credit = total_amount < 0

    return Invoice(
        isa_control_number=isa_ctrl,
        partner_id=partner_id,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        po_number=po_number,
        total_amount=total_amount,
        is_credit=is_credit,
        original_invoice_number=original_inv_num,
        distributor_invoice_number=dist_inv_num,
        lines=lines,
    )


# ---------------------------------------------------------------------------
# 820 — Payment Order / Remittance Advice
# ---------------------------------------------------------------------------

def _extract_820(segments: list, isa_ctrl: str, partner_id: str) -> Remittance:
    payment_amount = 0.0
    payment_date = ""
    invoice_number = ""
    po_number = ""
    lines: list[RemittanceLine] = []

    for seg in segments:
        sid = seg.segment_id

        if sid == "BPR":
            payment_amount = _float(seg.element(2))
            # BPR11 is the actual payment date in YYYYMMDD
            payment_date = seg.element(11).strip()

        elif sid == "REF":
            qualifier = seg.element(1).strip()
            value = seg.element(2).strip()
            if qualifier == "IV":
                invoice_number = value
            elif qualifier == "PO":
                po_number = value

        elif sid == "RMR":
            lines.append(RemittanceLine(
                invoice_number=seg.element(2).strip(),
                amount=_float(seg.element(4)),
            ))

    return Remittance(
        isa_control_number=isa_ctrl,
        partner_id=partner_id,
        payment_amount=payment_amount,
        payment_date=payment_date,
        invoice_number=invoice_number,
        po_number=po_number,
        lines=lines,
    )


# ---------------------------------------------------------------------------
# 852 — Product Activity Data
# ---------------------------------------------------------------------------

def _extract_852(segments: list, isa_ctrl: str, partner_id: str) -> ProductActivity:
    report_id = ""
    report_date = ""
    lines: list[ActivityLine] = []

    current_sku = ""
    current_line_num = ""
    current_qty = 0.0
    current_uom = ""
    period_start = ""
    period_end = ""
    in_lin_loop = False

    def _flush_line() -> None:
        if current_sku:
            lines.append(ActivityLine(
                line_number=current_line_num,
                sku=current_sku,
                quantity=current_qty,
                unit_of_measure=current_uom,
                period_start=period_start,
                period_end=period_end,
            ))

    for seg in segments:
        sid = seg.segment_id

        if sid == "BIA":
            report_date = seg.element(4).strip()
            report_id = seg.element(3).strip()

        elif sid == "LIN":
            if in_lin_loop:
                _flush_line()
            in_lin_loop = True
            current_line_num = seg.element(1).strip()
            current_sku = _extract_sku_from_product_ids(seg, start=2)
            current_qty = 0.0
            current_uom = ""
            period_start = ""
            period_end = ""

        elif sid == "ZA" and in_lin_loop:
            # ZA: ZA01=action code (S=sold), ZA02=quantity, ZA03=UoM
            current_qty = _float(seg.element(2))
            current_uom = seg.element(3).strip()

        elif sid == "DTM" and in_lin_loop:
            qualifier = seg.element(1).strip()
            date_val = seg.element(2).strip()
            if qualifier == "007":
                period_start = date_val
            elif qualifier == "008":
                period_end = date_val

    if in_lin_loop:
        _flush_line()

    return ProductActivity(
        isa_control_number=isa_ctrl,
        partner_id=partner_id,
        report_id=report_id,
        report_date=report_date,
        lines=lines,
    )


# ---------------------------------------------------------------------------
# 997 — Functional Acknowledgment
# ---------------------------------------------------------------------------

def _extract_997(
    segments: list, isa_ctrl: str, partner_id: str, isa_date: str
) -> FuncAck:
    ack_functional_id = ""
    ack_gs_ctrl = ""
    acceptance_code = "A"

    for seg in segments:
        sid = seg.segment_id

        if sid == "AK1":
            ack_functional_id = seg.element(1).strip()
            ack_gs_ctrl = seg.element(2).strip()

        elif sid == "AK9":
            acceptance_code = seg.element(1).strip()

    return FuncAck(
        isa_control_number=isa_ctrl,
        partner_id=partner_id,
        ack_date=isa_date,
        acknowledged_functional_id=ack_functional_id,
        acknowledged_gs_control=ack_gs_ctrl,
        acceptance_code=acceptance_code,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _float(value: str) -> float:
    try:
        return float(value) if value else 0.0
    except ValueError:
        return 0.0


def _extract_sku_from_product_ids(seg: object, start: int) -> str:
    """Extract SKU from qualifier/value pairs starting at `start` (1-based).

    Pairs are (qualifier at index, value at index+1). Returns the value
    for the 'IN' (buyer's item number) qualifier, or empty string.
    """
    i = start
    while True:
        qualifier = seg.element(i).strip()
        if not qualifier:
            break
        value = seg.element(i + 1).strip()
        if qualifier == "IN":
            return value
        i += 2
    return ""
