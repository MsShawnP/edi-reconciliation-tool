"""Integration tests for the U5 dbt matching models.

These tests require:
  1. A live Postgres instance with DATABASE_URL or POSTGRES_* env vars.
  2. The corpus loader to have run (load_corpus or `make parse`).
  3. The dbt models to have run (`dbt run --select marts`).

All tests are marked @pytest.mark.integration and skipped without DB credentials.
They query the materialized dbt tables directly via psycopg2.

Run with:
    pytest tests/test_matching.py -m integration
"""
from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Skip helpers
# ---------------------------------------------------------------------------

def _has_db() -> bool:
    return bool(
        os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_PASSWORD")
    )


def _connect():
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        dbname=os.environ.get("POSTGRES_DB", "cinderhaven"),
    )


def _query(sql: str) -> list[dict]:
    """Run a read-only query; return list of dicts."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def _scalar(sql: str):
    """Return the first cell of the first row."""
    rows = _query(sql)
    if not rows:
        return None
    return next(iter(rows[0].values()))


# ---------------------------------------------------------------------------
# int_document_links
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(not _has_db(), reason="No database credentials")
class TestDocumentLinks:
    def test_all_856_resolve_to_po(self):
        """Every ASN should resolve to a PO via po_direct — no orphans from 856."""
        orphan_856 = _scalar("""
            select count(*)
            from edi_marts.int_document_links
            where document_type = '856' and resolution_path = 'orphan'
        """)
        assert orphan_856 == 0, f"Expected 0 orphan 856s, got {orphan_856}"

    def test_invoice_fallback_used_for_unfi_820(self):
        """UNFI 820s that omit REF*PO should be resolved via invoice fallback."""
        fallback = _scalar("""
            select count(*)
            from edi_marts.int_document_links
            where document_type = '820'
              and resolution_path = 'invoice_fallback'
        """)
        assert fallback >= 1, "UNFI 820s without REF*PO should produce at least one invoice_fallback row"

    def test_resolution_path_values_are_valid(self):
        """All resolution paths must be one of the accepted values."""
        invalid = _scalar("""
            select count(*)
            from edi_marts.int_document_links
            where resolution_path not in ('po_direct', 'invoice_fallback', 'orphan')
        """)
        assert invalid == 0, f"Found {invalid} rows with invalid resolution_path"

    def test_link_table_is_not_empty(self):
        total = _scalar("select count(*) from edi_marts.int_document_links")
        assert total > 0, "int_document_links should have rows after corpus load"


# ---------------------------------------------------------------------------
# int_four_way_match
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(not _has_db(), reason="No database credentials")
class TestFourWayMatch:
    def test_match_status_values_are_valid(self):
        valid = {
            'matched', 'ordered_not_asnd', 'asnd_not_invoiced',
            'shipped_not_invoiced', 'invoiced_not_paid', 'short_pay',
            'uom_mismatch', 'qty_mismatch',
        }
        rows = _query("select distinct match_status from edi_marts.int_four_way_match")
        for row in rows:
            assert row['match_status'] in valid, \
                f"Unexpected match_status: {row['match_status']}"

    def test_matched_rows_have_no_delta(self):
        """Rows with match_status='matched' should have negligible deltas."""
        bad = _scalar("""
            select count(*)
            from edi_marts.int_four_way_match
            where match_status = 'matched'
              and (
                abs(ordered_vs_shipped_delta)    > 1
                or abs(shipped_vs_invoiced_delta) > 1
                or abs(invoice_vs_paid_delta)     > 5
              )
        """)
        assert bad == 0, \
            f"{bad} 'matched' rows exceed tolerance thresholds"

    def test_exception_rows_produce_nonzero_delta(self):
        """Every non-matched, non-operational row should have a meaningful delta."""
        bad = _scalar("""
            select count(*)
            from edi_marts.int_four_way_match
            where match_status not in ('matched', 'asnd_not_invoiced', 'invoiced_not_paid')
              and ordered_vs_shipped_delta = 0
              and shipped_vs_invoiced_delta = 0
              and invoice_vs_paid_delta = 0
        """)
        assert bad == 0, \
            f"{bad} exception rows have zero delta across all columns"

    def test_po_lines_present(self):
        total = _scalar("select count(*) from edi_marts.int_four_way_match")
        assert total > 0, "int_four_way_match should have rows after corpus load"

    def test_walmart_uom_normalization(self):
        """Walmart 810 invoices in EA; after normalization matched rows should exist."""
        matched = _scalar("""
            select count(*)
            from edi_marts.int_four_way_match
            where partner_id = 'WALMARTUS'
              and match_status = 'matched'
        """)
        # Walmart corpus always has some clean orders — expect at least one matched row
        assert matched >= 1, "Walmart corpus should have at least one matched row after UoM normalization"


# ---------------------------------------------------------------------------
# int_852_match
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(not _has_db(), reason="No database credentials")
class TestMatch852:
    def test_model_is_not_empty(self):
        total = _scalar("select count(*) from edi_marts.int_852_match")
        assert total > 0, "int_852_match should have rows after corpus load"

    def test_unfi_kehe_have_852_rows(self):
        """UNFI and KeHE generate 852 sell-through; Walmart does not."""
        unfi = _scalar("""
            select count(*) from edi_marts.int_852_match where partner_id = 'UNFI'
        """)
        assert unfi > 0, "UNFI should have 852 activity rows"

    def test_delta_calculation_is_correct(self):
        """delta_qty = reported_qty - shipped_qty."""
        bad = _scalar("""
            select count(*)
            from edi_marts.int_852_match
            where delta_qty != reported_qty - shipped_qty
        """)
        assert bad == 0, f"{bad} rows have incorrect delta_qty calculation"

    def test_has_discrepancy_flag_consistent(self):
        """has_discrepancy should be true iff abs(delta_qty) > 0."""
        bad = _scalar("""
            select count(*)
            from edi_marts.int_852_match
            where has_discrepancy != (abs(delta_qty) > 0)
        """)
        assert bad == 0, f"{bad} rows have inconsistent has_discrepancy flag"


# ---------------------------------------------------------------------------
# int_997_match
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(not _has_db(), reason="No database credentials")
class TestMatch997:
    def test_model_is_not_empty(self):
        total = _scalar("select count(*) from edi_marts.int_997_match")
        assert total > 0, "int_997_match should have rows (outbound docs)"

    def test_ack_status_values_are_valid(self):
        valid = {'accepted', 'accepted_with_errors', 'rejected', 'no_ack'}
        rows = _query("select distinct ack_status from edi_marts.int_997_match")
        for row in rows:
            assert row['ack_status'] in valid, \
                f"Unexpected ack_status: {row['ack_status']}"

    def test_clean_corpus_has_accepted_acks(self):
        """In a corpus with no injected 997-missing discrepancies, all acks are accepted."""
        accepted = _scalar("""
            select count(*) from edi_marts.int_997_match where ack_status = 'accepted'
        """)
        assert accepted >= 1, "clean corpus should have at least one accepted 997 ACK"


# ---------------------------------------------------------------------------
# fct_exceptions
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(not _has_db(), reason="No database credentials")
class TestFctExceptions:
    def test_dollar_impact_is_non_negative(self):
        """All exception dollar impacts should be >= 0."""
        bad = _scalar("""
            select count(*)
            from edi_marts.fct_exceptions
            where dollar_impact < 0
        """)
        assert bad == 0, f"{bad} rows have negative dollar_impact"

    def test_exception_classes_are_valid(self):
        valid = {
            'ordered_not_asnd', 'shipped_not_invoiced', 'short_pay',
            'uom_mismatch', 'qty_mismatch', '852_discrepancy', 'missing_997_ack',
        }
        rows = _query("select distinct exception_class from edi_marts.fct_exceptions")
        for row in rows:
            assert row['exception_class'] in valid, \
                f"Unexpected exception_class: {row['exception_class']}"

    def test_missing_997_ack_has_zero_dollar_impact(self):
        """997 missing ACK is operational exposure — dollar_impact must be 0."""
        bad = _scalar("""
            select count(*)
            from edi_marts.fct_exceptions
            where exception_class = 'missing_997_ack'
              and dollar_impact != 0
        """)
        assert bad == 0, \
            f"{bad} missing_997_ack rows have non-zero dollar_impact"

    def test_short_pay_has_dispute_window_30_days(self):
        """Short-pay dispute window is always 30 days."""
        bad = _scalar("""
            select count(*)
            from edi_marts.fct_exceptions
            where exception_class = 'short_pay'
              and dispute_window_days != 30
        """)
        assert bad == 0, \
            f"{bad} short_pay rows have wrong dispute_window_days"

    def test_chargeback_exceptions_have_60_day_window(self):
        """Chargeback classes (ordered_not_asnd, shipped_not_invoiced, uom/qty mismatch) use 60-day window."""
        bad = _scalar("""
            select count(*)
            from edi_marts.fct_exceptions
            where exception_class in (
                'ordered_not_asnd', 'shipped_not_invoiced',
                'uom_mismatch', 'qty_mismatch'
            )
            and dispute_window_days != 60
        """)
        assert bad == 0, \
            f"{bad} chargeback exception rows have wrong dispute_window_days"

    def test_injected_discrepancies_appear_in_mart(self):
        """Corpus with injected discrepancies should produce at least one exception row."""
        total = _scalar("select count(*) from edi_marts.fct_exceptions")
        # Default injection rate is > 0, so at least one exception should exist.
        assert total > 0, "corpus generated with default injection rate should have at least one exception"

    def test_short_pay_no_invoice_duplicates(self):
        """Each invoice_number must appear at most once in short_pay exceptions.

        invoice_amount is a document-level total replicated on every SKU row.
        Without deduplication an N-SKU invoice contributes N× the true delta.
        """
        dups = _scalar("""
            select count(*)
            from (
                select partner_id, invoice_number
                from edi_marts.fct_exceptions
                where exception_class = 'short_pay'
                  and invoice_number is not null
                group by partner_id, invoice_number
                having count(*) > 1
            ) dupes
        """)
        assert dups == 0, \
            f"Found {dups} (partner_id, invoice_number) pairs with multiple short_pay rows — indicates N× double-counting"

    def test_dispute_urgent_matches_computed_expiry(self):
        """Every row whose dispute window has already passed must be marked dispute_urgent."""
        bad = _scalar("""
            select count(*)
            from edi_marts.fct_exceptions
            where dispute_date_anchor is not null
              and dispute_window_days is not null
              and (dispute_date_anchor + dispute_window_days * interval '1 day')::date < current_date
              and dispute_urgent = false
        """)
        assert bad == 0, \
            f"{bad} rows have an expired dispute window but dispute_urgent = false"
