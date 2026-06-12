# EDI Reconciliation Tool

**Live:** https://reconcile.lailarallc.com

EDI acknowledgments confirm that documents arrived — nobody checks that their contents agree. For a specialty food brand trading 850/856/810/820 documents with three or more partners, content-level mismatches in quantity, price, and item identity leak revenue and accumulate chargebacks silently. This pipeline reconciles document contents across the full PO lifecycle and ranks every exception by dollar impact.

## Cinderhaven context

Built on the Cinderhaven synthetic dataset — a ~$25M specialty food brand,
50 SKUs across 5 product lines and 6 contracted retailers. Data is synthetic;
methodology and deliverables are real.

## What it does

- Generates a synthetic X12 corpus for three trading partners (Walmart, UNFI, KeHE) from Cinderhaven canonical orders, injects controlled discrepancies, and records each injection in a ledger
- Parses 850/856/810/820/852/997 documents into Postgres staging tables
- Matches documents across the PO lifecycle via multi-path key resolution in dbt, then surfaces content mismatches as dollar-ranked exceptions
- Validates matching-engine recall against the injected-discrepancy ledger — the pipeline proves it catches what it planted
- Serves a FastAPI dashboard: exception queue, 997 acknowledgment status, D3 PO lifecycle visual, and a failure-pattern catalog covering 7 exception classes

## Stack

- Python 3.13 — corpus generator, X12 parsing, loader, validation
- Postgres (psycopg2) — staging and mart schemas
- dbt (dbt-postgres) — matching models, staging + marts
- FastAPI + Jinja2 + uvicorn — dashboard
- D3.js — PO lifecycle visual
- pytest — 15 unit tests; 25 integration tests (require `DATABASE_URL`)
- Fly.io — deployment

## Data contract

**Canonical baseline:** 50 SKUs · 5 product lines (AS·PS·SC·DG·SB) · 6 retailers
(Walmart·Costco·Whole Foods·Sprouts·Kroger·Regional Group) · 10 channels
(6 retail + UNFI·KeHE·DPI + DTC)

Scoped to the three EDI trading partners (Walmart, UNFI, KeHE) — see
CINDERHAVEN_CANONICAL.md for the full platform spec.

## Run

```
git clone https://github.com/MsShawnP/edi-reconciliation-tool.git
cd edi-reconciliation-tool
pip install -r requirements-dev.txt   # runtime-only: requirements.txt
cp .env.example .env                  # set DATABASE_URL

make all     # corpus → parse → transform → validate
make serve   # dashboard at http://localhost:8000
make test    # pytest suite
```

Requires a running Postgres with the Cinderhaven canonical schema — see the
cinderhaven-data-platform Docker setup.

---

Built by [Lailara LLC](https://lailarallc.com) — data hygiene and analytics
consulting for specialty food brands scaling into national retail.
