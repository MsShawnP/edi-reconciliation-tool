# Finding: 820 Corpus Generator — RMR Segment at Wrong Grain

**Severity:** Low (mitigated by lifecycle cap/guard)
**Component:** Cinderhaven synthetic data generator — 820 Payment Order/Remittance Advice
**Discovered during:** EDI reconciliation tool UI fix #7

## Problem

The 820 corpus generator emits RMR (Remittance Detail) segments at line-item grain instead of invoice grain. This inflates the PAID case count in the `edi_marts.int_four_way_match` mart — raw paid quantities exceed invoiced quantities, which is structurally impossible.

Before mitigation, this produced PAID = 109M cases (later 28M after query dedup) against INVOICED = 11M. The lifecycle visual now caps PAID ≤ INVOICED and shows "+0 cases short-paid" in the funnel, which is acceptable but masks the real short-pay delta.

## Impact

- The lifecycle funnel's INVOICED → PAID callout cannot show an accurate short-pay delta until this is fixed.
- The exception dashboard is unaffected — the $17M Short Pay card pulls from the exception mart, not the lifecycle query.
- No downstream data integrity risk; the cap/guard prevents bad numbers from rendering.

## Fix

Change the 820 generator to emit one RMR segment per invoice, not per line item. After fixing, truncate raw 820 tables, re-run the generator, `dbt run`, and verify PAID ≤ INVOICED without the cap binding. The lifecycle visual should then show the correct short-pay delta naturally.

## Validation

After fix, confirm on the lifecycle page:
- PAID < INVOICED (short-pay delta is positive and plausible)
- `source: "live"` (sanity guard passes, no canonical fallback)
- Short-pay callout shows a non-zero case count consistent with the $17M on the exception dashboard
