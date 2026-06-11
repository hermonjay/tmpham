"""Ingestion task — wraps ``ingest.run.run_ingestion``."""
from __future__ import annotations

from prefect import task

from ingest.config import IngestionConfig
from ingest.run import run_ingestion
from orchestration.utils.config import OrchestrationConfig
from orchestration.utils.logging import get_logger, log_dict


@task(
    name="ingest-snapshots",
    description="Load CSV snapshots into raw tables via DuckDB MERGE.",
    retries=2,
    retry_delay_seconds=30,
    timeout_seconds=900,
)
def ingest_snapshots(cfg: OrchestrationConfig) -> dict:
    logger = get_logger()
    ingest_cfg = IngestionConfig(
        snapshot_dir=cfg.snapshot_dir,
        duckdb_path=cfg.duckdb_path,
        log_level=cfg.log_level,
    )

    log_dict(logger, "info", "ingest.start",
             snapshot_dir=str(cfg.snapshot_dir),
             duckdb_path=str(cfg.duckdb_path))

    result = run_ingestion(ingest_cfg)

    log_dict(logger, "info", "ingest.done",
             rows_processed=result.get("rows_processed", 0),
             history_rows=result.get("history_rows"))

    if result.get("history_rows", 0) == 0:
        raise RuntimeError("ingest produced 0 history rows — aborting before dbt")

    return result
