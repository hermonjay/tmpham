-- stg_customers: clean customer master from raw.cis_customers
select
    customer_id,
    customer_name,
    unit_holder_id,
    sid,
    agent_id,
    branch_name,
    -- Source timestamps are UTC-8; shift to WIB (UTC+7, +15h)
    cast(approved_kyc_at as timestamp) + interval '15 hours' as approved_kyc_at,
    customer_type
from {{ source('raw', 'cis_customers') }}
