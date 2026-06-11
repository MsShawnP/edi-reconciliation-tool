{{
  config(materialized='table')
}}

-- Four-way match: 850 PO lines → 856 ASN items → 810 invoice lines → 820 payments.
--
-- UoM normalization: quantities are converted to the PO's UoM using the
-- uom_conversions seed before comparison. Walmart 810 invoices in eaches (EA)
-- while 850 orders in cases (CA); the seed carries the per-partner factor.
--
-- Tolerance thresholds are dbt variables so they can be overridden per engagement:
--   tolerance_qty_cases  (default: 1 case)
--   tolerance_dollar     (default: $5.00)
--
-- match_status values:
--   matched             — all four legs present within tolerance
--   ordered_not_asnd    — PO line has no matching ASN item
--   asnd_not_invoiced   — ASN present but no invoice for this PO/SKU
--   shipped_not_invoiced— shipped qty > invoiced qty beyond tolerance
--   invoiced_not_paid   — invoice present but no remittance payment
--   short_pay           — paid_amount < invoice_amount beyond tolerance
--   uom_mismatch        — quantities diverge only after UoM normalization
--   qty_mismatch        — ordered vs shipped outside tolerance (no UoM explanation)

{% set qty_tol    = var('tolerance_qty_cases', 1) %}
{% set dollar_tol = var('tolerance_dollar', 5)    %}

with

po as (
    select * from {{ ref('stg_850_pos') }}
),

-- aggregate ASN quantity per (partner_id, po_number, sku)
asn_agg as (
    select
        partner_id,
        po_number,
        sku,
        sum(quantity)        as shipped_qty,
        max(unit_of_measure) as shipped_uom
    from {{ ref('stg_856_asns') }}
    group by 1, 2, 3
),

-- aggregate invoice quantity per (partner_id, po_number, sku); exclude credits
invoice_agg as (
    select
        partner_id,
        po_number,
        sku,
        sum(quantity)          as invoiced_qty,
        max(unit_of_measure)   as invoiced_uom,
        max(invoice_number)    as invoice_number,
        -- invoice_amount is per-document; use max (same value repeated per line)
        max(invoice_amount)    as invoice_amount
    from {{ ref('stg_810_invoices') }}
    where not is_credit
    group by 1, 2, 3
),

-- aggregate payments per (partner_id, invoice_number)
payment_agg as (
    select
        partner_id,
        rmr_invoice_number     as invoice_number,
        sum(rmr_amount)        as paid_amount
    from {{ ref('stg_820_remittances') }}
    group by 1, 2
),

-- join all four legs (left from PO outward)
joined as (
    select
        po.partner_id,
        po.po_number,
        po.line_number,
        po.sku,
        po.unit_of_measure                          as po_uom,
        po.quantity                                 as ordered_qty,
        po.unit_price,

        asn.shipped_qty,
        asn.shipped_uom,
        -- normalize shipped qty to PO UoM
        case
            when asn.shipped_qty is null
                then 0::numeric
            when asn.shipped_uom = po.unit_of_measure or asn.shipped_uom is null
                then asn.shipped_qty
            else asn.shipped_qty * coalesce(
                (select conversion_factor
                 from {{ ref('uom_conversions') }}
                 where (partner_id = po.partner_id or partner_id = '')
                   and from_uom = asn.shipped_uom
                   and to_uom   = po.unit_of_measure
                 order by partner_id desc   -- partner-specific before fallback ('')
                 limit 1),
                1.0)
        end                                         as shipped_qty_normalized,

        inv.invoiced_qty,
        inv.invoiced_uom,
        -- normalize invoiced qty to PO UoM
        case
            when inv.invoiced_qty is null
                then 0::numeric
            when inv.invoiced_uom = po.unit_of_measure or inv.invoiced_uom is null
                then inv.invoiced_qty
            else inv.invoiced_qty * coalesce(
                (select conversion_factor
                 from {{ ref('uom_conversions') }}
                 where (partner_id = po.partner_id or partner_id = '')
                   and from_uom = inv.invoiced_uom
                   and to_uom   = po.unit_of_measure
                 order by partner_id desc
                 limit 1),
                1.0)
        end                                         as invoiced_qty_normalized,

        inv.invoice_number,
        inv.invoice_amount,
        pay.paid_amount,

        asn.shipped_qty    is not null              as has_asn,
        inv.invoiced_qty   is not null              as has_invoice,
        pay.paid_amount    is not null              as has_payment

    from po
    left join asn_agg     asn
        on  po.partner_id = asn.partner_id
        and po.po_number  = asn.po_number
        and po.sku        = asn.sku
    left join invoice_agg inv
        on  po.partner_id = inv.partner_id
        and po.po_number  = inv.po_number
        and po.sku        = inv.sku
    left join payment_agg pay
        on  inv.partner_id     = pay.partner_id
        and inv.invoice_number = pay.invoice_number
),

final as (
    select
        *,
        -- deltas (post-normalization)
        ordered_qty       - shipped_qty_normalized              as ordered_vs_shipped_delta,
        shipped_qty_normalized - invoiced_qty_normalized        as shipped_vs_invoiced_delta,
        coalesce(invoice_amount, 0) - coalesce(paid_amount, 0) as invoice_vs_paid_delta,

        case
            when not has_asn
                then 'ordered_not_asnd'
            when not has_invoice
                then 'asnd_not_invoiced'
            when abs(ordered_qty - shipped_qty_normalized) > {{ qty_tol }}
                 and shipped_uom != po_uom
                then 'uom_mismatch'
            when abs(ordered_qty - shipped_qty_normalized) > {{ qty_tol }}
                then 'qty_mismatch'
            when abs(shipped_qty_normalized - invoiced_qty_normalized) > {{ qty_tol }}
                then 'shipped_not_invoiced'
            when not has_payment
                then 'invoiced_not_paid'
            when abs(coalesce(invoice_amount, 0) - coalesce(paid_amount, 0)) > {{ dollar_tol }}
                then 'short_pay'
            else 'matched'
        end                                                      as match_status

    from joined
)

select * from final
