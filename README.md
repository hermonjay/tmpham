# Analytics case study

Data Analytics Engineer case study. End-to-end local prototype: ingestion →
dbt transformation → Metabase BI, all on a shared DuckDB file.

**Stack:** Python 3.12 · uv · DuckDB · pandas · pyarrow · dbt-core 1.11 ·
dbt-duckdb · Metabase v0.59.x (Docker).

## Status

| Layer | Status | What it does |
|---|---|---|
| `ingest/`         | **Implemented** | CSV snapshot discovery, truncate-insert into raw tables (snapshots + cis_customers + cis_products), additive schema drift. |
| `dbt/`            | **Implemented** | `stg → mart → rpt` models, incremental `fct_agent_monthly_kpis`, asset classifier, 8+ tests (5+ custom singular). |
| `metabase/`       | **Implemented** | Custom Debian Metabase image w/ DuckDB driver pre-loaded; bind-mounts the same DuckDB file. |
| `infra/`          | placeholder    | Reserved for Terraform / CI / Iceberg bootstrap. |

## Quick start

```bash
# 1. Install deps (ingest runtime + dbt dev extras)
uv sync

# 2. Ingest snapshots + reference CSVs -> raw.* tables
uv run python -m ingest.run

# 3. dbt: install packages, then build + test
cd dbt && uv run dbt deps && uv run dbt build --profiles-dir . && cd ..

# 4. BI layer (Docker) — Metabase on http://localhost:3000
docker compose up -d --build
```

See layer READMEs for connection details: [`metabase/README.md`](metabase/README.md),
[`dbt/README.md`](dbt/README.md).

## Repository layout

```
.
├── ingest/                 # Ingestion layer — custom DuckDB MERGE (Problem 1)
│   ├── config.py           - Frozen dataclass + TOML loader.
│   ├── loader.py           - CSV snapshot discovery + metadata tagging.
│   ├── merger.py           - DuckDB MERGE (history + latest).
│   ├── run.py              - CLI entry point.
│   └── utils.py            - Logging, date parsing, key detection, hashing.
├── dbt/                    # Transformation layer (Problem 2)
│   ├── models/
│   │   ├── staging/        - stg_* views over raw.*
│   │   ├── marts/          - dim_agent, dim_product, fct_agent_monthly_kpis (incremental)
│   │   └── reports/        - rpt_agent_monthly_performance
│   ├── tests/              - generic + singular (asset alloc, no_future_month_kpis, …)
│   ├── macros/             - classify_asset, incremental_filter
│   ├── analyses/           - top_agents_latest_month.sql
│   └── docs/               - asset_classification_rules.md, kpi_validation.md
├── metabase/               # BI layer
│   ├── Dockerfile          - Multi-stage: upstream metabase jar on temurin:21-jre-noble.
│   └── README.md           - Setup, connection form, version pinning notes.
├── infra/                  # Placeholder for Terraform / CI
├── data/
│   └── snapshots/          # 5 cumulative CSV snapshots (2026-01-10 … 2026-04-01)
├── tests/                  - (removed)
├── docs/
│   ├── problem_1_design.md          # Ingest design write-up
│   ├── asset_classification_rules.md
│   └── kpi_validation.md
├── duckdb/                 # DuckDB database files (gitignored)
├── docker-compose.yml      # analytics-app + metabase, shared ./duckdb bind mount
├── Dockerfile              # uv + python3.12 + ingest entrypoint
├── pyproject.toml
└── README.md
```

## Pipeline shape

```
CSV snapshots + reference CSVs ──ingest.run──▶ raw.*  (history + latest, truncate-insert)
                                                    │
                                                    ▼
                                 staging.* (views) ─▶ marts.* (dim/fct, incremental merge)
                                                    │
                                                    ▼
                                              reports.* (views) ─▶ Metabase
                                                    │
                                                    ▼
                                         singular tests (validation gate)
```

Pipeline steps:

1. **ingest** — `uv run python -m ingest.run`
2. **dbt build** — `cd dbt && uv run dbt deps && uv run dbt build --profiles-dir .`
3. **validation** — dbt singular tests run as part of `dbt build`
