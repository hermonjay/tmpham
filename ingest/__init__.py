"""Ingestion layer for cis_user_portfolio_histories snapshots.

Public API:
    IngestionConfig  - frozen config dataclass.
    SnapshotLoader   - reads CSV snapshots from disk.
    DuckDBMerger     - idempotent MERGE into DuckDB.
    (ingest.run.run_ingestion - entry point; lazy to avoid circular import)."""

from ingest.config import IngestionConfig
from ingest.loader import SnapshotLoader
from ingest.merger import DuckDBMerger

__all__ = [
    "IngestionConfig",
    "SnapshotLoader",
    "DuckDBMerger",
]
