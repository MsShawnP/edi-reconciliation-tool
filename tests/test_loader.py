"""Tests for corpus/loader.py expand_* helpers.

Unit tests are pure-function — no DB required.
Integration tests require DATABASE_URL or POSTGRES_* env vars and are
marked @pytest.mark.integration so they can be skipped in CI without a DB.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from corpus.loader import (
    expand_810,
    expand_820,
    expand_850,
    expand_852,
    expand_856,
    expand_997,
)
from parser.models import (
    ActivityLine,
    AsnItem,
    FuncAck,
    Invoice,
    InvoiceLine,
    PoLine,
    ProductActivity,
    PurchaseOrder,
    Remittance,
    RemittanceLine,
    ShipNotice,
)

_TS = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 850 — Purchase Order
# ---------------------------------------------------------------------------

class TestExpand850:
    def _make_po(self, n_lines: int = 2) -> PurchaseOrder:
        lines = [
            PoLine(line_number=str(i), sku=f"SKU-{i:03d}", quantity=float(i * 10),
                   unit_of_measure="CA", unit_price=5.99)
            for i in range(1, n_lines + 1)
        ]
        return PurchaseOrder(
            isa_control_number="000000001",
            partner_id="WALMARTUS",
            po_number="PO-001",
            po_date="20240301",
            lines=lines,
        )

    def test_one_row_per_line(self):
        rows = expand_850(self._make_po(2), _TS)
        assert len(rows) == 2

    def test_row_keys(self):
        rows = expand_850(self._make_po(1), _TS)
        expected = {
            "isa_control_number", "partner_id", "po_number", "po_date",
            "line_number", "sku", "quantity", "unit_of_measure", "unit_price",
            "promo_allowance", "loaded_at",
        }
        assert set(rows[0].keys()) == expected

    def test_values_propagated(self):
        rows = expand_850(self._make_po(1), _TS)
        r = rows[0]
        assert r["partner_id"] == "WALMARTUS"
        assert r["po_number"] == "PO-001"
        assert r["sku"] == "SKU-001"
        assert r["quantity"] == 10.0
        assert r["loaded_at"] == _TS

    def test_empty_lines_returns_no_rows(self):
        po = PurchaseOrder("000000001", "WALMARTUS", "PO-001", "20240301")
        assert expand_850(po, _TS) == []


# ---------------------------------------------------------------------------
# 856 — Ship Notice
# ---------------------------------------------------------------------------

class TestExpand856:
    def _make_asn(self, multi_stop: bool = False) -> ShipNotice:
        items = [
            AsnItem(line_number="1", sku="SKU-001", quantity=5.0,
                    unit_of_measure="CA", hl_id="3", po_number="PO-001"),
            AsnItem(line_number="2", sku="SKU-002", quantity=3.0,
                    unit_of_measure="CA", hl_id="5",
                    po_number="PO-002" if multi_stop else "PO-001"),
        ]
        return ShipNotice(
            isa_control_number="000000002",
            partner_id="KEHE",
            shipment_id="SHIP-001",
            ship_date="20240302",
            bol_number="BOL-001",
            po_number="PO-001",
            items=items,
        )

    def test_one_row_per_item(self):
        rows = expand_856(self._make_asn(), _TS)
        assert len(rows) == 2

    def test_row_keys(self):
        rows = expand_856(self._make_asn(), _TS)
        expected = {
            "isa_control_number", "partner_id", "shipment_id", "ship_date",
            "bol_number", "header_po_number", "line_number", "sku", "quantity",
            "unit_of_measure", "hl_id", "item_po_number", "loaded_at",
        }
        assert set(rows[0].keys()) == expected

    def test_header_po_distinct_from_item_po(self):
        rows = expand_856(self._make_asn(multi_stop=True), _TS)
        assert rows[0]["header_po_number"] == "PO-001"
        assert rows[0]["item_po_number"] == "PO-001"
        assert rows[1]["header_po_number"] == "PO-001"
        assert rows[1]["item_po_number"] == "PO-002"

    def test_empty_items_returns_no_rows(self):
        asn = ShipNotice("000000002", "KEHE", "SHIP-001", "20240302")
        assert expand_856(asn, _TS) == []


# ---------------------------------------------------------------------------
# 810 — Invoice
# ---------------------------------------------------------------------------

class TestExpand810:
    def _make_invoice(self, is_credit: bool = False) -> Invoice:
        lines = [
            InvoiceLine(line_number="1", sku="SKU-001", quantity=120.0,
                        unit_of_measure="EA", unit_price=0.50),
            InvoiceLine(line_number="2", sku="SKU-002", quantity=60.0,
                        unit_of_measure="EA", unit_price=1.25),
        ]
        amount = -75.00 if is_credit else 135.00
        return Invoice(
            isa_control_number="000000003",
            partner_id="WALMARTUS",
            invoice_number="INV-001",
            invoice_date="20240303",
            po_number="PO-001",
            total_amount=amount,
            is_credit=is_credit,
            lines=lines,
        )

    def test_one_row_per_line(self):
        rows = expand_810(self._make_invoice(), _TS)
        assert len(rows) == 2

    def test_row_keys(self):
        rows = expand_810(self._make_invoice(), _TS)
        expected = {
            "isa_control_number", "partner_id", "invoice_number", "invoice_date",
            "po_number", "total_amount", "is_credit", "original_invoice_number",
            "distributor_invoice_number", "line_number", "sku", "quantity",
            "unit_of_measure", "unit_price", "loaded_at",
        }
        assert set(rows[0].keys()) == expected

    def test_header_fields_repeated_on_each_row(self):
        rows = expand_810(self._make_invoice(), _TS)
        for r in rows:
            assert r["invoice_number"] == "INV-001"
            assert r["total_amount"] == 135.00
            assert r["is_credit"] is False

    def test_credit_memo_is_credit_true(self):
        rows = expand_810(self._make_invoice(is_credit=True), _TS)
        for r in rows:
            assert r["is_credit"] is True
            assert r["total_amount"] == -75.00


# ---------------------------------------------------------------------------
# 820 — Remittance
# ---------------------------------------------------------------------------

class TestExpand820:
    def _make_remittance(self, with_rmr: bool = True,
                         po_number: str = "PO-001") -> Remittance:
        lines = []
        if with_rmr:
            lines = [
                RemittanceLine(invoice_number="INV-001", amount=135.00),
                RemittanceLine(invoice_number="INV-002", amount=75.00),
            ]
        return Remittance(
            isa_control_number="000000004",
            partner_id="UNFI",
            payment_amount=210.00,
            payment_date="20240304",
            invoice_number="INV-001",
            po_number=po_number,
            lines=lines,
        )

    def test_one_row_per_rmr_line(self):
        rows = expand_820(self._make_remittance(with_rmr=True), _TS)
        assert len(rows) == 2

    def test_row_keys(self):
        rows = expand_820(self._make_remittance(), _TS)
        expected = {
            "isa_control_number", "partner_id", "payment_amount", "payment_date",
            "header_invoice_number", "po_number", "rmr_invoice_number",
            "rmr_amount", "loaded_at",
        }
        assert set(rows[0].keys()) == expected

    def test_rmr_values(self):
        rows = expand_820(self._make_remittance(with_rmr=True), _TS)
        assert rows[0]["rmr_invoice_number"] == "INV-001"
        assert rows[0]["rmr_amount"] == 135.00
        assert rows[1]["rmr_invoice_number"] == "INV-002"
        assert rows[1]["rmr_amount"] == 75.00

    def test_no_rmr_fallback_produces_one_row(self):
        """UNFI remittances that omit RMR must not silently produce zero rows."""
        rows = expand_820(self._make_remittance(with_rmr=False), _TS)
        assert len(rows) == 1

    def test_no_rmr_fallback_uses_header_fields(self):
        rows = expand_820(self._make_remittance(with_rmr=False), _TS)
        r = rows[0]
        assert r["rmr_invoice_number"] == "INV-001"
        assert r["rmr_amount"] == 210.00

    def test_empty_po_number_preserved(self):
        rows = expand_820(self._make_remittance(po_number=""), _TS)
        assert rows[0]["po_number"] == ""


# ---------------------------------------------------------------------------
# 852 — Product Activity
# ---------------------------------------------------------------------------

class TestExpand852:
    def _make_activity(self) -> ProductActivity:
        lines = [
            ActivityLine(line_number="1", sku="SKU-001", quantity=48.0,
                         unit_of_measure="EA", period_start="20240226",
                         period_end="20240303"),
            ActivityLine(line_number="2", sku="SKU-002", quantity=24.0,
                         unit_of_measure="EA"),
        ]
        return ProductActivity(
            isa_control_number="000000005",
            partner_id="UNFI",
            report_id="UNFI-852-001",
            report_date="20240304",
            lines=lines,
        )

    def test_one_row_per_line(self):
        rows = expand_852(self._make_activity(), _TS)
        assert len(rows) == 2

    def test_row_keys(self):
        rows = expand_852(self._make_activity(), _TS)
        expected = {
            "isa_control_number", "partner_id", "report_id", "report_date",
            "line_number", "sku", "quantity", "unit_of_measure",
            "period_start", "period_end", "loaded_at",
        }
        assert set(rows[0].keys()) == expected

    def test_optional_period_defaults_to_empty(self):
        rows = expand_852(self._make_activity(), _TS)
        assert rows[1]["period_start"] == ""
        assert rows[1]["period_end"] == ""


# ---------------------------------------------------------------------------
# 997 — Functional Acknowledgment
# ---------------------------------------------------------------------------

class TestExpand997:
    def _make_ack(self, code: str = "A") -> FuncAck:
        return FuncAck(
            isa_control_number="000000006",
            partner_id="KEHE",
            ack_date="240301",
            acknowledged_functional_id="SH",
            acknowledged_gs_control="1001",
            acceptance_code=code,
        )

    def test_always_one_row(self):
        assert len(expand_997(self._make_ack(), _TS)) == 1

    def test_row_keys(self):
        rows = expand_997(self._make_ack(), _TS)
        expected = {
            "isa_control_number", "partner_id", "ack_date",
            "acknowledged_functional_id", "acknowledged_gs_control",
            "acceptance_code", "loaded_at",
        }
        assert set(rows[0].keys()) == expected

    def test_acceptance_code_propagated(self):
        for code in ("A", "E", "R"):
            rows = expand_997(self._make_ack(code=code), _TS)
            assert rows[0]["acceptance_code"] == code


# ---------------------------------------------------------------------------
# Integration tests — require live DB
# ---------------------------------------------------------------------------

def _has_db() -> bool:
    return bool(
        os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_PASSWORD")
    )


@pytest.mark.integration
@pytest.mark.skipif(not _has_db(), reason="No database credentials in environment")
class TestLoadCorpus:
    def test_round_trip(self):
        """Generate a small corpus, load it, verify non-zero row counts."""
        from corpus.generator import generate
        from corpus.loader import load_corpus

        result = generate(n_orders=2, seed=42)
        counts = load_corpus(result, truncate=True)

        assert counts["850"] > 0, "expected 850 rows"
        assert counts["856"] > 0, "expected 856 rows"
        assert counts["810"] > 0, "expected 810 rows"
        assert counts["820"] > 0, "expected 820 rows"
        assert counts["852"] > 0, "expected 852 rows"
        assert counts["997"] > 0, "expected 997 rows"

    def test_truncate_replaces_existing_rows(self):
        from corpus.generator import generate
        from corpus.loader import load_corpus

        result = generate(n_orders=1, seed=1)
        first = load_corpus(result, truncate=True)
        second = load_corpus(result, truncate=True)

        assert second["850"] == first["850"], "truncate should yield same row count on re-load"
