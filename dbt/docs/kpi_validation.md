# KPI validation queries

Each block is a standalone SQL query you can paste into DuckDB CLI,
Metabase, or `duckdb -c "..."`. Together they prove the KPIs in
`marts.fct_agent_monthly_kpis` and `reports.rpt_agent_monthly_performance`
reconcile to the raw source.

Conventions:
* `marts`, `reports`, `staging` = the dbt schemas (set in
  `dbt_project.yml` and materialised via `macros/generate_schema_name.sql`).
* All money columns are in IDR.

---

## 1. Total AUM per (agent, month)

**Claim:** `fct_agent_monthly_kpis.total_aum` = sum of month-end
ending_balance across all (customer, product) positions the agent owns
in that month.

```sql
-- Reference recomputation.
with month_end as (
    select
        ph.agent_id,
        date_trunc('month', cast(ph.date as date)) as month_start_date,
        ph.customer_id,
        ph.product_id,
        ph.ending_balance,
        row_number() over (
            partition by ph.agent_id, ph.customer_id, ph.product_id,
                         date_trunc('month', cast(ph.date as date))
            order by cast(ph.date as date) desc, ph.id desc
        ) as rn
    from raw.cis_user_portfolio_histories_latest ph
    where coalesce(ph.is_deleted, false) = false
      and ph.ending_balance is not null
)
select
    agent_id,
    month_start_date,
    sum(ending_balance) as reference_total_aum
from month_end
where rn = 1
group by 1, 2

union all

-- Persisted KPI.
select agent_id, month_start_date, total_aum as reference_total_aum
from marts.fct_agent_monthly_kpis
order by agent_id, month_start_date;
```

Run the two halves side-by-side; they must match exactly. A
mismatch means the fact grain changed without the model being updated.

---

## 2. AUM split — Equity/Campuran vs Fixed Income

**Claim:** `aum_equity_campuran + aum_fixed_income + aum_unknown_class
= total_aum` at the (agent, month) grain.

```sql
select
    agent_id,
    month_start_date,
    total_aum,
    aum_equity_campuran,
    aum_fixed_income,
    aum_unknown_class,
    (aum_equity_campuran + aum_fixed_income + aum_unknown_class) as bucket_sum,
    total_aum - (aum_equity_campuran + aum_fixed_income + aum_unknown_class) as diff
from marts.fct_agent_monthly_kpis
where abs(total_aum - (aum_equity_campuran + aum_fixed_income + aum_unknown_class)) > 1.0
   or aum_unknown_class > 0
order by diff desc;
```

**Expected:** zero rows. Any positive `aum_unknown_class` means a new
product was added to the catalogue without updating the classifier.

---

## 3. Core customer count

**Claim:** `core_customer_count` = number of distinct customers with
**month-end** AUM > IDR 100,000,000.

```sql
with month_end as (
    select
        ph.agent_id,
        date_trunc('month', cast(ph.date as date)) as month_start_date,
        ph.customer_id,
        ph.product_id,
        ph.ending_balance,
        row_number() over (
            partition by ph.agent_id, ph.customer_id, ph.product_id,
                         date_trunc('month', cast(ph.date as date))
            order by cast(ph.date as date) desc, ph.id desc
        ) as rn
    from raw.cis_user_portfolio_histories_latest ph
    where coalesce(ph.is_deleted, false) = false
      and ph.ending_balance is not null
),
customer_aum as (
    select agent_id, month_start_date, customer_id,
           sum(ending_balance) as customer_aum
    from month_end
    where rn = 1
    group by 1, 2, 3
)
select
    agent_id,
    month_start_date,
    count(distinct customer_id) as reference_core_count,
    100000000 as threshold_idr
from customer_aum
where customer_aum > 100000000
group by 1, 2
order by agent_id, month_start_date;
```

Cross-check by joining to the persisted fact:

```sql
select
    coalesce(r.agent_id, f.agent_id) as agent_id,
    coalesce(r.month_start_date, f.month_start_date) as month_start_date,
    r.reference_core_count,
    f.core_customer_count,
    (r.reference_core_count - f.core_customer_count) as diff
from reference_core r
full outer join marts.fct_agent_monthly_kpis f
    on f.agent_id = r.agent_id
   and f.month_start_date = r.month_start_date
where coalesce(r.reference_core_count, -1) <> coalesce(f.core_customer_count, -1);
```

**Expected:** zero rows.

---

## 4. Month-grain uniqueness

**Claim:** `(agent_id, month_start_date)` is unique in
`fct_agent_monthly_kpis` (required for the incremental MERGE to be
idempotent).

```sql
select agent_id, month_start_date, count(*) as n
from marts.fct_agent_monthly_kpis
group by 1, 2
having count(*) > 1;
```

**Expected:** zero rows.

This is also enforced by the `dbt_utils.unique_combination_of_columns`
generic test in `_marts__models.yml`.

---

## 5. No future dates

**Claim:** every `month_start_date` is `<= current_date`.

```sql
select agent_id, month_start_date, current_date as today
from marts.fct_agent_monthly_kpis
where month_start_date > current_date;
```

**Expected:** zero rows.

---

## 6. Idempotent reruns

**Claim:** running `dbt run -s fct_agent_monthly_kpis` twice in a row
produces identical row counts and identical (agent, month) hashes.

```sql
-- Snapshot before rerun.
create or replace temp table _before as
select agent_id, month_start_date, total_aum, core_customer_count,
       dbt_updated_at
from marts.fct_agent_monthly_kpis;

-- After rerun.
select
    count(*)                                                        as rows_after,
    count(*) filter (where b.dbt_updated_at <> a.dbt_updated_at)    as rows_with_changed_ts,
    count(*) filter (where coalesce(a.total_aum, -1) <> coalesce(b.total_aum, -1)) as aum_drift_rows
from _before b
join marts.fct_agent_monthly_kpis a
  on a.agent_id = b.agent_id
 and a.month_start_date = b.month_start_date;
```

**Expected:** `rows_with_changed_ts` may be > 0 (dbt re-stamps
`dbt_updated_at` on MERGE), but `aum_drift_rows` MUST be 0.

---

## 7. Late-arrival re-merge

**Setup:** simulate a late-arriving record by inserting one new
backdated portfolio row into the source:

```sql
insert into raw.cis_user_portfolio_histories_latest
(id, agent_id, selling_agent_id, product_id, unit_holder_id,
 date, full_name, ending_balance, beginning_balance,
 snapshot_date, ingestion_timestamp, _bk_hash,
 is_deleted, created_at, updated_at)
values (
  999999999, 1, 1, 1, 100001,
  '2026-01-31', 'Customer 0001', 250000000, 0,
  '2026-04-01', current_timestamp, 'late_arrival_test',
  false, current_timestamp, current_timestamp
);
```

Then:

```bash
dbt run -s fct_agent_monthly_kpis
```

**Assert:**

```sql
select *
from marts.fct_agent_monthly_kpis
where agent_id = 1 and month_start_date = date '2026-01-01';
```

The `total_aum` for agent 1 / Jan 2026 should have grown by
~250,000,000 IDR. And `core_customer_count` should be at least one
higher (customer 100001 now qualifies as core for that month).

---

## 8. Performance sanity — incremental pruning

```sql
-- DuckDB explains should show partition/ZoneMap pruning.
explain
select *
from marts.fct_agent_monthly_kpis
where month_start_date >= date '2026-03-01';
```

The `order_by='month_start_date, agent_id'` config on the fact table
lays rows on disk ordered by month. ZoneMaps on DuckDB's part-files
prune out months outside the filter.
