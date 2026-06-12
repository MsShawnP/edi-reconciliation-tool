# edi-reconciliation-tool — Current Work Plan

The current arc of work. Updated when the arc changes, not every
session. For session-by-session state, see HANDOFF.md.

---

## Goal — 2026-06-10 (clarify)

Build a portfolio piece demonstrating complete EDI content-level reconciliation — four-way match (850/856/810/820), 852 sell-through, and 997 acknowledgment tracking — across three synthetic trading partners (Walmart, UNFI, KeHE), structured to lead with CFO-visible dollar impact and prove the full methodology.

## Why this arc, why now

Next #3 on the portfolio priority list. Extends EDI Pre-flight from "is this document valid?" to "do these documents agree?" and consolidates ~30 backlog EDI items into one build. The complete piece makes Lailara the most credible EDI-literate data consultancy in the niche.

## Business question this arc answers

For a specialty food brand with 3+ EDI trading partners, where are the content-level mismatches across 850/856/810/820 documents, and what revenue is leaking or at chargeback risk because no one is reconciling them?

## Scope confirmed (2026-06-10)

**In v1:**
- Four-way match: 850 (ordered) vs 856 (shipped) vs 810 (invoiced) vs 820 (paid)
- 852 sell-through reconciliation (UNFI/KeHE distributor channel)
- 997 acknowledgment tracking
- Synthetic X12 corpus only — three partners with partner-specific quirks
- Structure: CFO-visible dollar impact leads; complete picture across all components follows

**All five deliverables required, no deadline:**
- Exception dashboard (web app)
- PO lifecycle D3 visual (the LinkedIn hook)
- Failure pattern catalog
- Synthetic X12 corpus + generator
- Matching SQL/dbt models

**Out of scope for v1:**
- Real-data client upload path (real data = paid engagement)
- Real-time/streaming reconciliation
- 830 forecast accuracy
- EDI onboarding diagnostics

## Tasks

Work in vertical slices — one section/feature end-to-end before moving
to the next. Visualizations get reviewed in their own slice, not
deferred to a polish phase.

Full plan: `docs/plans/2026-06-10-001-feat-edi-reconciliation-pipeline-plan.md`

**Phase 1 — Foundation**
- [x] U1: Discrepancy ledger schema + corpus generator scaffold
- [x] U2: Synthetic X12 corpus (Walmart, UNFI, KeHE)
- [x] U3: Pre-flight parser extension (all 6 doc types)
- [x] U4: Staging tables + dbt staging models
- *Gate: domain expert reviews corpus + ledger; tolerance thresholds confirmed*

**Phase 2 — Matching engine**
- [x] U5: Key resolution + four-way match + 852 + 997 + exception mart
- *Gate: validation script shows 100% recall, 0 false positives*

**Phase 3 — Portfolio surface**
- [x] U6: FastAPI/HTMX exception dashboard (CFO-first layout)
- [x] U7: D3 PO lifecycle visual (standalone SVG + dashboard embed)
- [x] U8: Failure pattern catalog (7 exception classes)
- [x] U9: Deployment + orchestration (Makefile + Fly.io)

## Definition of done for this arc

- [x] Exception dashboard live at subdomain, showing all failure classes with dollar values
- [x] PO lifecycle D3 visual renders and is LinkedIn-shareable
- [x] Failure pattern catalog page published
- [x] Synthetic X12 corpus committed to repo with generator script
- [x] Matching SQL/dbt models in repo, documented
- [x] 997 acknowledgment failure class visible in dashboard

---

## Arc history

When an arc completes, archive its goal, completion date, and outcome
here. Then start a new arc above. Provides continuity without bloating
the active plan.

### 2026-06-10 — EDI reconciliation pipeline (v1)
- Outcome: All 9 units shipped. Synthetic X12 corpus (Walmart/UNFI/KeHE), dbt four-way match engine, FastAPI/HTMX exception dashboard, D3 lifecycle visual, failure pattern catalog, Fly.io deploy. Live at https://reconcile.lailarallc.com
- Tag: v1.0.0 (2026-06-11)

---

## Deferred code-review findings

From the /ce:code-review pass (2026-06-11). These were triaged out of the immediate fix wave.
Fixed items (#4, #5, #23, #22, #11, #15) are committed; these stay open.

| # | Severity | Finding | Files | Notes |
|---|---|---|---|---|
| #12 | P2 | Untested injector types — mapping-drift and 997-missing-ack are injected but have no integration test verifying they appear in the exception mart | `corpus/generator/injector.py`, `tests/test_matching.py` | Low risk; corpus generation is correct; tests would catch regressions |
| #14 | P2 | Conditional assertion in `test_walmart_uom_normalization` — the assertion (`matched >= 1`) holds only if the injection rate leaves some clean Walmart orders; could become vacuous after injection-rate changes | `tests/test_matching.py:155` | Monitor if injection rate is raised above ~0.5 |
| #16 | P1 | Double-injection divergence — ledger counts vs mart row counts may not agree because some injections affect documents not matched by the four-way engine | `corpus/generator/injector.py`, `transforms/models/marts/fct_exceptions.sql` | **INVESTIGATED 2026-06-12 — structural, 5 root causes; awaiting direction call.** Full write-up + options A–D in `docs/finding-16-ledger-mart-divergence.md`. Figures stay unpublishable until resolved. Also found: `make validate` references a `corpus/validate` module that doesn't exist. |
| #17 | P2 | $0 dollar impact on price-less PO1 lines — if a 850 PO1 segment omits unit_price, ordered_not_asnd and similar exceptions show $0 impact | `transforms/models/marts/fct_exceptions.sql` | The eventual fix is labeling ("impact unpriced"), never imputing a number |
| #18 | P3 | Duplicate `_read_*_orders` helpers across partner generator modules | `corpus/generator/walmart.py`, `corpus/generator/unfi.py`, `corpus/generator/kehe.py` | Pure maintainability; no correctness issue |
| #19 | P3 | Duplicate `_connect()` helper in `tests/test_matching.py` — identical to the module-level helper | `tests/test_matching.py` | Remove the duplicate before the test file grows further |
| #24 | P2 | Agent-native parity gaps — no agent-callable tool surfaces exception data; dashboard is UI-only | `dashboard/routes/exceptions.py`, `dashboard/app.py` | Required if this tool is ever embedded in an AI workflow |

---

## Improvement history

Track when this project was reviewed and improved via /improve.
Each entry records what was found, what was fixed, and when to
check again.

<!-- Entries are added by /improve — don't delete this section -->
