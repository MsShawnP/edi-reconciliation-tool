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
--   Revenue-affecting classes carry a positive dollar_impact.
--   missing_997_ack is operational only — dollar_impact is 0.
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
        null::date                                  as dispute_date_anchor,
        null::text                                  as invoice_number,
        match_status
    from four_way
    where match_status = 'ordered_not_asnd'
),

-- ---------------------------------------------------------------------------
-- shipped_not_invoiced: shipped more than invoiced (beyond tolerance)
-- ---------------------------------------------------------------------------
shipped_not_invoiced as (
    select
        partner_id,
        po_number,
        sku,
        'shipped_not_invoiced'                      as exception_class,
        abs(shipped_vs_invoiced_delta) * unit_price as dollar_impact,
        60                                          as dispute_window_days,
        null::date                                  as dispute_date_anchor,
        invoice_number,
        match_status
    from four_way
    where match_status = 'shipped_not_invoiced'
),

-- ---------------------------------------------------------------------------
-- short_pay: invoice amount > amount paid (beyond tolerance)
-- ---------------------------------------------------------------------------
short_pay as (
    select
        f.partner_id,
        f.po_number,
        f.sku,
        'short_pay'                                 as exception_class,
        abs(f.invoice_vs_paid_delta)                as dollar_impact,
        30                                          as dispute_window_days,
        -- dispute clock starts from the payment date (820)
        (select max(payment_date)
         from {{ ref('stg_820_remittances') }} r
         where r.partner_id = f.partner_id
           and r.rmr_invoice_number = f.invoice_number)::date as dispute_date_anchor,
        f.invoice_number,
        f.match_status
    from four_way f
    where f.match_status = 'short_pay'
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
        null::date                                  as dispute_date_anchor,
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
        null::date                                  as dispute_date_anchor,
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
        partner_id,
        null::text                                  as po_number,
        sku,
        '852_discrepancy'                           as exception_class,
        -- dollar impact approximated using shipped qty × avg 810 unit price
        abs(delta_qty) * coalesce(
            (select avg(unit_price)
             from {{ ref('stg_810_invoices') }} inv
             where inv.partner_id = match_852.partner_id
               and inv.sku        = match_852.sku),
            0)                                      as dollar_impact,
        null::integer                               as dispute_window_days,
        null::date                                  as dispute_date_anchor,
        null::text                                  as invoice_number,
        '852_discrepancy'                           as match_status
    from match_852
    where has_discrepancy
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
