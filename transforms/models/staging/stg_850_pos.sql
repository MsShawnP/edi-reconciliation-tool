with source as (
    select * from {{ source('edi_raw', 'edi_850_pos_lines') }}
),

staged as (
    select
        isa_control_number,
        partner_id,
        po_number,
        -- YYYYMMDD text → date
        to_date(po_date, 'YYYYMMDD')    as po_date,
        line_number,
        sku,
        quantity::numeric               as quantity,
        unit_of_measure,
        unit_price::numeric             as unit_price,
        promo_allowance::numeric        as promo_allowance,
        loaded_at
    from source
)

select * from staged
