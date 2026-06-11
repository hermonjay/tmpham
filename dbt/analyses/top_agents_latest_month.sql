-- Top-5 agents by AUM in the latest month.
-- Re-runnable. Replace :latest_month with a literal for ad-hoc queries.
with
    latest_month as (
        select max(month_start_date) as m from {{ ref('fct_agent_monthly_kpis') }}
    )
select
    r.rank_aum_in_month as rank,
    f.agent_id,
    a.agent_name,
    f.month_start_date,
    f.total_aum,
    f.pct_equity_campuran,
    f.pct_fixed_income,
    f.core_customer_count,
    f.total_customer_count
from {{ ref('fct_agent_monthly_kpis') }} f
join latest_month lm on lm.m = f.month_start_date
left join {{ ref('dim_agent') }} a on a.agent_id = f.agent_id
left join
    {{ ref('rpt_agent_monthly_performance') }} r
    on r.agent_id = f.agent_id
    and r.month_start_date = f.month_start_date
where r.rank_aum_in_month <= 5
order by f.month_start_date desc, r.rank_aum_in_month asc
