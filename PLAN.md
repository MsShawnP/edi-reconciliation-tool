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
- [ ] U8: Failure pattern catalog (7 exception classes)
- [ ] U9: Deployment + orchestration (Makefile + Fly.io)

## Definition of done for this arc

- [ ] Exception dashboard live at subdomain, showing all failure classes with dollar values
- [ ] PO lifecycle D3 visual renders and is LinkedIn-shareable
- [ ] Failure pattern catalog page published
- [ ] Synthetic X12 corpus committed to repo with generator script
- [ ] Matching SQL/dbt models in repo, documented
- [ ] 997 acknowledgment failure class visible in dashboard

---

## Arc history

When an arc completes, archive its goal, completion date, and outcome
here. Then start a new arc above. Provides continuity without bloating
the active plan.

### [Date completed] — [Goal]
- Outcome: [what shipped or what was decided]
- Tag: [git tag if one was created]

---

## Improvement history

Track when this project was reviewed and improved via /improve.
Each entry records what was found, what was fixed, and when to
check again.

<!-- Entries are added by /improve — don't delete this section -->
