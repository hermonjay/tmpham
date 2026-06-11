"""Read CSV snapshots from disk into pandas DataFrames.

Each snapshot is returned as a ``LoadedSnapshot`` holding:
  * the original path
  * the parsed snapshot_date (from filename)
  * a DataFrame already enriched with ``snapshot_date`` and
    ``ingestion_timestamp`` metadata columns.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

import pandas as pd

from ingest.config import IngestionConfig
from ingest.utils import extract_snapshot_date, setup_logging


@dataclass(frozen=True)
class LoadedSnapshot:
    """A single snapshot ready for the merger."""

    path: Path
    snapshot_date: datetime
    df: pd.DataFrame

    @property
    def row_count(self) -> int:
        return int(len(self.df))


class SnapshotLoader:
    """Discover and load CSV snapshots from a directory."""

    def __init__(self, config: IngestionConfig):
        self.config = config
        self.logger = setup_logging(config.log_level).getChild("loader")

    # --- discovery ----------------------------------------------------

    def discover(self) -> list[Path]:
        """Return all snapshot paths, sorted lexicographically (= chronologically
        when filenames start with an ISO date)."""
        snapshot_dir = self.config.snapshot_dir
        if not snapshot_dir.exists():
            raise FileNotFoundError(
                f"Snapshot directory does not exist: {snapshot_dir}"
            )
        paths = sorted(snapshot_dir.glob(self.config.snapshot_glob))
        self.logger.info(
            "Discovered %d snapshot file(s) under %s", len(paths), snapshot_dir
        )
        return paths

    # --- single-file load --------------------------------------------

    def load_one(self, path: Path) -> LoadedSnapshot:
        snapshot_date = extract_snapshot_date(path)
        self.logger.info(
            "Loading snapshot file=%s snapshot_date=%s",
            path.name, snapshot_date.date(),
        )

        # pyarrow backend keeps types stable for DuckDB round-trip.
        df = pd.read_csv(path, dtype_backend="pyarrow")
        df.columns = [str(c).strip() for c in df.columns]

        # Defensive whitespace strip on string-like columns.
        obj_cols = [
            c for c in df.columns
            if pd.api.types.is_string_dtype(df[c]) or df[c].dtype == object
        ]
        for c in obj_cols:
            df[c] = df[c].astype("string").str.strip()

        # Metadata columns.
        df["snapshot_date"] = pd.to_datetime(snapshot_date.date())
        # ingested_at: parsed from filename date.
        df["ingested_at"] = pd.to_datetime(snapshot_date)

        if df.columns.duplicated().any():
            dup = df.columns[df.columns.duplicated()].tolist()
            raise ValueError(f"Duplicate column names in {path.name}: {dup}")

        return LoadedSnapshot(path=path, snapshot_date=snapshot_date, df=df)

    # --- iterator -----------------------------------------------------

    def iter_snapshots(self) -> Iterator[LoadedSnapshot]:
        for p in self.discover():
            yield self.load_one(p)
