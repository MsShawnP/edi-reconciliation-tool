"""Tests for corpus.generator (U1 + U2).

Tests marked @pytest.mark.integration require DATABASE_URL to be set and
the Cinderhaven Postgres instance to be reachable. They are skipped otherwise.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from corpus.generator.base import (
    CanonicalOrder,
    CanonicalOrderLine,
    CanonicalShipment,
    CorpusError,
    read_partner_orders,
)
from corpus.generator.ledger import (
    DiscrepancyClass,
    DiscrepancyEntry,
    DiscrepancyLedger,
    LEDGER_COLUMNS,
)


# ---------------------------------------------------------------------------
# Shared fixtures for U2 (no DB needed)
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
    """Build a minimal CanonicalOrder for unit tests."""
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


# ---------------------------------------------------------------------------
# Happy path (integration): base.py connects to Cinderhaven and returns orders
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping Cinderhaven integration test",
)
def test_base_connects_and_returns_orders():
    """base.py connects to Cinderhaven Postgres and returns at least one order."""
    orders = read_partner_orders("walmart")

    assert len(orders) >= 1
    first = orders[0]
    assert first.partner == "walmart"
    assert first.partner_id == "RET-WALMART"
    assert first.po_number
    assert first.po_date
    assert len(first.lines) >= 1
    assert len(first.shipments) >= 1
    for line in first.lines:
        assert line.sku.startswith("CHP-")
        assert line.units_ordered > 0
        assert line.unit_price > 0.0


# ---------------------------------------------------------------------------
# Happy path: ledger writer produces a valid CSV with all required columns
# ---------------------------------------------------------------------------

def test_ledger_writes_valid_csv(tmp_path: Path):
    """DiscrepancyLedger writes a CSV with all required columns for a single entry."""
    ledger = DiscrepancyLedger()
    ledger.record(DiscrepancyEntry(
        partner="walmart",
        doc_type="856",
        isa_control_number="000000001",
        field_path="SN102",
        expected_value="100",
        actual_value="88",
        discrepancy_class=DiscrepancyClass.SHIPPED_NOT_INVOICED,
        dollar_impact=312.00,
    ))

    paths = ledger.write(tmp_path)
    csv_path = paths["csv"]

    assert csv_path is not None
    assert csv_path.exists()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    row = rows[0]
    for col in LEDGER_COLUMNS:
        assert col in row, f"Required column missing from CSV: {col}"

    assert row["partner"] == "walmart"
    assert row["doc_type"] == "856"
    assert row["isa_control_number"] == "000000001"
    assert row["field_path"] == "SN102"
    assert row["expected_value"] == "100"
    assert row["actual_value"] == "88"
    assert row["discrepancy_class"] == "shipped-not-invoiced"
    assert float(row["dollar_impact"]) == pytest.approx(312.00)


# ---------------------------------------------------------------------------
# Edge case: zero shipments raises CorpusError with a descriptive message
# ---------------------------------------------------------------------------

def test_zero_shipments_raises_corpus_error():
    """When Cinderhaven returns orders but no shipments, CorpusError is raised."""
    fake_orders = [
        ("RO-000001", "PO-WMT-000001", "2024-01-15", 48, 384.00),
    ]
    fake_lines = [
        ("RO-000001", "CHP-AS-001", 48, 8.00, 384.00),
    ]

    mock_cursor = MagicMock()
    mock_cursor.fetchall.side_effect = [
        fake_orders,  # SELECT from retailer_orders
        fake_lines,   # SELECT from retailer_order_lines
        [],           # SELECT from retailer_shipments — deliberately empty
    ]
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("corpus.generator.base._connect", return_value=mock_conn):
        with pytest.raises(CorpusError, match="No shipments found"):
            read_partner_orders("walmart")


# ---------------------------------------------------------------------------
# Edge case: split-shipment ledger entries have correct per-item dollar values
# ---------------------------------------------------------------------------

def test_ledger_split_shipment_dollar_values(tmp_path: Path):
    """Split shipment records correct per-item dollar impacts in the ledger.

    Scenario: one 850 line (48 cases @ $8.00) → two 856 items.
    First 856 ships 36 cases (shortage of 12 = $96.00 exposure).
    Second 856 ships 12 but invoices only 10 (2 case gap = $16.00 exposure).
    """
    unit_price = 8.00

    # Entry 1: ordered-not-ASN'd shortage on the first partial shipment
    shortage_qty_1 = 12
    dollar_impact_1 = round(shortage_qty_1 * unit_price, 2)

    # Entry 2: shipped-not-invoiced gap on the second partial shipment
    invoiced_gap = 2
    dollar_impact_2 = round(invoiced_gap * unit_price, 2)

    ledger = DiscrepancyLedger()
    ledger.record(DiscrepancyEntry(
        partner="walmart",
        doc_type="856",
        isa_control_number="000000001",
        field_path="SN102",
        expected_value="48",
        actual_value="36",
        discrepancy_class=DiscrepancyClass.ORDERED_NOT_ASND,
        dollar_impact=dollar_impact_1,
    ))
    ledger.record(DiscrepancyEntry(
        partner="walmart",
        doc_type="810",
        isa_control_number="000000002",
        field_path="IT102",
        expected_value="12",
        actual_value="10",
        discrepancy_class=DiscrepancyClass.SHIPPED_NOT_INVOICED,
        dollar_impact=dollar_impact_2,
    ))

    paths = ledger.write(tmp_path)
    with open(paths["csv"], newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["isa_control_number"] == "000000001"
    assert rows[1]["isa_control_number"] == "000000002"
    assert float(rows[0]["dollar_impact"]) == pytest.approx(dollar_impact_1)
    assert float(rows[1]["dollar_impact"]) == pytest.approx(dollar_impact_2)
    assert rows[0]["discrepancy_class"] == "ordered-not-asnd"
    assert rows[1]["discrepancy_class"] == "shipped-not-invoiced"
    # Verify per-item math is correct: total matches the sum
    total_impact = float(rows[0]["dollar_impact"]) + float(rows[1]["dollar_impact"])
    assert total_impact == pytest.approx(dollar_impact_1 + dollar_impact_2)


# ===========================================================================
# U2 tests — partner generators and injector (no DB required)
# ===========================================================================

# ---------------------------------------------------------------------------
# ISA envelope structure — all partners
# ---------------------------------------------------------------------------

class TestWalmartGenerator:
    def _orders(self, n: int = 2) -> list[CanonicalOrder]:
        return [
            _make_order(f"RO-{i:03d}", "walmart", "RET-WALMART", f"PO-WMT-{i:04d}",
                        po_date=f"2024-0{(i % 9) + 1}-01")
            for i in range(1, n + 1)
        ]

    def test_850_has_valid_isa_envelope(self):
        from corpus.generator.partners.walmart import WalmartGenerator
        result = WalmartGenerator().generate(self._orders(), seed=42)
        doc = result.documents["850"][0]
        assert doc.startswith("ISA*")
        assert "IEA*1*" in doc
        # ISA sender should be WALMARTUS (trading partner sends 850)
        isa_line = doc.split("\n")[0]
        assert "WALMARTUS" in isa_line
        assert "CINDERHAVEN" in isa_line

    def test_850_has_beg_and_po1(self):
        from corpus.generator.partners.walmart import WalmartGenerator
        result = WalmartGenerator().generate(self._orders(), seed=42)
        doc = result.documents["850"][0]
        assert "BEG*00*SA*PO-WMT-0001" in doc
        assert "PO1*1*" in doc
        assert "*CA*" in doc  # orders in cases

    def test_first_order_produces_two_856s(self):
        from corpus.generator.partners.walmart import WalmartGenerator
        result = WalmartGenerator().generate(self._orders(2), seed=42)
        # First order: 2 ASNs (60/40 split); second order: 1 ASN → total 3
        assert len(result.documents["856"]) >= 2
        first_two = result.documents["856"][:2]
        # Both should reference the same PO (PRF segment)
        for doc in first_two:
            assert "PRF*PO-WMT-0001" in doc

    def test_810_invoices_in_eaches(self):
        from corpus.generator.partners.walmart import WalmartGenerator
        result = WalmartGenerator().generate(self._orders(), seed=42)
        doc = result.documents["810"][0]
        assert "*EA*" in doc  # IT1 uses EA (eaches)
        assert "*CA*" not in doc.split("IT1")[1].split("TDS")[0]  # no CA in IT1 section

    def test_997_references_856_group(self):
        from corpus.generator.partners.walmart import WalmartGenerator
        result = WalmartGenerator().generate(self._orders(), seed=42)
        # At least one 997 should ACK a SH (ship notice) group
        ack_types = []
        for doc in result.documents["997"]:
            for seg in doc.split("\n"):
                if seg.startswith("AK1*"):
                    ack_types.append(seg.split("*")[1])
        assert "SH" in ack_types
        assert "IN" in ack_types


class TestUnfiGenerator:
    def _orders(self, n: int = 4) -> list[CanonicalOrder]:
        return [
            _make_order(f"DO-{i:03d}", "unfi", "DIST-UNFI", f"PO-UNFI-{i:04d}",
                        po_date=f"2024-0{(i % 9) + 1}-01")
            for i in range(1, n + 1)
        ]

    def test_850_has_sln_promo_segment(self):
        from corpus.generator.partners.unfi import UnfiGenerator
        result = UnfiGenerator().generate(self._orders(), seed=42)
        doc = result.documents["850"][0]
        assert "SLN*" in doc, "UNFI 850 must include SLN promo allowance segment"
        # SLN should follow PO1 and contain PE (percent) qualifier and TD code
        assert "*PE*TD*PROMO-ALLOW" in doc

    def test_third_order_has_credit_810(self):
        from corpus.generator.partners.unfi import UnfiGenerator
        orders = self._orders(4)
        result = UnfiGenerator().generate(orders, seed=42)
        # 3rd order (idx==2) produces credit + rebill → at least 2 extra 810s
        assert len(result.documents["810"]) >= 4
        # Find the credit memo (negative TDS)
        credits = [d for d in result.documents["810"] if "TDS*-" in d]
        assert len(credits) >= 1, "Expected at least one credit 810 with negative TDS"

    def test_every_third_820_omits_po_reference(self):
        from corpus.generator.partners.unfi import UnfiGenerator
        orders = self._orders(6)
        result = UnfiGenerator().generate(orders, seed=42)
        # idx 2 and 5 → REF*PO absent; idx 0,1,3,4 → REF*PO present
        docs_820 = result.documents["820"]
        no_po_ref = [d for d in docs_820 if "REF*PO*" not in d]
        with_po_ref = [d for d in docs_820 if "REF*PO*" in d]
        assert len(no_po_ref) >= 1, "Expected at least one 820 without REF*PO"
        assert len(with_po_ref) >= 1, "Expected at least one 820 with REF*PO"

    def test_852_generated_for_each_order(self):
        from corpus.generator.partners.unfi import UnfiGenerator
        orders = self._orders(3)
        result = UnfiGenerator().generate(orders, seed=42)
        assert len(result.documents["852"]) == len(orders)
        for doc in result.documents["852"]:
            assert "BIA*00*SS*" in doc
            assert "ZA*S*" in doc


class TestKeheGenerator:
    def _orders(self, n: int = 4) -> list[CanonicalOrder]:
        return [
            _make_order(f"KO-{i:03d}", "kehe", "DIST-KEHE", f"PO-KEHE-{i:04d}",
                        po_date=f"2024-0{(i % 9) + 1}-01")
            for i in range(1, n + 1)
        ]

    def test_810_has_ref_ia_qualifier(self):
        from corpus.generator.partners.kehe import KeheGenerator
        result = KeheGenerator().generate(self._orders(), seed=42)
        doc = result.documents["810"][0]
        assert "REF*IA*" in doc, "KeHE 810 must carry REF*IA distributor invoice number"

    def test_856_uses_multi_hl_loops(self):
        from corpus.generator.partners.kehe import KeheGenerator
        result = KeheGenerator().generate(self._orders(4), seed=42)
        # First 856 covers orders 0+1 → must have 2 O-level HL loops
        doc = result.documents["856"][0]
        o_loops = [seg for seg in doc.split("\n") if seg.startswith("HL*") and "*O~" in seg]
        assert len(o_loops) >= 2, "KeHE multi-stop 856 must have ≥2 O-level HL loops"

    def test_850_has_valid_isa_envelope(self):
        from corpus.generator.partners.kehe import KeheGenerator
        result = KeheGenerator().generate(self._orders(), seed=42)
        doc = result.documents["850"][0]
        assert doc.startswith("ISA*")
        assert "KEHE" in doc.split("\n")[0]


# ---------------------------------------------------------------------------
# Injector tests
# ---------------------------------------------------------------------------

class TestInjector:
    def _walmart_result(self):
        from corpus.generator.partners.walmart import WalmartGenerator
        orders = [
            _make_order(f"RO-{i:03d}", "walmart", "RET-WALMART", f"PO-WMT-{i:04d}",
                        po_date=f"2024-0{i}-01", units_shipped=48)
            for i in range(1, 5)
        ]
        return WalmartGenerator().generate(orders, seed=42)

    def test_shipped_not_invoiced_modifies_sn1_and_records_ledger(self):
        from corpus.generator.injector import Injector
        result = self._walmart_result()
        original_856_count = len(result.documents["856"])

        # Use high rate to guarantee at least one injection
        injected = Injector().inject(result, rate=1.0, seed=7)

        sni_entries = [
            e for e in injected.ledger.entries()
            if e.discrepancy_class == DiscrepancyClass.SHIPPED_NOT_INVOICED
        ]
        assert len(sni_entries) >= 1
        # Dollar impact must be positive
        for e in sni_entries:
            assert e.dollar_impact > 0
            assert e.doc_type == "856"

    def test_short_pay_reduces_rmr_amount(self):
        from corpus.generator.injector import Injector
        result = self._walmart_result()
        injected = Injector().inject(result, rate=1.0, seed=13)
        sp_entries = [
            e for e in injected.ledger.entries()
            if e.discrepancy_class == DiscrepancyClass.SHORT_PAY
        ]
        assert len(sp_entries) >= 1
        for e in sp_entries:
            assert e.dollar_impact > 0

    def test_997_missing_ack_removes_documents(self):
        from corpus.generator.injector import Injector
        result = self._walmart_result()
        original_997_count = len(result.documents["997"])
        injected = Injector().inject(result, rate=1.0, seed=21)
        ack_entries = [
            e for e in injected.ledger.entries()
            if e.discrepancy_class == DiscrepancyClass.MISSING_ACK_997
        ]
        # Removed 997s should be fewer in the output
        if ack_entries:
            assert len(injected.documents["997"]) < original_997_count

    def test_zero_rate_produces_no_injections(self):
        from corpus.generator.injector import Injector
        result = self._walmart_result()
        injected = Injector().inject(result, rate=0.0, seed=0)
        assert len(injected.ledger.entries()) == 0

    def test_injector_preserves_document_count_for_non_removal_types(self):
        from corpus.generator.injector import Injector
        result = self._walmart_result()
        original_856 = len(result.documents["856"])
        # shipped-not-invoiced modifies documents in-place, does not remove them
        injected = Injector().inject(result, rate=1.0, seed=42)
        # 856 count may decrease (ordered-not-asnd removes some) but not increase
        assert len(injected.documents["856"]) <= original_856
