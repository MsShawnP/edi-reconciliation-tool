# edi-reconciliation-tool — Decisions Log

Permanent record of choices that should survive session turnover.
If a decision is reversed, strike it through and add the replacement
below — don't delete.

---

## Format

Each entry:
- **Date** — when decided
- **Decision** — one sentence, imperative voice
- **Why** — the reasoning, including what was tried and rejected
- **Scope** — what this applies to (file, chunk, deliverable, or "global")
- **Do not** — explicit anti-instructions, if any

---

## Architecture & Pipeline

### 2026-06-10 — Use Makefile + Python script for orchestration, not Dagster
- **Why:** Dagster is a full platform (daemon, scheduler, UI) that adds setup complexity without adding value to the portfolio story. The pipeline is linear (generate → parse → stage → match → serve). A Makefile is more transparent for a technical reviewer to follow.
- **Scope:** Global pipeline orchestration
- **Do not:** Add Dagster or any other orchestration platform in v1. If the pipeline grows to need scheduling, that decision gets its own entry.

### 2026-06-10 — Use multi-path key resolution (PO → ASN → Invoice), not a single PO anchor
- **Why:** In real EDI traffic, 820s (and sometimes 810s) arrive without PO references — especially from distributors like UNFI. A PO-only anchor would drop real-world documents. The three-tier fallback (PO Number primary, ASN/BOL secondary, Invoice Number tertiary) mirrors what a real engagement would need and is more defensible to technical evaluators. User confirmed: "in real life it is possible you don't have the PO so you have to look at the docs."
- **Scope:** `int_document_links.sql`, matching key schema globally
- **Do not:** Use bilateral match tables (850↔856, 856↔810 separately) — rejected in favor of the link-table approach.

### 2026-06-10 — Put matching logic in dbt (SQL), not Python
- **Why:** Deliberate portfolio signal — shows platform-integrated data engineering, not just scripting. Python layer handles parsing and loading only. Match logic in SQL is also easier for a technical evaluator to audit.
- **Scope:** U5 and all mart models
- **Do not:** Move match logic into Python for convenience.

### 2026-06-10 — Treat the discrepancy ledger as a first-class deliverable, not a test fixture
- **Why:** The ledger records exactly what was injected into the synthetic corpus, allowing the matching engine to be scored: found / missed / false-positive. This is the equivalent of the trade-spend diagnostic's 59-check pattern. It demonstrates to a potential client how the engine would be validated on their real data.
- **Scope:** U1, U2, U5 validation script
- **Do not:** Treat the ledger as internal-only scaffolding to be discarded after testing.

---

## Data & Schema

### 2026-06-10 — Use Postgres on the Cinderhaven platform, not DuckDB
- **Why:** The Cinderhaven data platform is live and is the SSOT for ~20 projects. Using Postgres keeps the matching models platform-integrated, which is part of the portfolio story. DuckDB was considered only when platform availability was uncertain; that uncertainty was resolved when user confirmed "it is the SSOT datasource for like 20 projects now."
- **Scope:** Database choice globally
- **Do not:** Introduce DuckDB as a "simpler" alternative.

### 2026-06-10 — Generate corpus from Cinderhaven canonical data, not independently random data
- **Why:** Dollar values in the exception mart must tie to canonical Cinderhaven revenue figures to be internally consistent with the platform story. Fully random synthetic data would not serve the Cinderhaven platform coherence narrative.
- **Scope:** Corpus generator (U1, U2)
- **Do not:** Generate documents with arbitrary dollar amounts. Pull from `CINDERHAVEN_CANONICAL.md` and register the new corpus seed there.

### 2026-06-10 — Store UoM conversion factors as a dbt seed CSV, not hardcoded in SQL or Python
- **Why:** Auditable, version-controlled, easily extended per engagement. A domain expert can open the CSV and verify the values. Hardcoded conversion factors are invisible and brittle.
- **Scope:** `transforms/seeds/uom_conversions.csv`
- **Do not:** Hardcode eaches/cases/inner-pack ratios in Python or SQL.

---

## Visualization

### 2026-06-10 — D3 lifecycle visual is a standalone SVG at LinkedIn dimensions (1200×628px) that also embeds in the dashboard
- **Why:** The visual is the primary distribution mechanism (LinkedIn hook). It must work without the dashboard being live. Embedding in the dashboard is secondary.
- **Scope:** U7, `visuals/po_lifecycle.svg`
- **Do not:** Make the lifecycle visual depend on the dashboard being deployed to share it.

---

## Output Formats

### 2026-06-10 — Dashboard layout: dollar-ranked exceptions above the fold; 997 ACK status as a clearly separated secondary layer labeled "For EDI/Ops Teams"
- **Why:** The portfolio piece is positioned at CFO/controller audiences. Revenue leakage and chargeback risk are the hook. 997 is operational, not revenue-facing; it belongs in a secondary layer so it doesn't dilute the CFO signal. Ordering is non-negotiable.
- **Scope:** U6, dashboard layout
- **Do not:** Merge 997 status into the main exception list. Keep it visually distinct and clearly labeled.

---

## Writing & Voice

### 2026-06-10 — Failure pattern catalog targets EDI coordinators and controllers, not technical implementers
- **Why:** The catalog is a deliverable for the prospect/client audience, not a developer reference. No jargon left unexplained. One sentence on what it is, root cause, detection logic, dollar formula, fix.
- **Scope:** U8, `catalog/failure_patterns.md`

---

## Scope

### 2026-06-10 — Synthetic corpus only in v1; no real-data client upload path
- **Why:** The portfolio piece uses synthetic data to prove the concept and position Lailara to run real-data engagements as paid work. User clarified: "the brief uses synthetic to show/prove the concept so people hire me to work on their real data." Real-data ingestion is built during a paid engagement, not in the portfolio piece.
- **Scope:** Global scope boundary
- **Do not:** Add a file upload UI or real-data ingestion path in v1.

### 2026-06-10 — All five deliverables required in v1; no deadline
- **Why:** User confirmed all five must land: exception dashboard, D3 lifecycle visual, failure pattern catalog, synthetic X12 corpus + generator, matching SQL/dbt models. No prioritization or staged drop. "There is no deadline."
- **Scope:** PLAN.md arc, definition of done
- **Do not:** Ship with any of the five deliverables missing.

### 2026-06-10 — Include 997 acknowledgment tracking in v1
- **Why:** User confirmed: "i want to include it." 997 is part of the complete reconciliation story, even though it is ops-facing rather than CFO-facing.
- **Scope:** R8, U5 (`int_997_match.sql`), dashboard secondary layer

---

## Python Conventions

### 2026-06-10 — Use TYPE_CHECKING guards in package __init__.py; callers import from submodules directly
- **Why:** Eager imports from submodules in `__init__.py` cause a RuntimeWarning in Python 3.12+ when running a submodule as `__main__` (e.g., `python -m corpus.generator.base`). The parent package is imported first, which imports the submodule, which then can't be set as `__main__`. Moving submodule imports under `TYPE_CHECKING` eliminates the warning. Callers import directly from the submodule path (`from corpus.generator.base import CanonicalOrder`), which is more explicit anyway.
- **Scope:** All `__init__.py` files in this project
- **Do not:** Import from sibling submodules at the top level of an `__init__.py`. Define Protocols, dataclasses, and type aliases inline; reference submodule types in `TYPE_CHECKING` blocks only.

---

## Reversed / Superseded

When a decision is overturned:
1. Strike through the original entry above (don't delete)
2. Add a new entry below with the replacement decision
3. Note the link in both directions

This preserves the history of why something is the way it is.
