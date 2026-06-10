"""Tests for corpus.generator.base and corpus.generator.ledger (U1).

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
