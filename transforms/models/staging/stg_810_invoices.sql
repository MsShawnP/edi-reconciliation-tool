with source as (
    select * from {{ source('edi_raw', 'edi_810_invoice_lines') }}
),

staged as (
    select
        isa_control_number,
        partner_id,
        invoice_number,
        to_date(invoice_date, 'YYYYMMDD') as invoice_date,
        po_number,
        total_amount::numeric             as invoice_amount,
        is_credit::boolean,
        nullif(original_invoice_number, '')    as original_invoice_number,
        nullif(distributor_invoice_number, '') as distributor_invoice_number,
        line_number,
        sku,
        quantity::numeric  as quantity,
        unit_of_measure,
        unit_price::numeric as unit_price,
        loaded_at
    from source
)

select * from staged
