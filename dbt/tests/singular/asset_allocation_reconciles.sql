{#
  Singular test: the asset allocation split MUST reconcile to total AUM
  at the (agent, month) grain.

  Allowed tolerance: 1 IDR (rounding on floating aggregates).
  A row in the output means an agent's month has unclassified AUM
  (asset_class = 'unknown') OR a bug in the case-when branching.
#}
with
    reconciled as (
        select
            agent_id,
            month_start_date,
            total_aum,
            aum_equity_campuran,
            aum_fixed_income,
            aum_unknown_class,
            (
                coalesce(aum_equity_campuran, 0)
                + coalesce(aum_fixed_income, 0)
                + coalesce(aum_unknown_class, 0)
            ) as bucket_sum
        from {{ ref('fct_agent_monthly_kpis') }}
    ),
    violations as (
        select *
        from reconciled
        where
            abs(bucket_sum - total_aum) > 1.0  -- 1 IDR rounding tol.
            or aum_unknown_class > 0  -- any unclassified AUM
    )
select *
from violations
