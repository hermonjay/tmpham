-- rpt_agent_monthly_performance: per (agent, month) with ranking and MoM delta
with
    base as (
        select
            fct_agent_monthly_kpis.agent_id,
            dim_agent.agent_name,
            fct_agent_monthly_kpis.month_start_date,
            fct_agent_monthly_kpis.total_aum,
            fct_agent_monthly_kpis.aum_equity_campuran,
            fct_agent_monthly_kpis.aum_fixed_income,
            fct_agent_monthly_kpis.pct_equity_campuran,
            fct_agent_monthly_kpis.pct_fixed_income,
            fct_agent_monthly_kpis.core_customer_count,
            fct_agent_monthly_kpis.total_customer_count,
            fct_agent_monthly_kpis.distinct_products_held,
            fct_agent_monthly_kpis.month_end_positions,
            fct_agent_monthly_kpis.core_customer_threshold_idr
        from {{ ref('fct_agent_monthly_kpis') }} as fct_agent_monthly_kpis
        left join
            {{ ref('dim_agent') }} as dim_agent
            on dim_agent.agent_id = fct_agent_monthly_kpis.agent_id
    ),

    lagged as (
        select
            base.agent_id,
            base.agent_name,
            base.month_start_date,
            base.total_aum,
            base.aum_equity_campuran,
            base.aum_fixed_income,
            base.pct_equity_campuran,
            base.pct_fixed_income,
            base.core_customer_count,
            base.total_customer_count,
            base.distinct_products_held,
            base.month_end_positions,
            base.core_customer_threshold_idr,
            lag(base.total_aum) over (
                partition by base.agent_id order by base.month_start_date
            ) as prev_month_aum,
            lag(base.core_customer_count) over (
                partition by base.agent_id order by base.month_start_date
            ) as prev_month_core_customers
        from base
    ),

    ranked as (
        select
            lagged.agent_id,
            lagged.agent_name,
            lagged.month_start_date,
            lagged.total_aum,
            lagged.aum_equity_campuran,
            lagged.aum_fixed_income,
            lagged.pct_equity_campuran,
            lagged.pct_fixed_income,
            lagged.core_customer_count,
            lagged.total_customer_count,
            lagged.distinct_products_held,
            lagged.month_end_positions,
            lagged.core_customer_threshold_idr,
            lagged.prev_month_aum,
            lagged.prev_month_core_customers,
            rank() over (
                partition by lagged.month_start_date order by lagged.total_aum desc
            ) as rank_aum_in_month
        from lagged
    )

select
    ranked.agent_id,
    ranked.agent_name,
    ranked.month_start_date,
    ranked.total_aum,
    ranked.aum_equity_campuran,
    ranked.aum_fixed_income,
    round(ranked.pct_equity_campuran, 4) as pct_equity_campuran,
    round(ranked.pct_fixed_income, 4) as pct_fixed_income,
    ranked.core_customer_count,
    ranked.total_customer_count,
    ranked.distinct_products_held,
    ranked.month_end_positions,
    ranked.rank_aum_in_month,
    case
        when ranked.prev_month_aum is not null
        then ranked.total_aum - ranked.prev_month_aum
    end as aum_mom_change_idr,
    case
        when ranked.prev_month_aum is not null and ranked.prev_month_aum <> 0
        then (ranked.total_aum - ranked.prev_month_aum) / ranked.prev_month_aum
    end as aum_mom_change_pct,
    case
        when ranked.prev_month_core_customers is not null
        then ranked.core_customer_count - ranked.prev_month_core_customers
    end as core_customers_mom_change,
    case
        when ranked.total_aum is null or ranked.total_aum = 0
        then 'No AUM'
        when ranked.pct_fixed_income >= 0.6
        then 'Fixed Income Heavy'
        when ranked.pct_equity_campuran >= 0.6
        then 'Equity Heavy'
        else 'Balanced'
    end as portfolio_profile
from ranked
