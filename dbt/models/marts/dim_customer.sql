-- dim_customer: one row per customer from cis_customers master
with
    customers as (
        select
            stg_customers.customer_id,
            stg_customers.customer_name,
            stg_customers.unit_holder_id,
            stg_customers.sid,
            stg_customers.agent_id,
            stg_customers.branch_name,
            stg_customers.approved_kyc_at,
            stg_customers.customer_type
        from {{ ref('stg_customers') }} as stg_customers
    )

select
    customers.customer_id,
    customers.customer_name,
    customers.unit_holder_id,
    customers.sid,
    customers.agent_id,
    customers.branch_name,
    customers.approved_kyc_at,
    customers.customer_type,
    case
        when customers.approved_kyc_at is not null
        then current_date - cast(customers.approved_kyc_at as date)
        else null
    end as kyc_tenure_days
from customers
