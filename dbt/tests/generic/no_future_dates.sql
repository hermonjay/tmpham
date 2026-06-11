{#
  Generic test: a column must never contain a value in the future.

  Usage:
    columns:
      - name: created_at
        tests:
          - no_future_dates

  The test runs against the column it is attached to. Optionally
  pass `timezone_offset_hours` if your database is TZ-naive and you
  want a tolerance window.
#}
{% test no_future_dates(model, column_name, timezone_offset_hours=0) %}

    with
        violations as (
            select *
            from {{ model }}
            where
                cast({{ column_name }} as timestamp)
                > current_timestamp
                + ({{ timezone_offset_hours }} || ' hours')::interval
        )

    select *
    from violations

{% endtest %}
