{{
  config(materialized='table')
}}

-- Exception mart: all discrepancy classes in a single fact table, dollar-ranked.
--
-- exception_class values (matches ledger DiscrepancyClass enum):
--   ordered_not_asnd        — 850 line with no 856 match
--   shipped_not_invoiced    — shipped qty > invoiced qty beyond tolerance
--   short_pay               — invoice amount > payment amount beyond tolerance
--   uom_mismatch            — UoM divergence between 850 and 856/810
--   qty_mismatch            — quantity variance (ordered vs shipped) outside tolerance
--   852_discrepancy         — sell-through ≠ shipped quantity for the period
--   missing_997_ack         — outbound document unacknowledged within 48-hour window
--
-- dollar_impact:
--   shipped_not_invoiced is SIGNED: positive = under-billed (brand owed),
--   negative = over-invoiced (credit risk). Other revenue-affecting classes
--   carry a positive dollar_impact. Aggregations must not net directions —
--   sum abs() for exposure. missing_997_ack is operational only — 0.
--
-- dispute_window:
--   short_pay: 30 days from payment_date (820 date)
--   chargebacks (shipped_not_invoiced, ordered_not_asnd, uom_mismatch): 60 days from doc date
--   others: null

with

four_way as (
    select * from {{ ref('int_four_way_match') }}
),

match_852 as (
    select * from {{ ref('int_852_match') }}
),

match_997 as (
    select * from {{ ref('int_997_match') }}
),

-- Pre-aggregate to avoid correlated subqueries that scan raw tables per row
latest_payment as (
    select partner_id, rmr_invoice_number, max(payment_date)::date as max_payment_date
    from {{ ref('stg_820_remittances') }}
    group by partner_id, rmr_invoice_number
),

avg_invoice_price as (
    select partner_id, sku, avg(unit_price) as avg_price
    from {{ ref('stg_810_invoices') }}
    group by partner_id, sku
),

-- ---------------------------------------------------------------------------
-- ordered_not_asnd: PO line with no ASN
-- ---------------------------------------------------------------------------
ordered_not_asnd as (
    select
        partner_id,
        po_number,
        sku,
        'ordered_not_asnd'                          as exception_class,
        ordered_qty * unit_price                    as dollar_impact,
        60                                          as dispute_window_days,
        -- no ASN exists for this class, so asn_date is NULL; use PO date instead
        po_date                                     as dispute_date_anchor,
        null::text                                  as invoice_number,
        match_status
    from four_way
    where match_status = 'ordered_not_asnd'
),

-- ---------------------------------------------------------------------------
-- shipped_not_invoiced: shipped qty ≠ invoiced qty beyond tolerance.
-- Positive dollar_impact = under-billed (shipped > invoiced, brand owed money).
-- Negative dollar_impact = over-invoiced (invoiced > shipped, credit risk).
-- ---------------------------------------------------------------------------
shipped_not_invoiced as (
    select
        partner_id,
        po_number,
        sku,
        'shipped_not_invoiced'                      as exception_class,
        shipped_vs_invoiced_delta * unit_price       as dollar_impact,
        60                                          as dispute_window_days,
        -- clock from ship date: brand shipped, discrepancy originates at the dock
        asn_date                                    as dispute_date_anchor,
        invoice_number,
        match_status
    from four_way
    where match_status = 'shipped_not_invoiced'
),

-- ---------------------------------------------------------------------------
-- short_pay: invoice amount > amount paid (beyond tolerance)
-- ---------------------------------------------------------------------------
short_pay as (
    -- One row per invoice_number: invoice_amount is the document total replicated
    -- on every SKU row, so without deduplication the delta is counted N times for
    -- an N-SKU invoice. DISTINCT ON (partner_id, invoice_number) keeps the first
    -- alphabetical SKU as a representative row — po_number/sku are display-only.
    select distinct on (f.partner_id, f.invoice_number)
        f.partner_id,
        f.po_number,
        f.sku,
        'short_pay'                                 as exception_class,
        abs(f.invoice_vs_paid_delta)                as dollar_impact,
        30                                          as dispute_window_days,
        lp.max_payment_date                         as dispute_date_anchor,
        f.invoice_number,
        f.match_status
    from four_way f
    left join latest_payment lp
        on lp.partner_id         = f.partner_id
       and lp.rmr_invoice_number = f.invoice_number
    where f.match_status = 'short_pay'
    order by f.partner_id, f.invoice_number, f.sku
),

-- ---------------------------------------------------------------------------
-- uom_mismatch: UoM divergence flags
-- ---------------------------------------------------------------------------
uom_mismatch as (
    select
        partner_id,
        po_number,
        sku,
        'uom_mismatch'                              as exception_class,
        abs(ordered_vs_shipped_delta) * unit_price  as dollar_impact,
        60                                          as dispute_window_days,
        -- clock from ship date: UoM divergence is detected from the ASN documents
        asn_date                                    as dispute_date_anchor,
        invoice_number,
        match_status
    from four_way
    where match_status = 'uom_mismatch'
),

-- ---------------------------------------------------------------------------
-- qty_mismatch: quantity variance (ordered vs shipped) outside tolerance
-- ---------------------------------------------------------------------------
qty_mismatch as (
    select
        partner_id,
        po_number,
        sku,
        'qty_mismatch'                              as exception_class,
        abs(ordered_vs_shipped_delta) * unit_price  as dollar_impact,
        60                                          as dispute_window_days,
        -- clock from ship date: quantity variance is a shipment-vs-order issue
        asn_date                                    as dispute_date_anchor,
        invoice_number,
        match_status
    from four_way
    where match_status = 'qty_mismatch'
),

-- ---------------------------------------------------------------------------
-- 852_discrepancy: sell-through ≠ shipped
-- ---------------------------------------------------------------------------
exc_852 as (
    select
        m.partner_id,
        null::text                                  as po_number,
        m.sku,
        '852_discrepancy'                           as exception_class,
        -- dollar impact approximated using shipped qty × avg 810 unit price
        abs(m.delta_qty) * coalesce(p.avg_price, 0) as dollar_impact,
        null::integer                               as dispute_window_days,
        null::date                                  as dispute_date_anchor,
        null::text                                  as invoice_number,
        '852_discrepancy'                           as match_status
    from match_852 m
    left join avg_invoice_price p
        on p.partner_id = m.partner_id
       and p.sku        = m.sku
    where m.has_discrepancy
),

-- ---------------------------------------------------------------------------
-- missing_997_ack: outbound document without ACK within window
-- ---------------------------------------------------------------------------
exc_997 as (
    select
        partner_id,
        null::text                                  as po_number,
        null::text                                  as sku,
        'missing_997_ack'                           as exception_class,
        0::numeric                                  as dollar_impact,
        null::integer                               as dispute_window_days,
        null::date                                  as dispute_date_anchor,
        null::text                                  as invoice_number,
        'missing_997_ack'                           as match_status
    from match_997
    where ack_missing_or_late
),

-- ---------------------------------------------------------------------------
-- Union all exception classes and add dispute window expiry
-- ---------------------------------------------------------------------------
all_exceptions as (
    select * from ordered_not_asnd
    union all
    select * from shipped_not_invoiced
    union all
    select * from short_pay
    union all
    select * from uom_mismatch
    union all
    select * from qty_mismatch
    union all
    select * from exc_852
    union all
    select * from exc_997
)

select
    partner_id,
    exception_class,
    po_number,
    sku,
    invoice_number,
    dollar_impact,
    dispute_window_days,
    dispute_date_anchor,
    -- expiry = dispute_date_anchor + window; null when no anchor or no window
    case
        when dispute_date_anchor is not null and dispute_window_days is not null
            then dispute_date_anchor + dispute_window_days * interval '1 day'
        else null
    end::date                                   as dispute_window_expires_at,
    -- urgency: expiry within 7 days
    case
        when dispute_date_anchor is not null
         and dispute_window_days is not null
         and (dispute_date_anchor + dispute_window_days * interval '1 day')::date
             <= current_date + 7
            then true
        else false
    end                                         as dispute_urgent,
    match_status,
    current_timestamp                           as mart_updated_at
from all_exceptions
