# Finding #16 — Ledger vs Mart Divergence: Root Cause and Options

**Status:** Investigated 2026-06-12. Structural — needs a direction call before any fix lands.
**Verdict:** The divergence is real, has five independent causes, and is worse than the finding suggested: two injection classes can **never** surface in the mart under their own name, and one can produce **zero** mart rows at all. Dashboard figures must not be published as authoritative until a direction is chosen and `make validate` exists.

---

## What the finding claimed

> Ledger counts vs mart row counts may not agree because some injections affect documents not matched by the four-way engine.

That is true, but incomplete. Count agreement between `discrepancy_ledger.csv` and `fct_exceptions` is not just unverified — it is structurally impossible under the current design.

## Root causes (all confirmed by code read; integration DB not available locally)

### 1. Grain mismatch — ledger is per document, mart is per PO line

Every injector entry is one row per injected *document* ([injector.py](../corpus/generator/injector.py)). `fct_exceptions` emits one row per *PO line* (sku) from `int_four_way_match`. One removed 856 covering a 3-SKU PO → 1 ledger entry, 3 mart rows. Counts can never reconcile without a grain map.

### 2. Single-status precedence shadows shipped_not_invoiced — always

`int_four_way_match.sql` assigns exactly one `match_status` per line via CASE precedence: `ordered_not_asnd → asnd_not_invoiced → uom_mismatch → qty_mismatch → shipped_not_invoiced → …`.

Pre-injection, generators emit consistent docs (ordered = shipped = invoiced per line). `_bump_sn1` raises shipped by Δ, so `|ordered − shipped|` **and** `|shipped − invoiced|` both become Δ:

- Δ > tolerance (1 case): `qty_mismatch` fires first. **shipped_not_invoiced is unreachable for injected data.**
- Δ = 1 (≤ tolerance): no flag at all — the injection is silent.

With `delta = randint(1, max(1, orig//5))`, small orders inject Δ=1 frequently: silent. The mart's `shipped_not_invoiced` CTE can only fire on data where the *invoice* leg diverges alone — which the injector never produces.

### 3. Two classes have no mart representation at all

- **mapping_drift**: corrupting a 856 LIN to `UNKNOWN-ITEM` makes that ASN line join to no PO line. The real PO line loses (part of) its ASN → surfaces as `ordered_not_asnd`/`qty_mismatch`. `fct_exceptions` has no `mapping_drift` class — the ledger class literally cannot appear in the mart.
- **uom_mismatch (Walmart 810 +1 each)**: `_bump_it1_ea` adds 1 each; normalized that is 1/case-pack of a case — far inside the 1-case tolerance. The four-way's `uom_mismatch` branch tests the *856* leg (`shipped_uom != po_uom`), never the 810 leg. **Every Walmart uom injection produces a ledger entry and zero mart rows.** (Related: finding #12 — both untested classes are exactly the never-surfacing ones.)

### 4. Sequential injection compounds on the same 856 list

Order in `Injector.inject`: SN1 bump → 856 removal → LIN corruption. One 856 can be bumped, then removed (SNI ledger entry now refers to a document that does not exist in the corpus), or bumped *and* SKU-corrupted (two ledger entries, at most one mart status). No guard prevents multi-injection of one document.

### 5. Walmart ships every PO as two 856s; the removal index only knows the first

`po_to_856_idx` keeps the first 856 per PO. `_inject_ordered_not_asnd` removes that one document — but the PO's second shipment (40% split, [walmart.py](../corpus/generator/partners/walmart.py)) still exists, so `has_asn` stays true and the mart reports `qty_mismatch`, not `ordered_not_asnd`. The injected class and the surfaced class disagree by construction for Walmart.

### Also: `make validate` points at a module that does not exist

The Makefile's validate target runs `python -m corpus.validate` — there is no `corpus/validate.py` in the repo. The recall check that would have caught all of the above was never written. `make all` fails at the validate step.

## Why this blocks published figures

The dashboard's headline counts and dollar totals key off `exception_class`. Today those classes systematically misattribute injected truth (SNI → qty_mismatch, drift → ordered_not_asnd, Walmart ASN-removal → qty_mismatch) and silently drop two classes. Any screenshot or written figure derived from per-class counts would not survive an audit against the corpus's own ledger.

## Options

**A. Cascade-aware validation contract (recommended).** Keep the matching engine's single-status semantics — they mirror how a real four-way match triages (a line failing an earlier leg never reaches later checks; that is honest). Write `corpus/validate.py` with an explicit *expected-surface map*: each ledger class → the set of acceptable mart classes at the right grain (e.g. SNI(Δ>tol) → qty_mismatch on that PO's lines; drift → ordered_not_asnd/qty_mismatch; Walmart uom → expected-invisible). Validation asserts set-level recall per ledger entry, reports per-class precision, and fails on anything unmapped. Injector gains a one-injection-per-document guard (fixes cause 4) and a per-PO (not per-document) removal index (fixes cause 5). Mart unchanged; dashboard footnotes the cascade semantics.
*Effort: ~1 session. Honest about what a four-way match can and cannot attribute.*

**B. Make the mart attribute like the ledger.** Replace single-status CASE with one row per failed check (a line can be both qty_mismatch and short_pay), add mapping_drift detection (UNKNOWN-ITEM SKUs in ASN-side anti-join), tighten the uom branch to the 810 leg. Counts then approach ledger semantics directly.
*Effort: 2–3 sessions; touches every mart consumer (dashboard CTEs, D3 visual, catalog copy); changes dollar-impact aggregation semantics (double-counting risk).*

**C. Make the injector produce only mart-visible signatures.** Bump SN1 only beyond tolerance and only on invoice-leg (i.e., edit 810 instead), drop 856-removal for Walmart or remove *all* 856s per PO, delete the two never-surfacing classes from the corpus.
*Effort: ~1 session, but it weakens the portfolio story — the corpus would only contain discrepancies the engine is already known to catch. Circular validation.*

**D. Document-only.** Note the divergence in README/catalog, publish no per-class figures.
*Effort: minimal. Leaves `make validate` broken and the P1 standing.*

## Recommendation

**A**, with the two injector guards folded in. It is the only option that makes the recall claim ("the pipeline proves it catches what it planted") true without weakening the corpus or rewriting the mart. B is defensible later as a v2; C undermines the point of ledger-based validation; D leaves the Makefile broken.

**Stopping here for direction per the work order — no fix applied.**
