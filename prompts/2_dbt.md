```
You are a Senior Analytics Engineer.

Continue from the existing repository.

Implement the dbt layer only.

Technology
dbt-core
dbt-duckdb
Architecture
stg (views)
mart (tables)
report (views)

Source Tables
raw.cis_user_portfolio_histories_latest
raw.cis_customers
raw.cis_products

Required Models
Staging:

stg_customers
stg_products
stg_user_portfolio_histories
Dimensions:

dim_agent
dim_product
Facts:

fct_agent_monthly_kpis
Reports:

rpt_agent_monthly_performance
KPI Requirements
Per agent and month:

Total AUM

AUM split

Equity/Campuran
Fixed Income
Core Customer Count
Definition:

Month-end AUM > 100,000,000 IDR

Asset Classification
Create deterministic rules based on Indonesian product names.

Document every rule.

Incremental
At least one model must be incremental.

Use:

incremental_strategy='merge'

Ensure:

idempotent reruns
late arriving records supported
Performance
Apply:

partitioning strategy
clustering strategy
incremental filtering
where supported by DuckDB.

Tests
Create at least 8 tests.

At least 5 must be custom tests.

Examples:

AUM cannot be negative
core customers must satisfy threshold
monthly grain uniqueness
asset allocation sums reconcile to total AUM
no future dates
Validation
Create SQL reconciliation queries proving KPI correctness.

Store in:

docs/kpi_validation.md

Documentation
Generate:

schema.yml
exposures
dbt docs descriptions
Output complete dbt project files.
```
