"""Orchestration config — env-driven, frozen dataclass.

All fields read from env at *construction* time (not import time) via
``field(default_factory=...)`` so monkeypatching ``os.environ`` in tests
affects new instances correctly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class OrchestrationConfig:
    """Runtime knobs. Override via env vars; sane defaults for local dev."""

    # --- paths ---
    duckdb_path: Path = field(
        default_factory=lambda: Path(_env("DUCKDB_PATH", "duckdb/analytics.duckdb")),
    )
    snapshot_dir: Path = field(
        default_factory=lambda: Path(_env("SNAPSHOT_DIR", "data/snapshots")),
    )

    # --- dbt ---
    dbt_project_dir: Path = field(
        default_factory=lambda: Path(_env("DBT_PROJECT_DIR", "dbt")),
    )
    dbt_profiles_dir: Path = field(
        default_factory=lambda: Path(_env("DBT_PROFILES_DIR", "dbt")),
    )
    dbt_target: str = field(default_factory=lambda: _env("DBT_TARGET", "prod"))
    dbt_full_refresh: bool = field(
        default_factory=lambda: _env("DBT_FULL_REFRESH", "false").lower() == "true",
    )

    # --- retry / timeout ---
    ingest_retries: int = field(default_factory=lambda: int(_env("INGEST_RETRIES", "2")))
    ingest_retry_delay: int = field(
        default_factory=lambda: int(_env("INGEST_RETRY_DELAY", "30")),
    )
    ingest_timeout: int = field(
        default_factory=lambda: int(_env("INGEST_TIMEOUT", "900")),
    )

    dbt_retries: int = field(default_factory=lambda: int(_env("DBT_RETRIES", "3")))
    dbt_retry_delay: int = field(
        default_factory=lambda: int(_env("DBT_RETRY_DELAY", "60")),
    )
    dbt_timeout: int = field(
        default_factory=lambda: int(_env("DBT_TIMEOUT", "1800")),
    )

    # --- misc ---
    runner: str = field(default_factory=lambda: _env("ORCH_RUNNER", "uv"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    def dbt_argv(self, *extra: str) -> list[str]:
        """Build a full dbt CLI invocation (runner prefix + flags)."""
        prefix = ["uv", "run", "dbt"] if self.runner == "uv" else ["dbt"]
        argv = prefix + list(extra)
        argv += ["--project-dir", str(self.dbt_project_dir)]
        argv += ["--profiles-dir", str(self.dbt_profiles_dir)]
        argv += ["--target", self.dbt_target]
        return argv
