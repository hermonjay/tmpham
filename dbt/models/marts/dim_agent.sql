-- dim_agent: one row per agent, enriched with name from customer master
with
    agent_portfolios as (
        select
            stg_user_portfolio_histories.agent_id,
            min(stg_user_portfolio_histories.portfolio_date) as first_seen_date,
            max(stg_user_portfolio_histories.portfolio_date) as last_seen_date,
            count(
                distinct stg_user_portfolio_histories.customer_id
            ) as distinct_customers_seen,
            count(
                distinct stg_user_portfolio_histories.product_id
            ) as distinct_products_seen
        from {{ ref('stg_user_portfolio_histories') }} as stg_user_portfolio_histories
        group by 1
    ),

    agent_names as (
        select
            dim_customer.agent_id,
            any_value(dim_customer.branch_name) as branch_name
        from {{ ref('dim_customer') }} as dim_customer
        group by 1
    )

select
    agent_portfolios.agent_id,
    coalesce(
        agent_names.branch_name,
        'Agent ' || cast(agent_portfolios.agent_id as varchar)
    ) as agent_name,
    agent_portfolios.first_seen_date,
    agent_portfolios.last_seen_date,
    agent_portfolios.distinct_customers_seen,
    agent_portfolios.distinct_products_seen,
    (
        agent_portfolios.last_seen_date = (
            select max(stg_user_portfolio_histories.portfolio_date)
            from
                {{ ref('stg_user_portfolio_histories') }}
                as stg_user_portfolio_histories
        )
    ) as is_currently_active
from agent_portfolios
left join
    agent_names
    on agent_names.agent_id = agent_portfolios.agent_id
