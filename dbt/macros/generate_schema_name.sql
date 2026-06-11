{#
  Schema-name override.

  Default dbt behaviour concatenates target.schema + custom_schema_name
  (e.g. `dbt_dev` + `mart` -> `dbt_dev_mart`). We want each layer to land
  in its own clean schema (`staging`, `marts`, `reports`) with no
  environment prefix — this project runs as a single prod target.

  Models that don't set +schema fall back to target.schema (`main`,
  matching DuckDB's default).
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%} {{ target.schema }}
    {%- else -%} {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
