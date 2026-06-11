"""Configuration for the ingestion layer.

Holds:
  * paths (snapshots, duckdb file)
  * target schema / table names
  * business-key detection knobs
  * logging level

Frozen dataclass + TOML loader (Python 3.11+ stdlib tomllib).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields  # noqa: F811
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IngestionConfig:
    """All knobs the ingestion process reads from.

    Defaults are tuned for the case-study dataset.
    Override via the TOML loader (`IngestionConfig.from_toml`).
    """

    # --- I/O ---
    snapshot_dir: Path = Path("data/snapshots")
    duckdb_path: Path = Path("duckdb/analytics.duckdb")

    # --- Target tables ---
    raw_schema: str = "raw"
    history_table: str = "cis_user_portfolio_histories"

    # --- Extra CSV tables (truncate-insert) ---
    extra_csv_tables: dict[str, str] = field(default_factory=lambda: {
        "data/cis_customers.csv": "cis_customers",
        "data/cis_products.csv": "cis_products",
    })

    # --- Snapshot discovery ---
    snapshot_glob: str = "*.csv"

    # --- Misc ---
    log_level: str = "INFO"

    @classmethod
    def from_toml(cls, path: str | Path) -> "IngestionConfig":
        """Load config from a TOML file with an [ingestion] section.

        Unknown keys are rejected. Missing keys fall back to dataclass defaults.
        """
        path = Path(path)
        with path.open("rb") as f:
            data = tomllib.load(f)
        section: dict[str, Any] = dict(data.get("ingestion", {}))

        # Coerce known keys to expected types.
        if "snapshot_dir" in section:
            section["snapshot_dir"] = Path(section["snapshot_dir"])
        if "duckdb_path" in section:
            section["duckdb_path"] = Path(section["duckdb_path"])
        if "business_key" in section:
            # Accept either a list or a single string in TOML.
            bk = section["business_key"]
            if isinstance(bk, str):
                bk = [bk]
            section["business_key"] = tuple(bk)

        # Reject unknown keys early for clear errors.
        valid = {f.name for f in fields(cls)}
        unknown = set(section) - valid
        if unknown:
            raise ValueError(
                f"Unknown config keys in {path}: {sorted(unknown)}. "
                f"Valid keys: {sorted(valid)}"
            )
        return cls(**section)
