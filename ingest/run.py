"""Entry point for the ingestion pipeline.

Usage:
    python -m ingest.run                       # uses default IngestionConfig
    python -m ingest.run --config conf.toml    # overrides from TOML
    uv run python -m ingest.run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

from ingest.config import IngestionConfig
from ingest.loader import SnapshotLoader
from ingest.merger import DuckDBMerger
from ingest.utils import setup_logging


def run_ingestion(config: IngestionConfig) -> dict:
    """Run the full ingestion pipeline.

    Returns a metrics dict that callers (CLI, tests) can assert on.
    """
    logger = setup_logging(config.log_level)
    logger.info("Starting ingestion with config=%s", config)

    config.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(config.duckdb_path))

    try:
        loader = SnapshotLoader(config)
        merger = DuckDBMerger(conn, config)

        results: dict = {
            "snapshots": [],
            "rows_processed": 0,
            "business_key": None,
        }

        for snap in loader.iter_snapshots():
            logger.info(
                "Processing snapshot file=%s date=%s rows=%d",
                snap.path.name, snap.snapshot_date.date(), snap.row_count,
            )
            r = merger.append_snapshot(snap.df)
            r["path"] = str(snap.path)
            r["snapshot_date"] = snap.snapshot_date.date().isoformat()
            results["snapshots"].append(r)
            results["rows_processed"] += r["rows_input"]

        history_count = conn.execute(
            f"SELECT COUNT(*) FROM {merger.history_fqtn}"
        ).fetchone()[0]
        results["history_rows"] = int(history_count)

        # --- Extra CSV tables (truncate-insert) ---
        results["extra_tables"] = []
        for csv_path_str, table_name in config.extra_csv_tables.items():
            csv_path = Path(csv_path_str)
            if not csv_path.exists():
                logger.warning("Extra CSV not found, skipping: %s", csv_path)
                continue
            r = merger.truncate_insert_csv(csv_path, table_name)
            results["extra_tables"].append(r)
            results["rows_processed"] += r["rows"]

        logger.info(
            "Ingestion complete. history=%d",
            history_count,
        )
        return results
    finally:
        conn.close()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the snapshot ingestion pipeline.")
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a TOML config file with an [ingestion] section.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.config:
        config = IngestionConfig.from_toml(args.config)
    else:
        config = IngestionConfig()
    run_ingestion(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
