{#
  Generic test: a column must never be negative.

  Nulls are allowed (some metrics may be null on legitimate empty months).

  Usage:
    columns:
      - name: total_aum
        tests:
          - non_negative
#}
{% test non_negative(model, column_name) %}

    with violations as (select * from {{ model }} where {{ column_name }} < 0)

    select *
    from violations

{% endtest %}
