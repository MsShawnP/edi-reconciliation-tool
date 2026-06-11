# EDI Reconciliation — Failure Pattern Catalog

Seven exception classes produced by the four-way match engine. Each entry covers what the exception is, which documents diverge, how dollar impact is calculated, and the dispute window that governs remediation timing.

---

## 1. Ordered, Not ASN'd

**Exception class:** `ordered_not_asnd`
**Documents involved:** 850 Purchase Order → (missing 856 ASN)
**Dollar impact:** `ordered_qty × unit_price`
**Dispute window:** 60 days from PO date (OTIF chargeback window)

### What it is

A line item on a 850 PO has no matching 856 Advance Ship Notice for the same SKU and trading partner. The supplier either did not ship the ordered goods or shipped without sending an ASN.

### Why it matters

Retail OTIF (On-Time In-Full) programs penalize suppliers for orders that are not acknowledged with an ASN before the delivery window closes. Without an ASN, the retailer's WMS cannot receive the shipment, creating chargeback exposure equal to the full line value.

### How it surfaces in X12

The matching engine joins `stg_850_pos` to `stg_856_asns` on `(partner_id, po_number, sku)`. Rows in the 850 with no 856 counterpart within the match tolerance window become `ordered_not_asnd` exceptions.

### Partner patterns in the synthetic corpus

| Partner | Quirk | Typical cause |
|---------|-------|---------------|
| Walmart | ASN required before 10am on ship date | High OTIF penalty — any missing ASN is an immediate chargeback trigger |
| UNFI | Ship-confirm via 856 optional on promo lines | Missing ASN may not trigger penalty but breaks inventory visibility |
| KeHE | Multi-stop 856 with O-level HL loops | ASN key resolution uses BOL number when PO ref is absent |

### Example

```
PO 850-2024-001 (Walmart) — 24 cases SKU-GRANOLA-6PK @ $47.50 = $1,140 at risk
No 856 found for this PO line within the match window
→ ordered_not_asnd exception: $1,140 dollar_impact, 60-day dispute window
```

---

## 2. Shipped, Not Invoiced

**Exception class:** `shipped_not_invoiced`
**Documents involved:** 856 ASN ↔ 810 Invoice (quantity divergence)
**Dollar impact:** `abs(shipped_qty − invoiced_qty) × unit_price`
**Dispute window:** 60 days from invoice date

### What it is

The 856 ASN shows more units shipped than the 810 invoice covers. The gap represents goods delivered to the retailer that the supplier has not billed for — revenue left uncollected.

### Why it matters

Shipped-not-invoiced is an underbilling event. The supplier absorbs the cost of goods without receiving payment. Over time, systematic underbilling compounds into material revenue leakage. The 60-day window mirrors chargeback dispute timelines: after it closes, the retailer has little obligation to reconcile.

### How it surfaces in X12

The engine compares `shipped_qty_normalized` (from 856, UoM-normalized) against `invoiced_qty_normalized` (from 810). Divergences beyond the configured tolerance (default: ±1%) flag as `shipped_not_invoiced`.

### Partner patterns in the synthetic corpus

| Partner | Quirk | Typical cause |
|---------|-------|---------------|
| KeHE | REF*IA (internal account) on 810; key resolution uses this to join to PO | Missing REF*IA causes invoice orphaning — ship matches PO, invoice doesn't |
| UNFI | Credit + rebill pattern on 3rd order; credit memo reduces invoiced_qty | Rebill delay creates a temporary shipped_not_invoiced exception |

### Example

```
PO 856-2024-012 (KeHE) — 24 cases shipped
810 invoice covers 20 cases only
→ shipped_not_invoiced: 4 cases × $47.50 = $190 unbilled
```

---

## 3. Short Pay

**Exception class:** `short_pay`
**Documents involved:** 810 Invoice ↔ 820 Remittance (dollar divergence)
**Dollar impact:** `abs(invoice_amount − paid_amount)` in dollars
**Dispute window:** 30 days from payment date (820 date)

### What it is

The 820 Payment Order/Remittance Advice shows a payment amount lower than the 810 invoice amount, beyond the configured tolerance. The retailer deducted from the invoice — either legitimately (earned deductions) or as an unauthorized chargeback.

### Why it matters

Short pays are the most time-sensitive exception: the dispute window is 30 days from the 820 payment date, shorter than any other exception class. Unauthorized deductions that are not disputed within the window become permanent write-offs. Short pay is the highest-dollar-impact exception class for most specialty food brands.

### How it surfaces in X12

The engine matches 820 remittance records to 810 invoices via `invoice_number` reference. Dollar differences exceeding the tolerance flag as `short_pay`. Dispute urgency is set when `dispute_window_expires_at ≤ current_date + 7`.

### Partner patterns in the synthetic corpus

| Partner | Quirk | Typical cause |
|---------|-------|---------------|
| UNFI | Every 3rd 820 omits `REF*PO` — invoice number is the only match key | Missing PO ref breaks join to 850; short pay stands alone, harder to dispute |
| Walmart | High deduction volume; deduction reason codes embedded in REF segments | Must decode reason code before disputing |

### Example

```
810 invoice WMT-INV-055: $1,140.00 for 24 cases
820 remittance: $898.50 paid
→ short_pay: $241.50 deducted, 30-day dispute window
   dispute_window_expires_at: payment_date + 30 days
```

---

## 4. UoM Mismatch

**Exception class:** `uom_mismatch`
**Documents involved:** 850 ↔ 856 ↔ 810 (unit-of-measure divergence)
**Dollar impact:** `abs(ordered_vs_shipped_delta) × unit_price` after normalization attempt
**Dispute window:** 60 days

### What it is

The unit of measure in the 850 PO (PO1 segment) does not match the unit of measure in the 856 ASN (IT1 segment) or the 810 invoice, and the normalization lookup (via `uom_conversions.csv` seed) cannot resolve the divergence. The engine records a quantity delta using the normalized values.

### Why it matters

UoM mismatches are stealth errors. The document counts look plausible (both say "24") but one side means cases and the other means eaches. A 12-count case pack means the retailer ordered 24 cases (288 units) but received 24 eaches (2 cases). The dollar exposure can be large while the exception appears minor at face value.

### How it surfaces in X12

The staging models normalize all quantities to cases using `uom_conversions.csv`. When the resulting normalized quantities diverge, the engine checks whether the source documents had mismatched UoM codes (CA/CS/EA/PK). If the normalization itself is the source of the gap, the exception is `uom_mismatch` rather than `qty_mismatch`.

### Partner patterns in the synthetic corpus

| Partner | Quirk | Typical cause |
|---------|-------|---------------|
| Walmart | 850 PO1 in CA (cases); 856 IT1 in EA (eaches) | Walmart eaches quirk: IT1 carries eaches, PO1 carries cases. Without the UoM seed row, every Walmart line misfires |
| UNFI | SLN promo segment on 850 PO1 uses different UoM than line item | Promo bonus quantity confuses the normalizer |

### Example

```
850 PO: 24 CA (cases) of SKU-GRANOLA-6PK (case_pack = 6)
856 IT1: 24 EA (eaches)
Normalized: 24 cases ordered vs 4 cases shipped
→ uom_mismatch: 20 case delta × $47.50 = $950 exposure
```

---

## 5. Quantity Mismatch

**Exception class:** `qty_mismatch`
**Documents involved:** 850 ↔ 856 (normalized quantity variance)
**Dollar impact:** `abs(ordered_qty − shipped_qty_normalized) × unit_price`
**Dispute window:** 60 days

### What it is

After UoM normalization, the ordered quantity (850 PO1) and shipped quantity (856 IT1) diverge beyond the configured tolerance. Both documents use consistent units; the supplier simply shipped a different quantity than ordered.

### Why it matters

Short-ships create OTIF exposure and may trigger vendor compliance chargebacks. Overshipments can result in unauthorized deductions (retailer returns excess at supplier cost) or warehouse refusal. The distinction from `uom_mismatch` is that here the units agree — the quantities themselves differ.

### How it surfaces in X12

`int_four_way_match` computes `ordered_vs_shipped_delta = ordered_qty − shipped_qty_normalized`. Where `abs(delta) > tolerance` and UoM codes match, the exception is `qty_mismatch`.

### Example

```
850 PO: 48 cases SKU-OAT-BARS-12CT
856 ASN: 36 cases shipped (short-ship — ran out of stock)
→ qty_mismatch: 12-case variance × $47.50 = $570 chargeback exposure
```

---

## 6. 852 Sell-Through Gap

**Exception class:** `852_discrepancy`
**Documents involved:** 852 Product Activity ↔ 856 shipped quantities (period reconciliation)
**Dollar impact:** `abs(sell_through_qty − shipped_qty) × avg(unit_price from 810)`
**Dispute window:** None — velocity signal, not a dispute

### What it is

The 852 Product Activity Data report (distributor sell-through) shows units sold to end consumers that do not reconcile with the quantities the supplier shipped to the distributor in the same period. Either the distributor is reporting lower sell-through than actual (destock risk) or the supplier shipped less than what was sold (stockout risk).

### Why it matters

For brands selling through UNFI or KeHE, the 852 is the only visibility into what is actually moving off distributor warehouse shelves. A systematic sell-through gap signals either a forecasting problem (ordering too little, stockouts) or a reporting problem (distributor sell-through data is stale or wrong). Neither is visible without this reconciliation.

### How it surfaces in X12

The 852 carries sell-through data in WT (warehouse transfer) and QA (quantity available) segments. `int_852_match` joins the period-level 852 totals by `(partner_id, sku, period)` to the sum of shipped quantities from 856 ASNs in the same window. Gaps beyond tolerance set `has_discrepancy = true`.

### Partner patterns in the synthetic corpus

| Partner | Quirk | Typical cause |
|---------|-------|---------------|
| UNFI | 852 sent weekly; ASNs are event-driven | Week-boundary effects — a Monday ASN falls in a different 852 period |
| KeHE | 852 aggregates multi-DC inventory; ASNs are per-DC | Aggregation mismatch when shipments cross DCs |

### Example

```
UNFI 852 (week of 2024-02-05): 96 cases SKU-GRANOLA-6PK sold
856 ASNs in the same period: 120 cases shipped
→ 852_discrepancy: 24-case gap — distributor sold less than shipped (inventory building or return risk)
```

---

## 7. Missing 997 ACK

**Exception class:** `missing_997_ack`
**Documents involved:** 997 Functional Acknowledgment (transmission confirmation)
**Dollar impact:** $0 — operational only
**Dispute window:** None

### What it is

An outbound transaction set (856 ASN, 810 invoice, 820 payment) was transmitted to the trading partner but no 997 functional acknowledgment was received within the 48-hour SLA window. The document may have been dropped, rejected by the partner's EDI translator, or failed to reach the VAN.

### Why it matters

Without a 997 ACK, the supplier cannot confirm that the trading partner received and accepted the document. A dropped 856 ASN means the retailer's WMS will refuse the physical shipment at dock. A dropped 810 invoice means the payment cycle never starts. Missing ACKs surface transmission failures before they become financial losses.

### How it surfaces in X12

`int_997_match` joins every outbound ISA control number to any received 997 with a matching GS control number. Records without a matching 997 within the 48-hour window, or with `ack_status = 'rejected'` or `'accepted_with_errors'`, set `ack_missing_or_late = true`.

### ACK status codes

| Status | Meaning |
|--------|---------|
| `accepted` | Trading partner received and processed the document |
| `accepted_with_errors` | Accepted but contains non-fatal errors — review required |
| `rejected` | Trading partner's translator rejected the document entirely |
| `missing` | No 997 received within the 48-hour SLA window |
| `late` | 997 received but after the SLA window |

### Partner patterns in the synthetic corpus

| Partner | Quirk | Typical cause |
|---------|-------|---------------|
| Walmart | High ACK SLA enforcement — 997 within 24 hours | Any delay triggers AS2 retransmission requirement |
| UNFI | 997 sometimes omitted for test ISA envelopes | ISA11 qualifier check required to filter test traffic |

### Example

```
856 ASN sent to KeHE — ISA control 000000042
No 997 received within 48 hours
→ missing_997_ack exception (operational, $0 dollar impact)
   Check VAN delivery logs; retransmit if no delivery confirmation
```

---

## Dispute window summary

| Exception class | Window | Clock starts |
|----------------|--------|-------------|
| ordered_not_asnd | 60 days | PO date |
| shipped_not_invoiced | 60 days | Invoice date |
| short_pay | 30 days | Payment date (820) |
| uom_mismatch | 60 days | Invoice date |
| qty_mismatch | 60 days | Invoice date |
| 852_discrepancy | None | — |
| missing_997_ack | None | — |

## Dollar impact formulas

| Exception class | Formula |
|----------------|---------|
| ordered_not_asnd | `ordered_qty × unit_price` |
| shipped_not_invoiced | `abs(shipped_qty − invoiced_qty) × unit_price` |
| short_pay | `abs(invoice_amount − paid_amount)` |
| uom_mismatch | `abs(ordered_vs_shipped_delta) × unit_price` |
| qty_mismatch | `abs(ordered_qty − shipped_qty_normalized) × unit_price` |
| 852_discrepancy | `abs(sell_through_qty − shipped_qty) × avg(unit_price)` |
| missing_997_ack | `$0` |
