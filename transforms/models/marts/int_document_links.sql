{{
  config(materialized='view')
}}

-- Multi-path key resolution: resolves every 856/810/820 to its canonical PO anchor.
--
-- Tier 1 (po_direct):   document carries an explicit PO Number reference.
-- Tier 2 (invoice_fallback): 820 has no PO ref → join via rmr_invoice_number → 810 → PO.
-- Tier 3 (orphan):      no resolution path found; po_number is null.
--
-- 997 ACKs are resolved separately in int_997_match; they do not appear here
-- because ACK coverage is an operational check, not a revenue-anchor join.

with

-- ---------------------------------------------------------------------------
-- 856 → PO (po_number already resolved from HL loops in stg_856_asns)
-- ---------------------------------------------------------------------------
asn_links as (
    select distinct
        partner_id,
        po_number,
        '856'              as document_type,
        isa_control_number as document_reference,
        shipment_id        as document_key,
        'po_direct'        as resolution_path
    from {{ ref('stg_856_asns') }}
    where po_number is not null
      and po_number != ''
),

-- ---------------------------------------------------------------------------
-- 810 → PO (BIG04 carries PO number for all three partners in our corpus)
-- ---------------------------------------------------------------------------
invoice_links as (
    select distinct
        partner_id,
        po_number,
        '810'              as document_type,
        isa_control_number as document_reference,
        invoice_number     as document_key,
        'po_direct'        as resolution_path
    from {{ ref('stg_810_invoices') }}
    where po_number is not null
      and po_number != ''
),

-- ---------------------------------------------------------------------------
-- 820 → PO (direct: po_number present from REF*PO)
-- ---------------------------------------------------------------------------
remittance_links_direct as (
    select distinct
        partner_id,
        po_number,
        '820'              as document_type,
        isa_control_number as document_reference,
        rmr_invoice_number as document_key,
        'po_direct'        as resolution_path
    from {{ ref('stg_820_remittances') }}
    where po_number is not null
      and po_number != ''
),

-- ---------------------------------------------------------------------------
-- 820 → PO (invoice fallback: UNFI 820 omits REF*PO; resolve via 810)
-- ---------------------------------------------------------------------------
remittance_links_invoice_fallback as (
    select distinct
        rem.partner_id,
        inv.po_number,
        '820'                  as document_type,
        rem.isa_control_number as document_reference,
        rem.rmr_invoice_number as document_key,
        'invoice_fallback'     as resolution_path
    from {{ ref('stg_820_remittances') }} rem
    join {{ ref('stg_810_invoices') }} inv
        on  rem.partner_id         = inv.partner_id
        and rem.rmr_invoice_number = inv.invoice_number
    where (rem.po_number is null or rem.po_number = '')
      and inv.po_number is not null
      and inv.po_number != ''
),

-- ---------------------------------------------------------------------------
-- 820 orphan: no po_number and no matching 810 invoice
-- ---------------------------------------------------------------------------
remittance_links_orphan as (
    select distinct
        rem.partner_id,
        null::text             as po_number,
        '820'                  as document_type,
        rem.isa_control_number as document_reference,
        rem.rmr_invoice_number as document_key,
        'orphan'               as resolution_path
    from {{ ref('stg_820_remittances') }} rem
    left join {{ ref('stg_810_invoices') }} inv
        on  rem.partner_id         = inv.partner_id
        and rem.rmr_invoice_number = inv.invoice_number
    where (rem.po_number is null or rem.po_number = '')
      and inv.invoice_number is null
)

select * from asn_links
union all
select * from invoice_links
union all
select * from remittance_links_direct
union all
select * from remittance_links_invoice_fallback
union all
select * from remittance_links_orphan
