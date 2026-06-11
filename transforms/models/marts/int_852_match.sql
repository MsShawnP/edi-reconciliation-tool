{{
  config(materialized='view')
}}

-- 852 sell-through reconciliation: compares what the distributor reports as
-- sold-through (852 product activity) against what Cinderhaven shipped (856 ASN).
--
-- Grain: one row per (partner_id, report_id, sku, period).
-- delta_qty = reported_sell_through − shipped_to_partner_in_period
-- Positive delta: distributor reports more sold than we shipped (data error or
--   prior-period carry-forward).
-- Negative delta: distributor reports fewer sold than shipped (slow mover or
--   unreported sell-through — potential chargeback/deduction risk).

with

-- 852 sell-through aggregated per (partner, report, sku, period)
activity as (
    select
        partner_id,
        report_id,
        sku,
        period_start,
        period_end,
        sum(quantity)   as reported_qty
    from {{ ref('stg_852_activity') }}
    where period_start is not null
      and period_end   is not null
    group by 1, 2, 3, 4, 5
),

-- 856 shipments that fall within each activity reporting period
shipped_in_period as (
    select
        asn.partner_id,
        act.report_id,
        asn.sku,
        act.period_start,
        act.period_end,
        sum(asn.quantity)   as shipped_qty
    from {{ ref('stg_856_asns') }} asn
    join activity act
        on  asn.partner_id = act.partner_id
        and asn.sku        = act.sku
        and asn.ship_date  between act.period_start and act.period_end
    group by 1, 2, 3, 4, 5
)

select
    act.partner_id,
    act.report_id,
    act.sku,
    act.period_start,
    act.period_end,
    act.reported_qty,
    coalesce(sip.shipped_qty, 0)                            as shipped_qty,
    act.reported_qty - coalesce(sip.shipped_qty, 0)         as delta_qty,
    abs(act.reported_qty - coalesce(sip.shipped_qty, 0)) > 0 as has_discrepancy
from activity act
left join shipped_in_period sip
    on  act.partner_id  = sip.partner_id
    and act.report_id   = sip.report_id
    and act.sku         = sip.sku
