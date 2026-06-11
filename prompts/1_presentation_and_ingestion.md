```
You are a Staff Analytics Engineer.

Build a production-quality repository for a Data Analytics Engineer case study.

Objective
Implement ONLY the ingestion layer first.

Everything else (dbt, orchestration, infrastructure, metabase) should exist as placeholders and folder structure only.

Do not implement them yet.

Technology Choices
Use:

Python 3.12
uv package manager
DuckDB
pandas
pyarrow
Do NOT use dlt for now.

Reason:

I want a simple local prototype first and will explain during presentation how this maps to dlt in production.

Repository Structure
Create:

.
├── ingest/
├── dbt/
├── orchestration/
├── infra/
├── metabase/
├── data/
├── tests/
├── docs/
├── duckdb/
├── pyproject.toml
├── uv.lock
└── README.md

Data
Input:

data/snapshots/*.csv

Files are cumulative snapshots of the same source table.

The snapshots are NOT append-only.

Rows may:

be inserted
be updated
appear multiple times across snapshots
The final target table must contain only the latest version of every business row.

Requirements
Create a robust ingestion process.

Read all snapshots.
Extract snapshot date from filename.
Add metadata columns:
snapshot_date
ingestion_timestamp
Determine the natural/business key automatically by profiling the dataset.
Implement an idempotent MERGE strategy.
Re-running ingestion must not create duplicates.
Running ingestion on a partially loaded database must be safe.
Handle schema drift defensively.
Use DuckDB MERGE.
Tables
Create:

raw.cis_user_portfolio_histories_snapshot
raw.cis_user_portfolio_histories_latest

Design Expectations
Use:

OOP
typing
logging
configuration file
reusable ingestion class
Create:

ingest/
├── config.py
├── loader.py
├── merger.py
├── run.py
└── utils.py

Documentation
Create:

docs/problem_1_design.md

Include:

assumptions
merge strategy
idempotency strategy
alternative approaches considered
mapping to production Athena + Iceberg + dlt architecture
Testing
Create basic pytest tests validating:

no duplicate keys
idempotent reruns
latest snapshot wins
Output
Provide complete repository files.

Do not skip code.

Generate code file-by-file.
```
