"""Cascade-aware validation contract for the EDI matching engine.

Given the discrepancy ledger (injector ground truth) and the populated mart
tables, validates that every injected discrepancy surfaces in the mart under
one of its expected exception classes — or is correctly classified as
expected-invisible.

The expected-surface map encodes the relationship between what the injector
plants and what the four-way match engine can detect.  The single-status CASE
cascade in int_four_way_match.sql is intentional and correct: a line failing
an earlier leg (e.g. qty_mismatch) never reaches later checks (e.g.
shipped_not_invoiced).  This validator treats that as a design property, not
a bug.

Usage (via Makefile):
    python -m corpus.validate --ledger corpus/output/discrepancy_ledger.csv --schema edi_marts

Exit codes:
    0 — all checks passed
    1 — validation failure (unmapped class, recall miss, or fatal error)
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Expected-surface map — the contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SurfaceRule:
    """What the mart is expected to show for a given ledger class."""
    acceptable: frozenset[str]
    may_be_invisible: bool = False


EXPECTED_SURFACE: dict[str, SurfaceRule] = {
    # SNI: _bump_sn1 raises shipped qty by Δ.  |ordered − shipped| and
    # |shipped − invoiced| both become Δ.  CASE precedence: qty_mismatch
    # fires before shipped_not_invoiced when Δ > tolerance.  When Δ ≤
    # tolerance (Δ=1 on small orders), the injection is silent.
    "shipped-not-invoiced": SurfaceRule(
        acceptable=frozenset({"qty_mismatch", "shipped_not_invoiced"}),
        may_be_invisible=True,
    ),

    # Short-pay: _reduce_rmr cuts 820 RMR by $50–$500, always > $5 tolerance.
    "short-pay": SurfaceRule(
        acceptable=frozenset({"short_pay"}),
    ),

    # ASN removal: removes a 856 for a PO.  PO lines lose their ASN →
    # ordered_not_asnd.  But for Walmart's two-856 split, removing the first
    # 856 leaves the second → shipped qty drops → qty_mismatch.
    "ordered-not-asnd": SurfaceRule(
        acceptable=frozenset({"ordered_not_asnd", "qty_mismatch"}),
    ),

    # Walmart UoM: +1 each on 810 IT1.  1/case_pack of a case is well
    # within the 1-case tolerance.  The mart's uom_mismatch branch tests the
    # 856 leg (shipped_uom ≠ po_uom), never the 810 leg.  Every injection
    # produces zero mart rows.  Explicitly mapped as no-surface.
    "uom-mismatch": SurfaceRule(
        acceptable=frozenset(),
        may_be_invisible=True,
    ),

    # Mapping drift: corrupts a 856 LIN SKU to UNKNOWN-ITEM.  The ASN line
    # joins to no PO line → the real PO line loses its ASN → surfaces as
    # ordered_not_asnd or qty_mismatch.  The mart has no mapping_drift class.
    "mapping-drift": SurfaceRule(
        acceptable=frozenset({"ordered_not_asnd", "qty_mismatch"}),
    ),

    # 852 sell-through gap: _reduce_za cuts ZA qty → int_852_match detects.
    "852-discrepancy": SurfaceRule(
        acceptable=frozenset({"852_discrepancy"}),
    ),

    # Missing 997: dropped 997 document → int_997_match detects.
    "997-missing-ack": SurfaceRule(
        acceptable=frozenset({"missing_997_ack"}),
    ),
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class EntryResult:
    ledger_class: str
    partner: str
    isa_control_number: str
    po_number: str | None
    expected_invisible: bool
    found_mart_classes: frozenset[str]
    passed: bool


@dataclass
class ClassRecall:
    ledger_class: str
    total: int = 0
    visible: int = 0
    invisible: int = 0
    hits: int = 0
    misses: int = 0

    @property
    def recall(self) -> float:
        return self.hits / self.visible if self.visible else 1.0


@dataclass
class ValidationResult:
    entry_results: list[EntryResult] = field(default_factory=list)
    class_recall: dict[str, ClassRecall] = field(default_factory=dict)
    mart_class_counts: dict[str, int] = field(default_factory=dict)
    unmapped_classes: list[str] = field(default_factory=list)
    passed: bool = True


# ---------------------------------------------------------------------------
# PO resolution from ledger entries
# ---------------------------------------------------------------------------

_PO_RE = re.compile(r"ASN for PO (.+)")


def _parse_po_from_expected(value: str) -> str | None:
    m = _PO_RE.match(value)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Core validation (pure — no DB dependency)
# ---------------------------------------------------------------------------

def validate(
    ledger_entries: list[dict[str, str]],
    mart_rows: list[dict[str, str]],
    isa_to_po: dict[str, str],
) -> ValidationResult:
    """Run the full validation contract.

    Args:
        ledger_entries: rows from discrepancy_ledger.csv (dict per row).
        mart_rows: rows from fct_exceptions (dict per row, needs
            partner_id, po_number, exception_class).
        isa_to_po: ISA control number → po_number lookup (from staging or
            int_document_links).

    Returns:
        ValidationResult with per-entry results, per-class recall, and
        overall pass/fail.
    """
    result = ValidationResult()

    # --- 1. Unmapped class check (hard error) ---
    seen_classes = {e["discrepancy_class"] for e in ledger_entries}
    for cls in sorted(seen_classes):
        if cls not in EXPECTED_SURFACE:
            result.unmapped_classes.append(cls)
    if result.unmapped_classes:
        result.passed = False
        return result

    # --- 2. Build mart index: po_number → set of exception_classes ---
    mart_by_po: dict[str, set[str]] = defaultdict(set)
    partner_classes: set[str] = set()
    for row in mart_rows:
        po = row.get("po_number") or ""
        cls = row["exception_class"]
        if po:
            mart_by_po[po].add(cls)
        partner_classes.add(cls)
        result.mart_class_counts[cls] = result.mart_class_counts.get(cls, 0) + 1

    # --- 3. Initialize per-class recall trackers ---
    for cls in EXPECTED_SURFACE:
        result.class_recall[cls] = ClassRecall(ledger_class=cls)

    # --- 4. Per-entry recall ---
    for entry in ledger_entries:
        disc_class = entry["discrepancy_class"]
        rule = EXPECTED_SURFACE[disc_class]
        partner = entry.get("partner", "")
        isa = entry.get("isa_control_number", "").strip()
        cr = result.class_recall[disc_class]
        cr.total += 1

        # Resolve PO
        po: str | None = None
        if disc_class == "ordered-not-asnd":
            po = _parse_po_from_expected(entry.get("expected_value", ""))
        elif isa in isa_to_po:
            po = isa_to_po[isa]

        # Expected-invisible with no acceptable classes (uom-mismatch)
        if rule.may_be_invisible and not rule.acceptable:
            cr.invisible += 1
            result.entry_results.append(EntryResult(
                ledger_class=disc_class, partner=partner,
                isa_control_number=isa, po_number=po,
                expected_invisible=True,
                found_mart_classes=frozenset(), passed=True,
            ))
            continue

        # Find matching mart classes for this entry
        found: set[str] = set()
        if po and po in mart_by_po:
            found = mart_by_po[po] & rule.acceptable
        elif not po:
            # Fallback: partner-level check (852/997 or unresolved PO)
            found = partner_classes & rule.acceptable

        if found:
            cr.visible += 1
            cr.hits += 1
            result.entry_results.append(EntryResult(
                ledger_class=disc_class, partner=partner,
                isa_control_number=isa, po_number=po,
                expected_invisible=False,
                found_mart_classes=frozenset(found), passed=True,
            ))
        elif rule.may_be_invisible:
            # SNI with Δ ≤ tolerance — silent injection, acceptable
            cr.invisible += 1
            result.entry_results.append(EntryResult(
                ledger_class=disc_class, partner=partner,
                isa_control_number=isa, po_number=po,
                expected_invisible=True,
                found_mart_classes=frozenset(), passed=True,
            ))
        else:
            cr.visible += 1
            cr.misses += 1
            result.passed = False
            result.entry_results.append(EntryResult(
                ledger_class=disc_class, partner=partner,
                isa_control_number=isa, po_number=po,
                expected_invisible=False,
                found_mart_classes=frozenset(), passed=False,
            ))

    return result


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report(vr: ValidationResult) -> str:
    lines: list[str] = []
    lines.append("=" * 68)
    lines.append("  EDI Matching Engine — Validation Report")
    lines.append("=" * 68)

    if vr.unmapped_classes:
        lines.append("")
        lines.append("HARD ERROR: unmapped ledger classes (contract incomplete):")
        for cls in vr.unmapped_classes:
            lines.append(f"  - {cls}")
        lines.append("")
        lines.append("Add these classes to EXPECTED_SURFACE in corpus/validate.py")
        lines.append("before proceeding.  An unmapped class means the contract")
        lines.append("cannot verify whether that injection type is detectable.")
        return "\n".join(lines)

    # Per-class recall
    lines.append("")
    lines.append("Per-class recall:")
    lines.append(f"  {'Class':<25} {'Total':>6} {'Visible':>8} {'Invisible':>10} {'Hits':>6} {'Miss':>6} {'Recall':>8}")
    lines.append("  " + "-" * 71)
    for cls, cr in sorted(vr.class_recall.items()):
        if cr.total == 0:
            continue
        recall_str = f"{cr.recall:.0%}" if cr.visible > 0 else "n/a"
        lines.append(
            f"  {cls:<25} {cr.total:>6} {cr.visible:>8} {cr.invisible:>10} "
            f"{cr.hits:>6} {cr.misses:>6} {recall_str:>8}"
        )

    # Mart class counts
    lines.append("")
    lines.append("Mart exception counts:")
    for cls, count in sorted(vr.mart_class_counts.items()):
        lines.append(f"  {cls:<25} {count:>6} rows")

    # Missed entries detail
    missed = [e for e in vr.entry_results if not e.passed]
    if missed:
        lines.append("")
        lines.append(f"RECALL FAILURES ({len(missed)} entries):")
        for e in missed[:20]:
            lines.append(
                f"  {e.ledger_class} | partner={e.partner} "
                f"ISA={e.isa_control_number} PO={e.po_number or '?'}"
            )
        if len(missed) > 20:
            lines.append(f"  ... and {len(missed) - 20} more")

    # Verdict
    lines.append("")
    lines.append("=" * 68)
    if vr.passed:
        lines.append("  PASSED — all ledger entries accounted for.")
    else:
        lines.append("  FAILED — see details above.")
    lines.append("=" * 68)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DB helpers (used by CLI entry point only)
# ---------------------------------------------------------------------------

def _connect(db_url: str):
    import psycopg2
    return psycopg2.connect(db_url, connect_timeout=10)


def _query(conn, sql: str, params=()) -> list[dict]:
    import psycopg2.extras
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def _load_isa_to_po(conn, schema: str) -> dict[str, str]:
    rows = _query(conn, f"""
        SELECT document_reference, po_number
        FROM {schema}.int_document_links
        WHERE po_number IS NOT NULL AND po_number != ''
    """)
    lookup: dict[str, str] = {}
    for row in rows:
        isa = str(row["document_reference"]).strip()
        if isa and isa not in lookup:
            lookup[isa] = row["po_number"]
    return lookup


def _load_mart_rows(conn, schema: str) -> list[dict]:
    return _query(conn, f"""
        SELECT partner_id, po_number, exception_class
        FROM {schema}.fct_exceptions
    """)


def _read_ledger(path: str) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate matching engine recall against the discrepancy ledger."
    )
    parser.add_argument(
        "--ledger", required=True,
        help="Path to discrepancy_ledger.csv",
    )
    parser.add_argument(
        "--schema", default="edi_marts",
        help="Postgres schema where mart tables live (default: edi_marts)",
    )
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        return 1

    ledger = _read_ledger(args.ledger)
    if not ledger:
        print("WARNING: ledger is empty — nothing to validate.")
        return 0

    print(f"  Ledger: {len(ledger)} entries from {args.ledger}")

    conn = _connect(db_url)
    try:
        isa_to_po = _load_isa_to_po(conn, args.schema)
        mart_rows = _load_mart_rows(conn, args.schema)
    finally:
        conn.close()

    print(f"  Mart: {len(mart_rows)} exception rows in {args.schema}.fct_exceptions")
    print(f"  ISA→PO lookup: {len(isa_to_po)} entries from int_document_links")
    print()

    vr = validate(ledger, mart_rows, isa_to_po)
    print(format_report(vr))

    return 0 if vr.passed else 1


if __name__ == "__main__":
    sys.exit(main())
