"""Analytics pipeline flow — dbt debug → dbt run → dbt build.

Strict ordering enforced by calling ``.result()`` before next step.
Flow-level retries = 0 (task-level retries handle transients).
"""
from __future__ import annotations

from prefect import flow, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner

from orchestration.tasks.dbt import dbt_build, dbt_debug, dbt_run
from orchestration.utils.config import OrchestrationConfig
from orchestration.utils.logging import install_json_handler, log_dict


@flow(
    name="analytics-pipeline",
    description="dbt debug → dbt run → dbt build",
    timeout_seconds=3600,
    task_runner=ConcurrentTaskRunner(),
    retries=0,
)
def analytics_pipeline(
    cfg: OrchestrationConfig | None = None,
    *,
    full_refresh: bool = False,
) -> dict:
    """Run the three-step dbt pipeline.

    Args:
        cfg: env-driven config. ``None`` → ``OrchestrationConfig()``.
        full_refresh: pass ``--full-refresh`` to dbt run + build.
    """
    cfg = cfg or OrchestrationConfig()
    install_json_handler(cfg.log_level)
    logger = get_run_logger()

    log_dict(logger, "info", "pipeline.start",
             duckdb_path=str(cfg.duckdb_path),
             dbt_target=cfg.dbt_target,
             full_refresh=full_refresh)

    # 1. dbt debug  (health check — fail fast if profile broken)
    dbt_debug.submit(cfg).result()

    # 2. dbt run    (materialise models)
    run_metrics = dbt_run.submit(cfg, full_refresh=full_refresh).result()

    # 3. dbt build  (seeds + models + snapshots + tests — full DAG)
    build_metrics = dbt_build.submit(cfg, full_refresh=full_refresh).result()

    summary = {
        "run": run_metrics,
        "build": build_metrics,
    }
    log_dict(logger, "info", "pipeline.complete",
             build_full_refresh=build_metrics.get("full_refresh"))
    return summary


@flow(
    name="analytics-pipeline-daily",
    description="Scheduled entry — daily 01:00 Asia/Bangkok.",
    timeout_seconds=3600,
    task_runner=ConcurrentTaskRunner(),
)
def analytics_pipeline_daily() -> dict:
    """No-arg wrapper for the scheduled deployment."""
    return analytics_pipeline(OrchestrationConfig(), full_refresh=False)
