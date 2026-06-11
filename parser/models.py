"""Dataclasses for parsed X12 documents.

One dataclass per transaction set. Fields are the matching keys and
quantities needed for four-way reconciliation — not a full EDI spec.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 850 — Purchase Order
# ---------------------------------------------------------------------------

@dataclass
class PoLine:
    line_number: str
    sku: str
    quantity: float
    unit_of_measure: str
    unit_price: float
    promo_allowance: float = 0.0   # SLN percent allowance (UNFI quirk)


@dataclass
class PurchaseOrder:
    isa_control_number: str
    partner_id: str        # ISA06 sender (retailer/distributor sends the PO)
    po_number: str
    po_date: str
    lines: list[PoLine] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 856 — Ship Notice / Manifest
# ---------------------------------------------------------------------------

@dataclass
class AsnItem:
    line_number: str
    sku: str
    quantity: float
    unit_of_measure: str
    hl_id: str = ""
    po_number: str = ""   # PRF segment in the containing O-level HL loop


@dataclass
class ShipNotice:
    isa_control_number: str
    partner_id: str        # ISA08 receiver (Cinderhaven ships to retailer/distributor)
    shipment_id: str       # BSN02
    ship_date: str
    bol_number: str = ""   # REF*BM
    po_number: str = ""    # first PRF found (primary PO anchor)
    items: list[AsnItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 810 — Invoice
# ---------------------------------------------------------------------------

@dataclass
class InvoiceLine:
    line_number: str
    sku: str
    quantity: float
    unit_of_measure: str
    unit_price: float


@dataclass
class Invoice:
    isa_control_number: str
    partner_id: str               # ISA08 receiver
    invoice_number: str           # BIG02
    invoice_date: str             # BIG01
    po_number: str                # BIG04
    total_amount: float           # TDS01 / 100 (negative for credit memos)
    is_credit: bool = False
    original_invoice_number: str = ""     # REF*IV on credit memo
    distributor_invoice_number: str = ""  # REF*IA (KeHE quirk)
    lines: list[InvoiceLine] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 820 — Payment Order / Remittance Advice
# ---------------------------------------------------------------------------

@dataclass
class RemittanceLine:
    invoice_number: str
    amount: float


@dataclass
class Remittance:
    isa_control_number: str
    partner_id: str        # ISA06 sender (retailer/distributor remits)
    payment_amount: float  # BPR02
    payment_date: str      # BPR11
    invoice_number: str    # REF*IV
    po_number: str = ""    # REF*PO (absent on some UNFI remittances — key resolution fallback)
    lines: list[RemittanceLine] = field(default_factory=list)   # RMR segments


# ---------------------------------------------------------------------------
# 852 — Product Activity Data
# ---------------------------------------------------------------------------

@dataclass
class ActivityLine:
    line_number: str
    sku: str
    quantity: float
    unit_of_measure: str
    period_start: str = ""
    period_end: str = ""


@dataclass
class ProductActivity:
    isa_control_number: str
    partner_id: str    # ISA06 sender (distributor sends sell-through)
    report_id: str     # BIA03
    report_date: str   # BIA04
    lines: list[ActivityLine] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 997 — Functional Acknowledgment
# ---------------------------------------------------------------------------

@dataclass
class FuncAck:
    isa_control_number: str
    partner_id: str                  # ISA06 sender (who acknowledged)
    ack_date: str                    # ISA09 interchange date
    acknowledged_functional_id: str  # AK1 element 1 (e.g. "SH", "IN", "PO")
    acknowledged_gs_control: str     # AK1 element 2
    acceptance_code: str = "A"       # AK9 element 1 ("A" = accepted)


# ---------------------------------------------------------------------------
# Parse error
# ---------------------------------------------------------------------------

class X12ParseError(Exception):
    """Raised when an X12 document cannot be parsed.

    segment_index: 0-based index into the segment list at the point of failure.
    context: the raw segment text or surrounding detail for debugging.
    """
    def __init__(self, message: str, segment_index: int = -1, context: str = "") -> None:
        self.segment_index = segment_index
        self.context = context
        super().__init__(message)
