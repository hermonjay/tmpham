"""Prefect 3.x orchestration for the analytics pipeline.

Steps (strict order):
    1. ingest snapshots   → raw tables in DuckDB
    2. dbt debug           → connection / config health check
    3. dbt run             → materialise models
    4. dbt build           → seeds + models + snapshots + tests (full DAG)

Scheduled daily at 01:00 Asia/Bangkok (UTC+7).
"""
from orchestration.utils.config import OrchestrationConfig

__all__ = ["OrchestrationConfig"]
