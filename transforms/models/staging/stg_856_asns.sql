with source as (
    select * from {{ source('edi_raw', 'edi_856_asn_items') }}
),

staged as (
    select
        isa_control_number,
        partner_id,
        shipment_id,
        to_date(ship_date, 'YYYYMMDD') as ship_date,
        bol_number,
        header_po_number,
        line_number,
        sku,
        quantity::numeric              as quantity,
        unit_of_measure,
        hl_id,
        -- item_po_number: the PO from the O-level HL loop this item belongs to.
        -- For single-stop shipments equals header_po_number; for multi-stop (KeHE)
        -- each O-loop carries its own PO reference.
        coalesce(nullif(item_po_number, ''), header_po_number) as po_number,
        loaded_at
    from source
)

select * from staged
