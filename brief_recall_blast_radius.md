# Portfolio Project Brief: Recall Blast Radius Graph

**Created:** June 10, 2026
**Source:** `portfolio_priority_list_gtd.md` Next list
**Template:** `portfolio_brief_template.md`

**Status:** Brief stage
**Tier:** 1 (new dimension: food safety / traceability)
**Priority:** Next #2 — score 33, highest unbuilt brainstorm item; opens a domain (traceability) nothing shipped touches; folds in six sibling items.

### 1. The Pain

A retailer or the FDA calls: a lot of an ingredient is implicated. The CEO needs to answer, within hours: which of our lots used it, which SKUs, which shipments, which DCs, which retailers, which stores, how many cases are still in the supply chain vs. sold through — and who do we have to notify. At most $25M brands the answer lives in the co-packer's batch records (paper or PDF), the 3PL's shipment logs, and the ERP — none linked. The honest answer to "what's our blast radius?" is "give us three days," and in a recall, three days is the difference between a scoped withdrawal and a category-wide one.

- **Who feels it:** CEO existentially; QA/ops lead operationally; the CFO when the insurance and disposal invoices land.
- **When acute:** the day it happens. Before that, it's invisible — which is exactly the pitch.
- **Compounding:** FSMA 204 (Food Traceability Rule) makes lot-level traceability for foods on the Food Traceability List a regulatory requirement, with enforcement on a compliance clock — and retailers (Walmart, Kroger) are pushing FSMA-204-style KDE/CTE data requirements onto suppliers ahead of FDA enforcement regardless. **Verify the current FDA compliance date and major-retailer mandates at build time; do not publish a stale date.**

#### The Status Quo

A "mock recall" exercise done annually for SQF/BRC audit purposes, executed via frantic spreadsheet archaeology, documented as passing because the auditor watched. Zero capability between audits.

### 2. Why This Piece

- **Builds on:** the platform (orders/shipments/retailers already exist); adds the lot/batch dimension PDHA and the Product Master piece deliberately excluded.
- **Proves what isn't demonstrated:** graph thinking (traversal, network viz), the food-safety domain, and regulatory fluency (FSMA 204 KDEs/CTEs). Nothing in the portfolio touches quality/safety — a gap a food-industry reader notices.
- **Folds in:** recall geographic spread (#69), lot scope estimation (#82), scope forecasting (#90), scenario modeling (#96), comms readiness (#155), FSMA 204 readiness (#153), batch traceability (#107 as substrate). Seven backlog items, one piece.

### 3. The Portfolio Piece

**Working title:** *The Blast Radius: What a Recall Actually Touches* (alt: *"Lot 24-117 Has a Problem"*)

An interactive graph. The user picks a contaminated input — an ingredient lot, a production run, a packaging lot — and watches the contamination propagate through the genealogy: ingredient lot → batches → finished-goods lots → cases → shipments → DCs → retailers → stores/DTC orders. A scope panel updates live: units affected, units still in channel vs. estimated sold-through, disposal + logistics + fee cost estimate, and the notification list (which trading partners, which form of notice).

#### Structure

- **Part 1 — The hook:** "It's 2pm Friday. Your tomato supplier just called." A scenario opener, then the single scariest stat: the average direct cost of a recall for a food company (cite a defensible industry source — GMA/FMI figure commonly used; verify at build) against Cinderhaven's 3–5% net margin. One bad lot ≈ multiple years of profit.
- **Part 2 — The proof:** the interactive blast radius. Three preset scenarios (single ingredient lot / shared ingredient across product lines / packaging lot spanning everything) showing how radius scales non-linearly with where in the BOM the contamination sits. The "shared ingredient" scenario is the gut-punch: one chili lot touches 14 SKUs across 3 product lines.
- **Part 3 — The evidence:** the data model that makes it possible (lot genealogy tables, recursive traversal SQL), an FSMA 204 KDE/CTE mapping table (which Key Data Elements at which Critical Tracking Events Cinderhaven's data does/doesn't capture), and the readiness checklist.

#### The Margin Math

Scenario-based: Scenario B (shared ingredient) at Cinderhaven scale ≈ X cases in channel × disposal + freight + retailer handling fees + admin ≈ $600K–$1.2M direct, before lost shelf placement — modeled live in the tool, not asserted. Against $750K–$1.25M annual net income (3–5% of $25M), the framing writes itself.

#### Before / After

- **Before:** "give us three days" + a mock-recall binder.
- **After:** any lot, any direction (trace-forward and trace-back), scoped in minutes, with the notification list generated.

#### Who Else Sees This?

- **Primary:** CEO (existential risk framing).
- **Secondary:** QA manager (the person who runs mock recalls and knows the binder is theater) and the insurance broker.
- **Shared:** CEO sends QA the link with "can we do this?"

### 4. Technical Specification

- **Repo:** `recall-blast-radius` — "Lot-level trace-forward/trace-back for a specialty food brand. Pick a lot, see everything it touched."

| Tool | Role |
|------|------|
| Postgres | Lot genealogy tables (new platform dimension), recursive CTEs for traversal |
| dbt | Genealogy models + tests on the platform |
| Python (NetworkX) | Graph construction, scope computation, scenario generation |
| D3 (force/hierarchical) | The blast-radius visualization |
| FastAPI | Traversal API behind the interactive |
| Dagster | Asset integration with platform |

#### Deliverables

| Deliverable | Format | Purpose |
|------------|--------|---------|
| Interactive blast radius | Web app (subdomain) | The flagship interactive |
| Three preset scenarios | In-app | The narrative arc |
| FSMA 204 KDE/CTE mapping | Table/page | Regulatory credibility + audit hook |
| Traceability readiness checklist | Page + PDF | Lead magnet |
| Genealogy SQL + dbt models | Repo | Practitioner proof |

#### Deployment

Fly.io (FastAPI) + Cloudflare Pages, `recall.lailarallc.com`. Found via /work, the FSMA 204 SEO surface, and the checklist as shareable artifact.

#### Simulated Data Sources

Co-packer batch records (the messy source — model as if extracted from PDFs/spreadsheets), 3PL shipment logs, ERP production orders, retailer DC ship-to data. The genealogy should be *reconstructed* from these, mirroring the real engagement.

### 5. Skills Demonstrated

Graph modeling and traversal (recursive SQL + NetworkX), regulatory domain depth (FSMA 204, KDE/CTE, TLC), D3 network viz, scenario modeling, extending a governed platform with a new dimension cleanly.

### 6. Foot-in-the-Door Offering

- **Offering:** "Traceability Readiness Assessment" (with a live mock-recall drill as the centerpiece).
- **Format:** fixed-fee 2-week engagement, ending in a timed trace exercise.
- **Price range:** $15K–$25K.
- **Client gets:** KDE/CTE gap map against FSMA 204, lot-genealogy data assessment, timed mock-recall result with blast-radius report, remediation roadmap.
- **Client lift:** kickoff call + batch record samples, shipment log export, ERP production data. One ops contact for 2–3 hours total.

#### The DIY Defense

The graph looks like a viz problem. The real problem: lot genealogy doesn't exist as data — it's trapped in co-packer batch records with inconsistent lot-code formats, and reconstructing it requires knowing that lot codes mutate at repack, that catch-weight items break unit math, and that 3PL logs identify pallets (SSCC) not lots. The mapping layer is the engagement.

### 7. Marketing / Distribution

- **Portfolio:** new "Risk & Traceability" engagement card on /work.
- **LinkedIn:** screen capture of the shared-ingredient scenario propagating. Hook: "One lot of chili flakes. Fourteen SKUs. Three product lines. Can you draw this picture for your brand in under an hour?"
- **SEO:** "FSMA 204 compliance specialty food," "mock recall exercise," "lot traceability small food manufacturer." FSMA 204 search volume is real and the audience is exactly the buyer.
- **Gating:** checklist PDF optionally email-gated — first gated artifact; decide deliberately.

### 8. Competitor / Existing Content Scan

Traceability software vendors (FoodLogiQ, iFoodDS, Trustwell) publish FSMA 204 content — all of it "buy our platform." Consultancies publish compliance explainers with no working demonstration. **Gap:** nobody shows a working blast-radius on realistic data at the $25M scale. **Angle:** "see your recall before you have one" — capability demonstration, not compliance scolding.

### 9. Cinderhaven Integration

Extends the platform with new lot/batch genealogy tables — the first new platform dimension since Dimension & Weight. Must derive from canonical production volumes (don't invent revenue-inconsistent throughput). New seed needed for genealogy generation — follow the seed-isolation pattern (cf. distressed scenario, seed=300) and register in `CINDERHAVEN_CANONICAL.md` with drift-guard coverage. Reuses retailers/DCs/shipments as-is.

### 10. Tactical Notes

- **Verify FSMA 204 dates and the Food Traceability List status at build time.** A stale compliance date in a traceability piece is credibility suicide.
- Decide whether Cinderhaven SKUs are even FTL-covered (sauces with fresh ingredients vs shelf-stable) — the nuance itself is a credibility marker.
- Lot-code realism: different formats per co-packer, Julian dates, line codes.
- Keep the graph readable — blast radius for the packaging-lot scenario could be hundreds of nodes; aggregation strategy needed (collapse store level into counts).

#### The Credibility Marker

KDE/CTE vocabulary used correctly, lot-code mutation at repack, and the FTL-coverage nuance — the three things that signal someone who has actually read the rule and handled batch records.

#### Data Paranoia / Security

Medium — batch records and supplier identities are sensitive in real engagements. Narrative: drill runs on extracts, supplier names maskable (Anonymizer Path A exists — cross-sell it).

### 11. Open Questions

- [ ] Final title
- [ ] Trace-back (ingredient sourcing) in v1 or trace-forward only?
- [ ] Gate the checklist PDF or keep open?
- [ ] Preset-scenarios-only vs free lot picker (free picker = more data integrity work)
- [ ] Current FSMA 204 enforcement date + Walmart/Kroger supplier mandate status (research task)

### 12. Build Estimate

- **Effort:** Large (new platform dimension + graph viz + FastAPI app)
- **Dependencies:** platform (done); canonical registration of new genealogy seed
- **New skills:** graph traversal at viz scale; FSMA 204 research depth

#### Out of Scope

- No allergen-labeling consistency analysis (#156 stays separate)
- No FDA inspection database mining (#160)
- No real supplier/ingredient pricing data
- No "recall insurance" analysis (cut items stay cut)


---
## Cross-brief notes

- **Canonical governance applies to all five.** Briefs 2 and 3 generate new data (genealogy, X12 corpus): new isolated seeds, registered in `CINDERHAVEN_CANONICAL.md`, drift-guard coverage, injected-error ledgers as validation ground truth. Briefs 1, 4, 5 generate none and must reconcile exactly.
- **Hero SKU continuity:** CHP-0009 is the worked example in briefs 1 and 4; candidate hero lot for brief 2.
- **Research tasks before any build:** FSMA 204 current enforcement dates + retailer mandates (brief 2); GS1 Sunrise 2027 current status (brief 4). Both verified at build time, not from memory.
- **Sequencing within the five:** 1 → 2 → 3 → 4 → 5 as listed. Brief 4 can float anywhere as filler. Brief 5 wants 2 and 3 done first or ships with two stubbed questions.
