# Portfolio Project Brief: EDI Reconciliation v2

**Created:** June 10, 2026
**Source:** `portfolio_priority_list_gtd.md` Next list
**Template:** `portfolio_brief_template.md`

**Status:** Brief stage
**Tier:** 1–2 (data engineering proof + revenue recovery)
**Priority:** Next #3 — consolidates ~30 backlog items into one build; extends shipped EDI Pre-flight from "is this document valid?" to "do these documents agree?"

### 1. The Pain

The buyer's EDI "works" — documents flow, orders ship, invoices go out. But nobody reconciles across document types. POs (850) that never got ASNs (856). Shipments with no invoice (810). Invoices short-paid on the remittance (820) with no one noticing because the 820 posts as a lump. Distributor 852 sell-through that doesn't tie to what was shipped. Each mismatch is either revenue leaking (unbilled shipments, uncontested short-pays) or a chargeback brewing (ASN timing/accuracy). The EDI provider's dashboard shows transmission success — green checkmarks — while the *content* disagrees document to document.

- **Who feels it:** CFO (the leakage), ops (the chargebacks), nobody by name — which is the problem.
- **When acute:** as soon as document volume exceeds what one person eyeballs — roughly 3+ EDI trading partners.
- **Compounding:** every partner adds spec quirks (UNFI promo coding, KeHE invoicing rules); mismatch volume scales with order volume; the dispute window expires whether you noticed or not.

#### The Status Quo

The EDI VAN/provider portal (transmission status only), the ERP (its own version of events), and a quarterly "why is AR off?" investigation that finds three months of expired disputes.

### 2. Why This Piece

- **Builds on:** EDI Pre-flight (validation of single documents — this is the natural v2), Deduction Recovery (the downstream consequence of these mismatches), Remittance Stub Parsing (the 820/stub side feeds the 810↔820 leg), OTIF Blind Spot (true OTIF from EDI timestamps lands here as a module).
- **Proves:** multi-document reconciliation logic — genuinely hard data engineering — and the deepest EDI fluency in the portfolio. Together with Pre-flight it makes the practice arguably the most credible EDI-literate data consultancy in the niche.
- **Consolidation:** absorbs the entire EDI 25–32 brainstorm cluster (~30 items) as modules. This is the piece that justifies all those folds.

### 3. The Portfolio Piece

**Working title:** *Green Checkmarks, Missing Money: The Four-Way Match Your EDI Provider Doesn't Do*

Anchor: **4-way triangulation** — 850 (ordered) vs 856 (shipped) vs 810 (invoiced) vs 820 (paid) — with the 852 sell-through reconciliation as the second act for the distributor channel.

#### Structure

- **Part 1 — The hook:** a single PO's lifecycle as a horizontal flow: ordered 150 cases → ASN'd 138 → invoiced 150 → paid 131. Three discrepancies, three different failure modes, all invisible in the provider dashboard. "Your EDI works. Your numbers don't match."
- **Part 2 — The proof:** the reconciliation engine on a year of Cinderhaven EDI traffic. Exception dashboard grouped by failure pattern: shipped-not-invoiced (revenue leak), invoiced-not-paid-in-full (short-pay), ordered-not-ASN'd (OTIF exposure), UoM mismatches (eaches vs cases — the classic), mapping drift (retailer item # ↔ internal SKU). Each exception carries a dollar value and a dispute-window clock. Module 2: 852 sell-through vs shipments for UNFI/KeHE — where did the inventory go?
- **Part 3 — The evidence:** the matching logic (SQL + Python, tolerance rules, UoM conversion tables), synthetic EDI document corpus (real X12 segment structure), and a "failure pattern catalog" documenting each mismatch type with its root cause and fix.

#### The Margin Math

Industry framing: unreconciled short-pays and unbilled shipments typically run 0.5–1.5% of EDI-channel revenue. At Cinderhaven's wholesale volume that's a low-six-figure annual number — computed live from the synthetic corpus, not asserted. Plus avoided ASN chargebacks (tie to shipped chargeback work).

#### Before / After

- **Before:** transmission dashboard says green; AR investigation every quarter finds expired disputes.
- **After:** daily exception list, dollar-ranked, dispute clocks visible, UoM and mapping errors caught at the document level.

#### Who Else Sees This?

- **Primary:** CFO/controller.
- **Secondary:** ops manager (the ASN/OTIF modules) and whoever administers the EDI provider relationship.
- **Shared:** CFO forwards the exception dashboard screenshot to the controller: "do we have this?"

### 4. Technical Specification

- **Repo:** `edi-reconciliation` — "Four-way EDI document matching (850/856/810/820) plus 852 sell-through reconciliation for a specialty food brand."

| Tool | Role |
|------|------|
| Python | X12 parsing (extend Pre-flight's parser), matching engine, tolerance/UoM logic |
| Postgres + dbt | Document staging, match models, exception marts on the platform |
| FastAPI + HTMX | Exception dashboard (consistent with Pre-flight's stack) |
| D3 | PO-lifecycle flow visual (the hook graphic) |
| Dagster | Pipeline orchestration |

#### Deliverables

| Deliverable | Format | Purpose |
|------------|--------|---------|
| Exception dashboard | Web app | The interactive proof |
| PO lifecycle visual | D3, embedded | The hook / LinkedIn asset |
| Failure pattern catalog | Page + repo doc | Practitioner credibility |
| Synthetic X12 corpus + generator | Repo | DE proof; reusable |
| Matching SQL/dbt models | Repo | Technical evaluation surface |

#### Deployment

Fly.io + subdomain (`reconcile.lailarallc.com` or fold under `edi.lailarallc.com/reconcile` — decide; same-domain strengthens the v1→v2 story).

#### Simulated Data Sources

Raw X12 files (850/856/810/820/852/997) per partner with partner-specific quirks (UNFI promo coding in the 850, KeHE invoice requirements), ERP order/shipment/invoice extracts that *almost* match, remittance data consistent with the Remittance Stub Parsing piece.

### 5. Skills Demonstrated

X12/EDI fluency at content level (not just syntax), multi-source reconciliation engine design, tolerance-rule and UoM-conversion handling, exception-driven workflow design, platform-integrated dbt modeling.

### 6. Foot-in-the-Door Offering

- **Offering:** "EDI Reconciliation Audit" — trailing 6–12 months of documents, four-way matched.
- **Format:** fixed-fee 2–3 weeks.
- **Price range:** $18K–$30K (priced against found money).
- **Client gets:** dollar-ranked exception ledger, recoverable short-pay list with dispute-window status, failure pattern report, ongoing-monitoring recommendation.
- **Client lift:** EDI archive export from the VAN/provider (they all support this) + ERP extracts. Near-zero client hours after kickoff.

#### The DIY Defense

The match looks like a VLOOKUP. It isn't: line-level matching across documents with different keys (PO line vs ASN item vs invoice line), UoM conversions that differ by partner, partial shipments splitting one 850 across multiple 856s, credit/rebill chains on the 810 side, and 820s that bundle dozens of invoices with adjustment codes. The tolerance rules *are* the product.

### 7. Marketing / Distribution

- **Portfolio:** /work engagement card; explicitly positioned as Pre-flight's sequel.
- **LinkedIn:** the PO lifecycle graphic (150 → 138 → 150 → 131). Hook: "Four documents, one PO, three discrepancies, zero alerts."
- **SEO:** "EDI reconciliation," "850 856 810 matching," "short pay recovery CPG," "852 sell-through reconciliation."
- **Shareability:** the failure pattern catalog — EDI coordinators will bookmark it.

### 8. Competitor / Existing Content Scan

EDI providers (SPS, TrueCommerce) market "visibility" but reconcile transmission, not content; deduction-management vendors (HighRadius et al.) attack the 820 side only, enterprise-priced. **Gap:** content-level four-way matching presented for the mid-market, with working code. **Angle:** the provider dashboard is the false comfort; the match is the truth.

### 9. Cinderhaven Integration

Needs a synthetic X12 corpus generated *from* canonical platform orders/shipments/invoices — documents must tie to canonical revenue and chargeback figures, then have controlled discrepancies injected. New seed, registered in `CINDERHAVEN_CANONICAL.md`, drift-guard covered. The injected-discrepancy ledger becomes the validation ground truth (like the trade-spend diagnostic's 59-check pattern).

### 10. Tactical Notes

- X12 realism is the credibility battlefield: segment/element structure, ISA/GS envelopes, 997 flow. Use Pre-flight's parser as the base; don't hand-wave the corpus.
- Scope discipline: the fold-list is enormous. v1 = 4-way match + 852 module + dashboard. Everything else (830 forecast accuracy, demand sensing, onboarding diagnostics) is a documented roadmap, not built.
- Decide the OTIF-from-timestamps overlap with shipped OTIF Blind Spot — reference it, don't rebuild it.

#### The Credibility Marker

UoM conversion (eaches/cases) as a named failure class, partial-shipment 850→multiple-856 matching, and UNFI 850 promo-coding quirks. The things only someone who has read real X12 knows to handle.

#### Data Paranoia / Security

High in real engagements — EDI archives contain full pricing and terms. Narrative: audit runs on client infrastructure or anonymized extracts (Anonymizer Path A cross-sell again).

### 11. Open Questions

- [ ] Anchor confirmation: 4-way triangulation (recommended) vs 852 sell-through as the lead
- [ ] Same subdomain as Pre-flight or new?
- [ ] How many trading partners in the corpus (3 feels right: Walmart direct, UNFI, KeHE)
- [ ] Whether 997 tracking makes v1 or roadmap

### 12. Build Estimate

- **Effort:** Large (corpus generation + matching engine + dashboard)
- **Dependencies:** platform (done); Remittance Stub Parsing redeploy (for 820-side consistency); Pre-flight parser reuse
- **New skills:** none fundamentally; X12 depth extension

#### Out of Scope

- 830/planning documents (roadmap only)
- Real-time/streaming reconciliation — batch is the honest mid-market reality
- EDI onboarding consulting content (#150 stays folded as roadmap note)
- Rebuilding OTIF logic — link to OTIF Blind Spot


---
## Cross-brief notes

- **Canonical governance applies to all five.** Briefs 2 and 3 generate new data (genealogy, X12 corpus): new isolated seeds, registered in `CINDERHAVEN_CANONICAL.md`, drift-guard coverage, injected-error ledgers as validation ground truth. Briefs 1, 4, 5 generate none and must reconcile exactly.
- **Hero SKU continuity:** CHP-0009 is the worked example in briefs 1 and 4; candidate hero lot for brief 2.
- **Research tasks before any build:** FSMA 204 current enforcement dates + retailer mandates (brief 2); GS1 Sunrise 2027 current status (brief 4). Both verified at build time, not from memory.
- **Sequencing within the five:** 1 → 2 → 3 → 4 → 5 as listed. Brief 4 can float anywhere as filler. Brief 5 wants 2 and 3 done first or ships with two stubbed questions.
