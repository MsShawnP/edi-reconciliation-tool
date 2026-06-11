with source as (
    select * from {{ source('edi_raw', 'edi_820_remittance_lines') }}
),

staged as (
    select
        isa_control_number,
        partner_id,
        payment_amount::numeric          as payment_amount,
        to_date(payment_date, 'YYYYMMDD') as payment_date,
        header_invoice_number,
        -- po_number may be empty for UNFI remittances that omit REF*PO.
        -- Key resolution in int_document_links falls back to invoice number.
        nullif(po_number, '') as po_number,
        rmr_invoice_number,
        rmr_amount::numeric  as rmr_amount,
        loaded_at
    from source
)

select * from staged
