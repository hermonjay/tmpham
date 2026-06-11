-- fct_agent_monthly_kpis: per (agent, month) KPI row
with
    source_portfolios as (
        select
            stg_user_portfolio_histories.portfolio_id,
            stg_user_portfolio_histories.agent_id,
            stg_user_portfolio_histories.customer_id,
            stg_user_portfolio_histories.product_id,
            stg_user_portfolio_histories.portfolio_date,
            stg_user_portfolio_histories.portfolio_month,
            stg_user_portfolio_histories.ending_balance,
            stg_user_portfolio_histories.is_deleted,
            stg_user_portfolio_histories.is_active_entry,
            dim_product.asset_class_bucket as asset_class
        from {{ ref('stg_user_portfolio_histories') }} as stg_user_portfolio_histories
        left join
            {{ ref('dim_product') }} as dim_product
            on dim_product.product_id = stg_user_portfolio_histories.product_id
    ),

    {% if is_incremental() %}
        {{ incremental_filter_cte('month_start_date') }},
    {% endif %}

    portfolios as (
        select
            source_portfolios.portfolio_id,
            source_portfolios.agent_id,
            source_portfolios.customer_id,
            source_portfolios.product_id,
            source_portfolios.portfolio_date,
            source_portfolios.portfolio_month,
            source_portfolios.ending_balance,
            source_portfolios.is_deleted,
            source_portfolios.is_active_entry,
            source_portfolios.asset_class
        from source_portfolios
        {% if is_incremental() %}
            join
                _incr_watermark as _incr_watermark
                on source_portfolios.portfolio_month > _incr_watermark.watermark
        {% endif %}
    ),

    month_end_entries as (
        select
            agent_id,
            customer_id,
            product_id,
            portfolio_month as month_start_date,
            ending_balance,
            asset_class,
            is_deleted,
            is_active_entry,
            row_number() over (
                partition by agent_id, customer_id, product_id, portfolio_month
                order by portfolio_date desc, portfolio_id desc
            ) as rn
        from portfolios
        where is_active_entry and ending_balance is not null
        qualify rn = 1
    ),

    agent_month as (
        select
            agent_id,
            month_start_date,
            sum(ending_balance) as total_aum,
            sum(
                case when asset_class = 'equity_campuran' then ending_balance else 0 end
            ) as aum_equity_campuran,
            sum(
                case when asset_class = 'fixed_income' then ending_balance else 0 end
            ) as aum_fixed_income,
            sum(
                case
                    when
                        asset_class is null
                        or asset_class not in ('equity_campuran', 'fixed_income')
                    then ending_balance
                    else 0
                end
            ) as aum_unknown_class,
            count(distinct product_id) as distinct_products_held,
            count(*) as month_end_positions
        from month_end_entries
        group by 1, 2
    ),

    customer_month_aum as (
        select
            agent_id,
            month_start_date,
            customer_id,
            sum(ending_balance) as customer_month_end_aum
        from month_end_entries
        group by 1, 2, 3
    ),

    core_customers as (
        select
            agent_id,
            month_start_date,
            count(distinct customer_id) as core_customer_count
        from customer_month_aum
        where customer_month_end_aum > {{ var('core_customer_threshold_idr') }}
        group by 1, 2
    ),

    total_customers as (
        select
            agent_id,
            month_start_date,
            count(distinct customer_id) as total_customer_count
        from customer_month_aum
        group by 1, 2
    )

select
    agent_month.agent_id,
    agent_month.month_start_date,
    agent_month.total_aum,
    agent_month.aum_equity_campuran,
    agent_month.aum_fixed_income,
    agent_month.aum_unknown_class,
    case
        when agent_month.total_aum > 0
        then agent_month.aum_equity_campuran / agent_month.total_aum
        else null
    end as pct_equity_campuran,
    case
        when agent_month.total_aum > 0
        then agent_month.aum_fixed_income / agent_month.total_aum
        else null
    end as pct_fixed_income,
    coalesce(core_customers.core_customer_count, 0) as core_customer_count,
    coalesce(total_customers.total_customer_count, 0) as total_customer_count,
    agent_month.distinct_products_held,
    agent_month.month_end_positions,
    {{ var('core_customer_threshold_idr') }} as core_customer_threshold_idr,
    current_timestamp as dbt_updated_at
from agent_month
left join
    core_customers
    on core_customers.agent_id = agent_month.agent_id
    and core_customers.month_start_date = agent_month.month_start_date
left join
    total_customers
    on total_customers.agent_id = agent_month.agent_id
    and total_customers.month_start_date = agent_month.month_start_date
