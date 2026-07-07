{{
  config(materialized='view')
}}

-- 852 sell-through reconciliation: compares total distributor-reported
-- sell-through (852 product activity) against total shipped (856 ASN)
-- per partner and SKU.
--
-- Grain: one row per (partner_id, sku).
-- delta_qty = total_reported − total_shipped
-- Positive delta: distributor reports more sold than shipped.
-- Negative delta: distributor reports fewer sold than shipped.

with

activity as (
    select
        partner_id,
        sku,
        sum(quantity) as total_reported_qty
    from {{ ref('stg_852_activity') }}
    group by 1, 2
),

shipped as (
    select
        partner_id,
        sku,
        sum(quantity) as total_shipped_qty
    from {{ ref('stg_856_asns') }}
    group by 1, 2
)

select
    act.partner_id,
    act.sku,
    act.total_reported_qty,
    coalesce(shp.total_shipped_qty, 0)                          as total_shipped_qty,
    act.total_reported_qty - coalesce(shp.total_shipped_qty, 0) as delta_qty,
    abs(act.total_reported_qty - coalesce(shp.total_shipped_qty, 0)) > 0 as has_discrepancy
from activity act
left join shipped shp
    on  act.partner_id = shp.partner_id
    and act.sku        = shp.sku
