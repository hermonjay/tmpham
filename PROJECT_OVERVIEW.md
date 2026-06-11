# tmpham — Project Overview

**Data Analytics Engineer case study.** End-to-end local prototype:
**ingestion → dbt transformation → Prefect orchestration → Metabase BI**,
all on a shared DuckDB file.

**Stack:** Python 3.12 · uv · DuckDB · pandas · pyarrow · dbt-core 1.11 ·
dbt-duckdb · Prefect 3.x · Metabase v0.59.x (Docker).

---

## Top-level layout

```
.
├── README.md                   # Project overview + quickstart
├── pyproject.toml              # uv-managed deps (pandas, pyarrow, duckdb; dev: dbt, prefect, pytest)
├── uv.lock                     # Lockfile
├── Dockerfile                  # analytics-app: uv + python3.12 + ingest entrypoint
├── docker-compose.yml          # analytics-app + metabase, shared ./duckdb bind mount
├── .env.example                # Default env vars
├── .gitignore
├── PROJECT_OVERVIEW.md         # This file
│
├── data/
│   ├── cis_customers.csv       # 500 customer master rows
│   ├── cis_products.csv        # 10 product master rows
│   └── snapshots/              # 5 cumulative CSV snapshots (2026-01-10 → 2026-04-01)
├── duckdb/
│   └── analytics.duckdb        # Shared DuckDB warehouse (gitignored)
├── docs/
│   └── problem_1_design.md     # Ingest layer design write-up
├── ingest/                     # Problem 1: Ingestion
├── dbt/                        # Problem 2: dbt transformation
├── orchestration/              # Problem 3: Prefect orchestration
├── metabase/                   # BI layer (Docker)
├── infra/                      # Placeholder (Terraform / CI)
├── logs/                       # Runtime logs (gitignored)
└── tests/                      # pytest suite
```

---

## Root files

| File | Purpose |
|---|---|
| `README.md` | Project intro, status table, quickstart, repo layout, design highlights, prod-mapping table. Main entry doc. |
| `pyproject.toml` | uv/hatch project. Runtime deps: `pandas>=2.2`, `pyarrow>=17.0`, `duckdb>=1.1`. Dev group: `dbt-core>=1.11`, `dbt-duckdb>=1.10`, `pytest>=8.0`, `pytest-cov>=5.0`. Python 3.12+, ruff line=100. |
| `uv.lock` | Lockfile (236 KB). |
| `Dockerfile` | `analytics-app` image. Multi-stage uv+python3.12-bookworm-slim. Layer-cached: deps first, source after. Default CMD runs `ingest.run` once then idles. |
| `docker-compose.yml` | Two services: `analytics-app` (writes DuckDB), `metabase` (reads DuckDB, blocked by analytics healthcheck). Bind-mount `./duckdb` shared; named volume `analytics-metabase` for H2 metadata. |
| `.env.example` | Default env: `DUCKDB_PATH`, `SNAPSHOT_DIR`, `LOG_LEVEL`, `MB_PORT=3000`, `METABASE_VERSION=v0.59.x`, `DUCKDB_DRIVER_VERSION=1.5.3.0`. |
| `.gitignore` | Ignores `.venv`, `.env`, `duckdb/*.duckdb*`, `dbt/target`, `dbt/logs`, `dbt/dbt_packages`, `dbt/.user.yml`, `logs/`. |

---

## `data/`

| File | Purpose |
|---|---|
| `cis_customers.csv` | 500 customer master rows (`customer_id, customer_name, unit_holder_id, sid, agent_id, agent_code, agent_name, ..., approved_kyc_at, customer_type`). |
| `cis_products.csv` | 10 product master rows (`id, hpfid, siar_code, sinvest_code, sid, ifua, ifca, name, logo, description`). |
| `snapshots/` | 5 cumulative CSV snapshots of `cis_user_portfolio_histories`, filenames encode date: `2026-01-10` (1.4 MB) → `2026-01-26` (5.6 MB) → `2026-02-20` (10 MB) → `2026-03-23` (18.1 MB) → `2026-04-01` (19.7 MB). |

---

## `docs/`

| File | Purpose |
|---|---|
| `problem_1_design.md` | Design write-up for ingest layer. Goal, assumptions, business-key detection algorithm, MERGE SQL, idempotency proof, schema-drift handling, alt approaches considered, prod mapping (Athena+Iceberg), failure modes table. |

---

## `ingest/` — Problem 1: Ingestion

**Goal:** load cumulative CSV snapshots into two raw DuckDB tables
(`*_snapshot` history, `*_latest` current state) via idempotent MERGE.

| File | Purpose |
|---|---|
| `__init__.py` | Re-exports `IngestionConfig`, `SnapshotLoader`, `DuckDBMerger`. |
| `config.py` | Frozen `@dataclass` holding all knobs: paths, target schema/table names, **declared `business_key`** (default `("id",)`), log level. `from_toml()` loader (stdlib `tomllib`). Rejects unknown keys. |
| `loader.py` | `SnapshotLoader`: `discover()` globs `*.csv` lexicographically; `load_one()` reads via pandas+pyarrow backend, strips whitespace on string cols, adds metadata cols `snapshot_date` + `ingestion_timestamp`, returns `LoadedSnapshot` dataclass. |
| `merger.py` | `DuckDBMerger`: the core. Reads declared business key from config, adds sha256 hash `_bk_hash`, creates target tables, handles additive schema drift (`ALTER TABLE ADD COLUMN`), aligns missing cols to NULL, runs two `MERGE INTO` statements (history on `(_bk_hash, snapshot_date)`, latest on `_bk_hash` with `s.snapshot_date >= t.snapshot_date` guard). |
| `run.py` | CLI entry (`python -m ingest.run`, optional `--config <toml>` for overrides). Wires loader+merger, returns metrics dict: `snapshots[]`, `rows_processed`, `history_rows`, `latest_rows`, `business_key`. |
| `utils.py` | `setup_logging` (idempotent), `extract_snapshot_date` (ISO `YYYY-MM-DD` + compact `YYYYMMDD`), `profile_columns`, `detect_business_key` (inspection-only utility; **not** wired into the pipeline), `hash_business_key_series` (sha256, ASCII `\x1f` separator, `__NULL__` sentinel). |

**Key invariants:** idempotent MERGE, additive-only schema drift, latest-snapshot-wins, filename-as-snapshot-date, **declared business key** (no auto-detection).

---

## `dbt/` — Problem 2: Transformation

```
dbt/
├── README.md                          # Stack, architecture, quickstart, test catalogue
├── __init__.py                        # Package marker
├── dbt_project.yml                    # Project config; per-layer materialisation + schema
├── profiles.yml                       # duckdb adapter, ../duckdb/analytics.duckdb, threads=4
├── packages.yml                       # dbt_utils 1.3.0
├── package-lock.yml
├── .user.yml                          # dbt Cloud user marker (gitignored normally)
├── analyses/
│   └── top_agents_latest_month.sql    # Ad-hoc: top-5 agents by AUM in latest month
├── docs/
│   ├── asset_classification_rules.md  # Classifier rules + catalogue + bucket rationale
│   └── kpi_validation.md              # 8 standalone SQL reconciliation queries
├── macros/
│   ├── classify_asset.sql             # 2-bucket classifier: equity_campuran | fixed_income | unknown
│   ├── generate_schema_name.sql       # Strips env prefix → clean staging/marts/reports schemas
│   └── incremental_filter.sql         # Watermark CTE + predicate (90-day lookback for late arrivals)
├── models/
│   ├── staging/
│   │   ├── _sources.yml               # raw.cis_user_portfolio_histories_latest, raw.cis_customers, raw.cis_products
│   │   ├── _staging__models.yml       # Column tests + relationships
│   │   ├── stg_customers.sql          # View: customer_type flag (individual/institution/unknown)
│   │   ├── stg_products.sql           # View: adds asset_class via classify_asset macro
│   │   └── stg_user_portfolio_histories.sql  # View: types + is_active_entry + portfolio_month bucket
│   ├── marts/
│   │   ├── _marts__models.yml         # dim_agent, dim_product, fct_agent_monthly_kpis tests
│   │   ├── dim_agent.sql              # Table: one row per agent + first/last seen + active flag
│   │   ├── dim_product.sql            # Table: product + asset_class + human label
│   │   └── fct_agent_monthly_kpis.sql # Incremental merge table: per-(agent,month) KPIs
│   └── reports/
│       ├── _reports__models.yml       # rpt_agent_monthly_performance + Metabase/Finance exposures
│       └── rpt_agent_monthly_performance.sql  # View: MoM deltas, in-month rank, portfolio_profile label
├── scripts/
│   ├── __init__.py
│   └── seed_raw_sources.py            # Creates raw.cis_products (10 rows) + raw.cis_customers (derived)
└── tests/
    ├── generic/
    │   ├── no_future_dates.sql        # Generic: column ≤ current_timestamp
    │   └── non_negative.sql           # Generic: column ≥ 0
    └── singular/
        ├── asset_allocation_reconciles.sql           # Buckets sum to total; no unknown
        ├── core_customers_threshold_satisfied.sql    # fct equals re-computation from stg
        ├── monthly_positions_within_bounds.sql       # No row explosion (≤ customers×10)
        ├── no_future_month_kpis.sql                  # month_start_date ≤ today
        ├── no_negative_aum.sql                       # KPI sign correctness
        ├── no_orphan_customer_portfolio.sql          # FK stg_portfolio→stg_customers
        └── no_unknown_asset_class.sql                # Classifier covers catalogue
```

### Key model details

- **`fct_agent_monthly_kpis`** — incremental merge, `unique_key=['agent_id','month_start_date']`, `on_schema_change='append_new_columns'`, `order_by='month_start_date, agent_id'` for ZoneMap pruning. 90-day lookback via `incremental_filter_cte`.
- **KPIs:** `total_aum`, `aum_equity_campuran`, `aum_fixed_income`, `aum_unknown_class`, `pct_*`, `core_customer_count` (distinct customers > IDR 100M threshold), `total_customer_count`, `distinct_products_held`, `month_end_positions`.
- **`rpt_agent_monthly_performance`** — adds `rank_aum_in_month`, `aum_mom_change_idr/pct`, `core_customers_mom_change`, `portfolio_profile` label (Fixed Income Heavy / Equity Heavy / Balanced / No AUM).
- **Asset classifier** — `fund_type` wins if curated; else keyword regex scan (`SIMILAR TO`). Money Market lumped with Fixed Income. Unknown is hard-fail.
- **Exposures:** Metabase dashboard + Finance CSV export.

---

## `orchestration/` — Problem 3: Prefect orchestration

```
orchestration/
├── README.md                  # Pipeline order, install, env vars, retry policy, structured logging
├── __init__.py                # Re-exports OrchestrationConfig
├── flows/
│   └── pipeline.py            # @flow analytics_pipeline + analytics_pipeline_scheduled
├── tasks/
│   ├── __init__.py
│   ├── ingest.py              # @task ingest_snapshots (2 retries/30s/15m)
│   ├── dbt.py                 # @task dbt_deps, dbt_seed_raw_sources, dbt_build (3 retries/60s/30m)
│   └── validate.py            # @task run_validation_tests (1 retry/30s/10m)
├── deployments/
│   ├── __init__.py
│   └── schedule.py            # serve_local / serve_scheduled / deploy_to_work_pool
└── utils/
    ├── __init__.py
    ├── config.py              # Frozen OrchestrationConfig (env-driven: DUCKDB_PATH, DBT_*, INGEST_*, LOG_LEVEL, ORCH_RUNNER)
    ├── logging.py             # JsonFormatter, install_json_handler, log_dict
    └── shell.py               # run_shell subprocess wrapper with timeout + ShellError
```

### Pipeline shape

1. **ingest snapshots** → raw.*
2. **dbt deps + raw seed** (parallel via `.submit()`)
3. **dbt build** (models + tests)
4. **validation gate** (dbt test on singular suite)

### Deployment patterns

- `serve_local()` — ad-hoc dev.
- `serve_scheduled()` — daily 02:00 UTC + hourly weekday.
- `deploy_to_work_pool()` — process work pool + monthly full-refresh.

### Flow policy

- `ConcurrentTaskRunner`. Strict inter-step ordering, intra-step parallelism.
- Flow `retries=0` (only failing step re-runs).
- Hard ceiling 60 min.

---

## `metabase/` — BI layer

| File | Purpose |
|---|---|
| `README.md` | Setup, wiring explanation, version matrix, connection form fields, re-sync workflow. |
| `Dockerfile` | Two-stage: upstream `metabase/metabase:v0.59.x` jar copied onto `eclipse-temurin:21-jre-noble` (Debian/glibc — avoids Alpine/musl segfault in DuckDB's `init_have_lse_atomics`). Downloads MotherDuck DuckDB driver `1.5.3.0` into `/plugins`, chmod 0644 for UID 2000. |
| `.dockerignore` | Excludes everything but `Dockerfile`. |

**Wiring:** bind-mount `./duckdb` into Metabase read-only. H2 metadata in `analytics-metabase` named volume. UI on `http://localhost:3000`.

---

## `infra/`

| File | Purpose |
|---|---|
| `README.md` | Placeholder. Reserved for Terraform (S3/Glue/Athena/IAM), Iceberg bootstrap, GitHub Actions CI/CD. Not implemented. |

---

## `tests/`

| File | Purpose |
|---|---|
| `__init__.py` | Package marker. |
| `conftest.py` | Pytest fixtures: `snapshot_dir` (3 CSVs incl. schema-drift `risk_score`), `config` (IngestionConfig pointing at tmp_path). |
| `test_ingest.py` | Unit + E2E tests for ingest layer: `extract_snapshot_date` (ISO/compact/embedded/missing), `detect_business_key` (single perfect + composite), row counts, latest-wins, idempotent rerun (×2 and ×3), no duplicates, partial-then-extend load, schema-drift adds column, out-of-order load (no regression). |
| `test_orchestration.py` | Smoke tests: `OrchestrationConfig` env overrides + defaults, `run_shell` (OK / non-zero / timeout), JSON formatter (one line + idempotent install), end-to-end flow with stubbed tasks. |

---

## Pipeline shape (overall)

```
CSV snapshots ──ingest.run──▶ raw.*  (history + latest, MERGE, _bk_hash)
                                    │
                                    ▼
                          dbt seed (customers, products)
                                    │
                                    ▼
                     staging.* (views) ─▶ marts.* (dim/fct, incremental merge)
                                    │
                                    ▼
                              reports.* (views) ─▶ Metabase (ro)
                                    │
                                    ▼
                         singular tests (validation gate)
```

Orchestrated by `orchestration.flows.pipeline.analytics_pipeline`:
ingest → dbt deps + seed (parallel) → dbt build → validate.

---

## Production mapping

| Local | Production |
|---|---|
| `SnapshotLoader` reading local CSVs | Dagster S3 sensor / asset |
| `DuckDBMerger.merge_snapshot` | Athena/Iceberg native `MERGE INTO` |
| `raw.<table>_snapshot` / `_latest` | Athena/Iceberg tables |
| `_bk_hash` | Same (Iceberg row-level MERGE perf) |
| `ALTER TABLE ADD COLUMN` | Iceberg native additive schema evolution |
| `python -m ingest.run` | Dagster asset, sensor on `s3://…` |
| Prefect `@flow` | Dagster job / sensor |
| Local `duckdb/analytics.duckdb` | Athena workgroup + Glue catalog |

Invariants preserved: idempotent MERGE on (bk, snapshot_date), additive-only drift, latest-snapshot-wins, filename-as-snapshot-date.
