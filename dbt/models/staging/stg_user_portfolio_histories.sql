select
    id as portfolio_id,
    agent_id,
    selling_agent_id,
    product_id,
    unit_holder_id as customer_id,
    -- Source dates are UTC-8; shift to WIB (UTC+7, +15h)
    cast(cast(date as timestamp) + interval '15 hours' as date) as portfolio_date,
    date_trunc('month', cast(cast(date as timestamp) + interval '15 hours' as date)) as portfolio_month,
    cast(cast(snapshot_date as timestamp) + interval '15 hours' as date) as snapshot_date,
    cast(created_at as timestamp) + interval '15 hours' as created_at,
    cast(updated_at as timestamp) + interval '15 hours' as updated_at,
    current_nav,
    run_nav_value,
    beginning_unit,
    subscription_unit,
    redeem_unit,
    dividend_unit,
    ending_unit,
    capital,
    beginning_balance,
    ending_balance,
    profit_or_loss,
    profit_or_loss_in_percent as profit_or_loss_pct,
    is_deleted,
    (is_deleted = false) as is_active_entry
from {{ source('raw', 'cis_user_portfolio_histories') }}
qualify row_number() over (partition by id order by ingested_at desc) = 1
