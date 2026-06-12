"""Tests for the cascade-aware validation contract (corpus/validate.py).

All tests exercise the pure validate() function with synthetic data —
no database required.
"""
from corpus.validate import (
    EXPECTED_SURFACE,
    ClassRecall,
    ValidationResult,
    validate,
    format_report,
)


def _ledger_entry(
    disc_class: str,
    partner: str = "walmart",
    isa: str = "000001001",
    doc_type: str = "856",
    expected_value: str = "",
) -> dict[str, str]:
    return {
        "partner": partner,
        "doc_type": doc_type,
        "isa_control_number": isa,
        "field_path": "test",
        "expected_value": expected_value,
        "actual_value": "test",
        "discrepancy_class": disc_class,
        "dollar_impact": "100.0",
    }


def _mart_row(
    exception_class: str,
    po_number: str = "PO-001",
    partner_id: str = "WALMARTUS",
) -> dict[str, str]:
    return {
        "partner_id": partner_id,
        "po_number": po_number,
        "exception_class": exception_class,
    }


class TestExpectedSurfaceMapComplete:
    """The map must cover every DiscrepancyClass the injector can produce."""

    def test_all_seven_classes_mapped(self):
        expected_classes = {
            "shipped-not-invoiced",
            "short-pay",
            "ordered-not-asnd",
            "uom-mismatch",
            "mapping-drift",
            "852-discrepancy",
            "997-missing-ack",
        }
        assert set(EXPECTED_SURFACE.keys()) == expected_classes

    def test_uom_mismatch_explicitly_invisible(self):
        rule = EXPECTED_SURFACE["uom-mismatch"]
        assert rule.may_be_invisible is True
        assert len(rule.acceptable) == 0


class TestUnmappedClassHardError:
    def test_unknown_class_fails(self):
        entries = [_ledger_entry("totally-new-class")]
        result = validate(entries, [], {})
        assert not result.passed
        assert "totally-new-class" in result.unmapped_classes

    def test_known_classes_pass_unmapped_check(self):
        entries = [_ledger_entry("short-pay", isa="000001001")]
        mart = [_mart_row("short_pay", po_number="PO-001")]
        result = validate(entries, mart, {"000001001": "PO-001"})
        assert len(result.unmapped_classes) == 0


class TestRecallShortPay:
    def test_short_pay_found(self):
        entries = [_ledger_entry("short-pay", isa="000001001")]
        mart = [_mart_row("short_pay", po_number="PO-001")]
        isa_to_po = {"000001001": "PO-001"}
        result = validate(entries, mart, isa_to_po)
        assert result.passed
        assert result.class_recall["short-pay"].hits == 1
        assert result.class_recall["short-pay"].misses == 0

    def test_short_pay_missing_fails(self):
        entries = [_ledger_entry("short-pay", isa="000001001")]
        isa_to_po = {"000001001": "PO-001"}
        result = validate(entries, [], isa_to_po)
        assert not result.passed
        assert result.class_recall["short-pay"].misses == 1


class TestRecallOrderedNotAsnd:
    def test_po_parsed_from_expected_value(self):
        entries = [_ledger_entry(
            "ordered-not-asnd", doc_type="850",
            expected_value="ASN for PO PO-042",
        )]
        mart = [_mart_row("ordered_not_asnd", po_number="PO-042")]
        result = validate(entries, mart, {})
        assert result.passed
        assert result.entry_results[0].po_number == "PO-042"

    def test_walmart_two_856_surfaces_as_qty_mismatch(self):
        entries = [_ledger_entry(
            "ordered-not-asnd", doc_type="850",
            expected_value="ASN for PO PO-001",
        )]
        mart = [_mart_row("qty_mismatch", po_number="PO-001")]
        result = validate(entries, mart, {})
        assert result.passed


class TestRecallShippedNotInvoiced:
    def test_surfaces_as_qty_mismatch(self):
        entries = [_ledger_entry("shipped-not-invoiced", isa="000001001")]
        mart = [_mart_row("qty_mismatch", po_number="PO-001")]
        isa_to_po = {"000001001": "PO-001"}
        result = validate(entries, mart, isa_to_po)
        assert result.passed
        assert result.class_recall["shipped-not-invoiced"].hits == 1

    def test_silent_injection_acceptable(self):
        entries = [_ledger_entry("shipped-not-invoiced", isa="000001001")]
        isa_to_po = {"000001001": "PO-001"}
        result = validate(entries, [], isa_to_po)
        assert result.passed
        assert result.class_recall["shipped-not-invoiced"].invisible == 1


class TestRecallMappingDrift:
    def test_surfaces_as_ordered_not_asnd(self):
        entries = [_ledger_entry("mapping-drift", isa="000001001")]
        mart = [_mart_row("ordered_not_asnd", po_number="PO-001")]
        isa_to_po = {"000001001": "PO-001"}
        result = validate(entries, mart, isa_to_po)
        assert result.passed

    def test_missing_mart_row_fails(self):
        entries = [_ledger_entry("mapping-drift", isa="000001001")]
        isa_to_po = {"000001001": "PO-001"}
        result = validate(entries, [], isa_to_po)
        assert not result.passed
        assert result.class_recall["mapping-drift"].misses == 1


class TestRecallUomMismatch:
    def test_always_invisible(self):
        entries = [_ledger_entry("uom-mismatch", isa="000001001")]
        result = validate(entries, [], {})
        assert result.passed
        assert result.class_recall["uom-mismatch"].invisible == 1
        assert result.class_recall["uom-mismatch"].visible == 0
        assert result.entry_results[0].expected_invisible is True


class TestRecall852:
    def test_partner_level_fallback(self):
        entries = [_ledger_entry("852-discrepancy", partner="unfi", isa="000002001")]
        mart = [_mart_row("852_discrepancy", po_number="", partner_id="UNFI")]
        result = validate(entries, mart, {})
        assert result.passed

    def test_852_missing_fails(self):
        entries = [_ledger_entry("852-discrepancy", partner="unfi", isa="000002001")]
        result = validate(entries, [], {})
        assert not result.passed


class TestRecall997:
    def test_partner_level_fallback(self):
        entries = [_ledger_entry("997-missing-ack", partner="walmart", isa="000001001")]
        mart = [_mart_row("missing_997_ack", po_number="", partner_id="WALMARTUS")]
        result = validate(entries, mart, {})
        assert result.passed


class TestMartClassCounts:
    def test_counts_reported(self):
        entries = [_ledger_entry("short-pay", isa="000001001")]
        mart = [
            _mart_row("short_pay", po_number="PO-001"),
            _mart_row("short_pay", po_number="PO-002"),
            _mart_row("qty_mismatch", po_number="PO-003"),
        ]
        result = validate(entries, mart, {"000001001": "PO-001"})
        assert result.mart_class_counts["short_pay"] == 2
        assert result.mart_class_counts["qty_mismatch"] == 1


class TestFormatReport:
    def test_passed_report_contains_verdict(self):
        entries = [_ledger_entry("uom-mismatch")]
        result = validate(entries, [], {})
        report = format_report(result)
        assert "PASSED" in report

    def test_failed_report_contains_failure_detail(self):
        entries = [_ledger_entry("short-pay", isa="000001001")]
        result = validate(entries, [], {"000001001": "PO-001"})
        report = format_report(result)
        assert "FAILED" in report
        assert "RECALL FAILURES" in report

    def test_unmapped_report_contains_hard_error(self):
        entries = [_ledger_entry("invented-class")]
        result = validate(entries, [], {})
        report = format_report(result)
        assert "HARD ERROR" in report
        assert "invented-class" in report
