{{
  config(materialized='view')
}}

-- 997 ACK coverage check: for each outbound 856 and 810, determine whether
-- the trading partner responded with a 997 functional acknowledgment within
-- 48 hours.
--
-- Join key note: in the synthetic corpus, 997 ACKs store the ISA interchange
-- control number of the acknowledged document in AK1 element 2 (rather than
-- the GS group control number per the X12 standard). This avoids storing a
-- separate gs_control_number column in staging. The join therefore uses:
--     acknowledged_gs_control = isa_control_number::integer
-- Real-world deployments must extract and store gs_control_number from staging
-- tables and join on that instead (ISA and GS controls diverge in batch EDI).
--
-- Grain: one row per outbound document (856 or 810 unique by isa_control_number).
-- A single ISA may carry multiple line items; we de-duplicate to the document level.

with

-- outbound 856 documents (Cinderhaven → trading partner)
outbound_856 as (
    select distinct
        partner_id,
        isa_control_number,
        ship_date                   as doc_date,
        '856'                       as document_type,
        'SH'                        as expected_functional_id
    from {{ ref('stg_856_asns') }}
),

-- outbound 810 documents (Cinderhaven → trading partner)
outbound_810 as (
    select distinct
        partner_id,
        isa_control_number,
        invoice_date                as doc_date,
        '810'                       as document_type,
        'IN'                        as expected_functional_id
    from {{ ref('stg_810_invoices') }}
),

outbound_docs as (
    select * from outbound_856
    union all
    select * from outbound_810
),

acks as (
    select
        partner_id,
        acknowledged_gs_control,
        acknowledged_functional_id,
        ack_date,
        acceptance_code
    from {{ ref('stg_997_acks') }}
)

select
    d.partner_id,
    d.document_type,
    d.isa_control_number,
    d.doc_date,
    d.expected_functional_id,

    a.acknowledged_gs_control   is not null     as ack_received,
    a.ack_date,
    a.acceptance_code,

    -- flag ACKs outside the 48-hour window (late or missing)
    -- interval '48 hours' rather than + 2 (date integer): the boundary is
    -- 48 clock-hours from the document date (midnight), not "2 calendar days later".
    -- Both doc_date and ack_date are dates (no sub-day precision), so an ACK on
    -- exactly day D+2 tests as NOT late (date casts to midnight, equal to deadline,
    -- and the > comparison is false).
    case
        when a.ack_date is null                              then true   -- no ACK at all
        when a.ack_date > d.doc_date + interval '48 hours'  then true   -- received late
        else false
    end                                         as ack_missing_or_late,

    -- acceptance status: R = rejected (partner refused), E = accepted with errors
    case
        when a.acceptance_code is null          then 'no_ack'
        when a.acceptance_code = 'R'            then 'rejected'
        when a.acceptance_code = 'E'            then 'accepted_with_errors'
        else 'accepted'
    end                                         as ack_status

from outbound_docs d
left join acks a
    on  d.partner_id                  = a.partner_id
    and d.isa_control_number::integer = a.acknowledged_gs_control
    and d.expected_functional_id      = a.acknowledged_functional_id
