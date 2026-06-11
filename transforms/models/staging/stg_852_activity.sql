with source as (
    select * from {{ source('edi_raw', 'edi_852_activity_lines') }}
),

staged as (
    select
        isa_control_number,
        partner_id,
        report_id,
        to_date(report_date, 'YYYYMMDD')   as report_date,
        line_number,
        sku,
        quantity::numeric                   as quantity,
        unit_of_measure,
        to_date(nullif(period_start, ''), 'YYYYMMDD') as period_start,
        to_date(nullif(period_end,   ''), 'YYYYMMDD') as period_end,
        loaded_at
    from source
)

select * from staged
