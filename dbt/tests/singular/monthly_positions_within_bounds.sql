{#
  Singular test: month_end_positions <= total_customer_count * (plausible_products).
  Concretely: a single agent/month cannot have more positions than
  distinct (customer, product) pairs that exist. We approximate by
  asserting month_end_positions <= (total_customer_count * 10)
  since the catalogue has 10 products. Any agent/month blowing this
  bound indicates a row explosion bug in the fact build.
#}
with
    stats as (
        select agent_id, month_start_date, month_end_positions, total_customer_count
        from {{ ref('fct_agent_monthly_kpis') }}
    ),
    violations as (
        select *
        from stats
        -- 10 is the size of the current product catalogue (raw.cis_products).
        -- If catalogue grows, bump this constant or derive dynamically.
        where month_end_positions > (total_customer_count * 10)
    )
select *
from violations
