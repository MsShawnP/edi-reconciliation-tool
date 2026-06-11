with source as (
    select * from {{ source('edi_raw', 'edi_997_acks') }}
),

staged as (
    select
        isa_control_number,
        partner_id,
        to_date(ack_date, 'YYMMDD')        as ack_date,
        acknowledged_functional_id,
        acknowledged_gs_control::integer    as acknowledged_gs_control,
        acceptance_code,
        -- A = Accepted, E = Accepted with errors, R = Rejected
        (acceptance_code = 'A')             as is_accepted,
        loaded_at
    from source
)

select * from staged
