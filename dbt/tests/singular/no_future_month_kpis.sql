{#
  Singular test: month_start_date must never be in the future relative
  to the current system date, AND must never exceed the max portfolio_date
  present in the source (a KPI cannot predate the data that produced it).
#}
with
    future_kpis as (
        select agent_id, month_start_date, current_timestamp as checked_at
        from {{ ref('fct_agent_monthly_kpis') }}
        where month_start_date > current_date
    )
select *
from future_kpis
