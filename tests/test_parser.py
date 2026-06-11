"""Tests for parser.x12_parser (U3).

All tests use X12 strings produced by the U2 corpus generators — no
hardcoded X12 literals, no database required.
"""
from __future__ import annotations

import pytest

from corpus.generator.base import (
    CanonicalOrder,
    CanonicalOrderLine,
    CanonicalShipment,
)
from parser.x12_parser import parse_document
from parser.models import (
    FuncAck,
    Invoice,
    ProductActivity,
    PurchaseOrder,
    Remittance,
    ShipNotice,
    X12ParseError,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_order(
    order_id: str = "RO-001",
    partner: str = "walmart",
    partner_id: str = "RET-WALMART",
    po_number: str = "PO-0001",
    po_date: str = "2024-03-01",
    skus: list[tuple[str, int, float]] | None = None,
    units_shipped: int = 48,
) -> CanonicalOrder:
    if skus is None:
        skus = [("CHP-AS-001", 24, 8.00), ("CHP-AS-002", 24, 7.00)]
    lines = [
        CanonicalOrderLine(sku=s, units_ordered=q, unit_price=p, line_total=q * p)
        for s, q, p in skus
    ]
    total_units = sum(q for _, q, _ in skus)
    total_value = sum(q * p for _, q, p in skus)
    shipment = CanonicalShipment(
        shipment_id=f"SHP-{order_id}",
        ship_date="2024-03-05",
        delivery_date="2024-03-07",
        carrier="FedEx",
        bol_number=f"BOL-{order_id}",
        units_shipped=units_shipped,
    )
    return CanonicalOrder(
        order_id=order_id,
        partner=partner,
        partner_id=partner_id,
        po_number=po_number,
        po_date=po_date,
        total_units=total_units,
        total_value=total_value,
        lines=lines,
        shipments=[shipment],
    )


def _walmart_docs(n: int = 2):
    from corpus.generator.partners.walmart import WalmartGenerator
    orders = [
        _make_order(f"RO-{i:03d}", "walmart", "RET-WALMART", f"PO-WMT-{i:04d}",
                    po_date="2024-03-01")
        for i in range(1, n + 1)
    ]
    return WalmartGenerator().generate(orders, seed=42).documents


def _unfi_docs(n: int = 4):
    from corpus.generator.partners.unfi import UnfiGenerator
    orders = [
        _make_order(f"DO-{i:03d}", "unfi", "DIST-UNFI", f"PO-UNFI-{i:04d}",
                    po_date="2024-03-01")
        for i in range(1, n + 1)
    ]
    return UnfiGenerator().generate(orders, seed=42).documents


def _kehe_docs(n: int = 4):
    from corpus.generator.partners.kehe import KeheGenerator
    orders = [
        _make_order(f"KO-{i:03d}", "kehe", "DIST-KEHE", f"PO-KEHE-{i:04d}",
                    po_date="2024-03-01")
        for i in range(1, n + 1)
    ]
    return KeheGenerator().generate(orders, seed=42).documents


# ---------------------------------------------------------------------------
# Happy path: 850 — Purchase Order
# ---------------------------------------------------------------------------

class TestParse850:
    def test_walmart_850_returns_purchase_order(self):
        """Walmart 850 → PurchaseOrder with correct po_number and two line items."""
        docs = _walmart_docs()
        result = parse_document(docs["850"][0])

        assert isinstance(result, PurchaseOrder)
        assert result.po_number == "PO-WMT-0001"
        assert len(result.lines) == 2

    def test_850_line_has_correct_qty_uom_price(self):
        docs = _walmart_docs()
        result = parse_document(docs["850"][0])

        line = result.lines[0]
        assert line.sku == "CHP-AS-001"
        assert line.quantity == 24.0
        assert line.unit_of_measure == "CA"
        assert line.unit_price == pytest.approx(8.00)

    def test_850_isa_control_and_partner_captured(self):
        docs = _walmart_docs()
        result = parse_document(docs["850"][0])

        assert result.isa_control_number        # non-empty
        assert "WALMART" in result.partner_id.upper()


# ---------------------------------------------------------------------------
# Happy path: 856 — Ship Notice (multi-HL)
# ---------------------------------------------------------------------------

class TestParse856:
    def test_walmart_856_returns_ship_notice(self):
        """Walmart 856 → ShipNotice with shipment_id and po_number."""
        docs = _walmart_docs()
        result = parse_document(docs["856"][0])

        assert isinstance(result, ShipNotice)
        assert result.shipment_id                 # non-empty
        assert result.po_number == "PO-WMT-0001"

    def test_856_items_populated(self):
        docs = _walmart_docs()
        result = parse_document(docs["856"][0])

        assert len(result.items) >= 1
        for item in result.items:
            assert item.sku.startswith("CHP-")
            assert item.quantity > 0
            assert item.unit_of_measure == "CA"

    def test_kehe_856_multi_hl_captures_both_po_references(self):
        """KeHE multi-stop 856 → items carry their respective PO numbers via HL/PRF."""
        docs = _kehe_docs(4)
        result = parse_document(docs["856"][0])

        assert isinstance(result, ShipNotice)
        po_numbers = {item.po_number for item in result.items}
        # Multi-stop covers two orders → should reference at least two POs
        assert len(po_numbers) >= 2

    def test_856_bol_number_captured(self):
        docs = _walmart_docs()
        result = parse_document(docs["856"][0])

        assert result.bol_number   # REF*BM populated


# ---------------------------------------------------------------------------
# Happy path: 820 — Remittance Advice
# ---------------------------------------------------------------------------

class TestParse820:
    def test_walmart_820_returns_remittance(self):
        docs = _walmart_docs()
        result = parse_document(docs["820"][0])

        assert isinstance(result, Remittance)
        assert result.payment_amount > 0
        assert result.invoice_number        # REF*IV present on Walmart 820

    def test_820_rmr_lines_captured(self):
        docs = _walmart_docs()
        result = parse_document(docs["820"][0])

        assert len(result.lines) >= 1
        for line in result.lines:
            assert line.invoice_number
            assert line.amount > 0

    def test_unfi_820_without_po_ref_has_empty_po_number(self):
        """UNFI every-3rd-820 omits REF*PO — po_number must be empty (key resolution fallback)."""
        docs = _unfi_docs(6)
        # idx 2 (0-based 3rd order) has no REF*PO
        no_po_remittances = [
            parse_document(d)
            for d in docs["820"]
            if "REF*PO*" not in d
        ]
        assert no_po_remittances, "Expected at least one 820 without REF*PO"
        for rem in no_po_remittances:
            assert isinstance(rem, Remittance)
            assert rem.po_number == ""


# ---------------------------------------------------------------------------
# Happy path: 997 — Functional Acknowledgment
# ---------------------------------------------------------------------------

class TestParse997:
    def test_walmart_997_returns_func_ack(self):
        docs = _walmart_docs()
        result = parse_document(docs["997"][0])

        assert isinstance(result, FuncAck)
        assert result.acknowledged_functional_id in {"SH", "IN", "PO", "RA", "PS"}
        assert result.acknowledged_gs_control
        assert result.acceptance_code == "A"

    def test_997_ack_date_captured(self):
        docs = _walmart_docs()
        result = parse_document(docs["997"][0])

        assert result.ack_date      # ISA09 interchange date, non-empty


# ---------------------------------------------------------------------------
# Edge case: UNFI 850 SLN promo segment
# ---------------------------------------------------------------------------

class TestUnfiSln:
    def test_unfi_850_sln_captured_without_breaking_po1(self):
        """UNFI 850 SLN promo → promo_allowance > 0 on line; PO1 quantity intact."""
        docs = _unfi_docs()
        result = parse_document(docs["850"][0])

        assert isinstance(result, PurchaseOrder)
        assert len(result.lines) == 2
        for line in result.lines:
            assert line.promo_allowance > 0, "SLN promo allowance not captured"
            assert line.quantity > 0          # PO1 quantity intact


# ---------------------------------------------------------------------------
# Edge case: 810 credit (negative TDS)
# ---------------------------------------------------------------------------

class TestInvoiceCredit:
    def test_unfi_810_credit_has_negative_total_and_credit_flag(self):
        """UNFI 3rd-order credit 810 → total_amount < 0, is_credit = True."""
        docs = _unfi_docs(4)
        credit_docs = [d for d in docs["810"] if "TDS*-" in d]
        assert credit_docs, "Expected at least one credit 810 from UNFI 3rd order"

        result = parse_document(credit_docs[0])
        assert isinstance(result, Invoice)
        assert result.total_amount < 0
        assert result.is_credit is True

    def test_kehe_810_has_distributor_invoice_number(self):
        """KeHE 810 → distributor_invoice_number populated from REF*IA."""
        docs = _kehe_docs()
        result = parse_document(docs["810"][0])

        assert isinstance(result, Invoice)
        assert result.distributor_invoice_number.startswith("KH-")


# ---------------------------------------------------------------------------
# Edge case: 852 — Product Activity (UNFI and KeHE)
# ---------------------------------------------------------------------------

class TestParse852:
    def test_unfi_852_returns_product_activity(self):
        docs = _unfi_docs()
        result = parse_document(docs["852"][0])

        assert isinstance(result, ProductActivity)
        assert result.report_id
        assert len(result.lines) >= 1

    def test_852_lines_have_period_dates(self):
        docs = _unfi_docs()
        result = parse_document(docs["852"][0])

        for line in result.lines:
            assert line.period_start    # DTM*007
            assert line.period_end      # DTM*008
            assert line.sku.startswith("CHP-")
            assert line.quantity > 0


# ---------------------------------------------------------------------------
# Error path: missing IEA trailer
# ---------------------------------------------------------------------------

class TestParseErrors:
    def test_missing_iea_raises_x12_parse_error(self):
        """Document truncated before IEA → X12ParseError with meaningful message."""
        docs = _walmart_docs()
        raw = docs["850"][0]
        # Strip the IEA line
        truncated = "\n".join(
            line for line in raw.split("\n") if not line.startswith("IEA")
        )
        with pytest.raises(X12ParseError, match="IEA"):
            parse_document(truncated)

    def test_missing_iea_error_has_segment_index(self):
        docs = _walmart_docs()
        raw = docs["850"][0]
        truncated = "\n".join(
            line for line in raw.split("\n") if not line.startswith("IEA")
        )
        with pytest.raises(X12ParseError) as exc_info:
            parse_document(truncated)
        assert exc_info.value.segment_index >= 0   # points to last valid segment


# ---------------------------------------------------------------------------
# Integration: parse full U2 corpus — zero errors, counts match
# ---------------------------------------------------------------------------

class TestFullCorpusParse:
    def _generate_all(self):
        from corpus.generator.partners.walmart import WalmartGenerator
        from corpus.generator.partners.unfi import UnfiGenerator
        from corpus.generator.partners.kehe import KeheGenerator

        wmt_orders = [
            _make_order(f"RO-{i:03d}", "walmart", "RET-WALMART", f"PO-WMT-{i:04d}",
                        po_date="2024-03-01")
            for i in range(1, 5)
        ]
        unfi_orders = [
            _make_order(f"DO-{i:03d}", "unfi", "DIST-UNFI", f"PO-UNFI-{i:04d}",
                        po_date="2024-03-01")
            for i in range(1, 5)
        ]
        kehe_orders = [
            _make_order(f"KO-{i:03d}", "kehe", "DIST-KEHE", f"PO-KEHE-{i:04d}",
                        po_date="2024-03-01")
            for i in range(1, 5)
        ]

        docs: dict[str, list[str]] = {k: [] for k in ["850", "856", "810", "820", "852", "997"]}
        for partner_gen, orders in [
            (WalmartGenerator(), wmt_orders),
            (UnfiGenerator(), unfi_orders),
            (KeheGenerator(), kehe_orders),
        ]:
            result = partner_gen.generate(orders, seed=42)
            for doc_type, doc_list in result.documents.items():
                docs[doc_type].extend(doc_list)

        return docs

    def test_full_corpus_parses_with_zero_errors(self):
        """Every generated document must parse without raising X12ParseError."""
        docs = self._generate_all()
        errors = []
        for doc_type, doc_list in docs.items():
            for i, raw in enumerate(doc_list):
                try:
                    parse_document(raw)
                except X12ParseError as exc:
                    errors.append(f"{doc_type}[{i}]: {exc}")

        assert not errors, "Parse errors:\n" + "\n".join(errors)

    def test_full_corpus_doc_type_routing(self):
        """Each doc type routes to the correct dataclass."""
        from parser.models import (
            FuncAck, Invoice, ProductActivity,
            PurchaseOrder, Remittance, ShipNotice,
        )
        expected_types = {
            "850": PurchaseOrder,
            "856": ShipNotice,
            "810": Invoice,
            "820": Remittance,
            "852": ProductActivity,
            "997": FuncAck,
        }
        docs = self._generate_all()
        for doc_type, klass in expected_types.items():
            for raw in docs[doc_type]:
                result = parse_document(raw)
                assert isinstance(result, klass), (
                    f"{doc_type} parsed as {type(result).__name__}, expected {klass.__name__}"
                )
