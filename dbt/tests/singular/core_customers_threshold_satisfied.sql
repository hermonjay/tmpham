{#
  Singular test: core_customer_count must be derivable from the source.

  We recompute the metric from stg_user_portfolio_histories at the
  same grain and assert it equals the persisted value in the fact.
  Any mismatch means the fact-build logic drifted from the canonical
  query (e.g. a join changed grain, threshold var got mis-applied).

  Allowed tolerance: 0 — this is an exact reconciliation.
#}
with
    expected as (
        -- Canonical re-computation, mirroring the fct SQL.
        with
            month_end as (
                select
                    agent_id,
                    customer_id,
                    portfolio_month as month_start_date,
                    sum(ending_balance) as customer_aum
                from
                    (
                        select
                            ph.agent_id,
                            ph.customer_id,
                            ph.portfolio_month,
                            ph.ending_balance,
                            row_number() over (
                                partition by
                                    ph.agent_id,
                                    ph.customer_id,
                                    ph.product_id,
                                    ph.portfolio_month
                                order by ph.portfolio_date desc, ph.portfolio_id desc
                            ) as rn
                        from {{ ref('stg_user_portfolio_histories') }} ph
                        where ph.is_active_entry and ph.ending_balance is not null
                    )
                where rn = 1
                group by 1, 2, 3
            )
        select
            agent_id,
            month_start_date,
            count(distinct customer_id) as expected_core_count
        from month_end
        where customer_aum > {{ var('core_customer_threshold_idr') }}
        group by 1, 2
    ),
    actual as (
        select agent_id, month_start_date, core_customer_count
        from {{ ref('fct_agent_monthly_kpis') }}
    )
select
    coalesce(e.agent_id, a.agent_id) as agent_id,
    coalesce(e.month_start_date, a.month_start_date) as month_start_date,
    e.expected_core_count,
    a.core_customer_count
from expected e
full outer join
    actual a on a.agent_id = e.agent_id and a.month_start_date = e.month_start_date
where coalesce(e.expected_core_count, -1) <> coalesce(a.core_customer_count, -1)
