{% macro incremental_filter_cte(partition_col, cte_name='_incr_watermark', lookback_days=90) %}
    {#
  Emit a CTE that resolves the incremental watermark
  (max partition seen in the target, minus a lookback window).

  Pair with `incremental_filter_predicate`. DuckDB's binder rejects
  nested aggregates in WHERE clauses, so we materialise the watermark
  into a 1-row CTE first and then JOIN to it.

  Returns the CTE body without the leading `with` keyword so it can
  be slotted into an existing CTE chain.

  Lookback window:
    Default 90 days — wide enough to catch late arrivals across the
    3-month sample history. Tune via `lookback_days` arg in
    production. Anything older than the window requires a full refresh.
#}
    {% if is_incremental() %}
        {{ cte_name }} as (
            select
                coalesce(
                    (select max({{ partition_col }}) from {{ this }}), date '1900-01-01'
                )
                - interval '{{ lookback_days }}' day as watermark
        )
    {% endif %}
{% endmacro %}


{% macro incremental_filter_predicate(partition_col, cte_name='_incr_watermark') %}
    {#
  Predicate that JOINs to the watermark CTE emitted by
  `incremental_filter_cte`. Returns only the join expression — caller
  is responsible for placing it in the FROM/JOIN clause of the model.

  Usage pattern:

      with source as (
          select ... from {{ ref('stg') }}
      )
      {% if is_incremental() %}
      , {{ incremental_filter_cte('portfolio_month') }}
      {% endif %}
      , filtered as (
          select s.*
          from source s
          {% if is_incremental() %}
          join {{ incremental_filter_predicate('portfolio_month') }}
          {% endif %}
      )
      select * from filtered;

  On a full-refresh run, no CTE is emitted and no JOIN is applied —
  the macro returns null/empty, leaving the query planar.
#}
    {% if is_incremental() %}
        {{ cte_name }} w on s.{{ partition_col }} > w.watermark
    {% endif %}
{% endmacro %}
