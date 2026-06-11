"""Deployment helpers — schedules and serve/push patterns.

Schedule: daily 01:00 Asia/Bangkok (UTC+7) = 18:00 UTC.

Three patterns:
  1. ``serve_local()``       — ad-hoc, no schedule, long-poll worker
  2. ``serve_scheduled()``   — local worker + daily schedule
  3. ``deploy_to_work_pool`` — push to remote Prefect server work pool

CLI:
    uv run python -m orchestration.deployments.schedule serve_local
    uv run python -m orchestration.deployments.schedule serve_scheduled
    uv run python -m orchestration.deployments.schedule deploy_to_work_pool
"""
from __future__ import annotations

import sys

from prefect import serve
from prefect.client.schemas.schedules import CronSchedule

from orchestration.flows.pipeline import analytics_pipeline, analytics_pipeline_daily


# 01:00 Asia/Bangkok = 18:00 UTC
DAILY_01_00_BANGKOK = CronSchedule(
    cron="0 18 * * *",
    timezone="UTC",           # cron expression is already UTC-converted
)

# Alt: express in local timezone directly
DAILY_01_00_BANGKOK_LOCAL = CronSchedule(
    cron="0 1 * * *",
    timezone="Asia/Bangkok",
)


def serve_local() -> None:
    """Ad-hoc local worker — no schedule. Ctrl-C exits."""
    deployment = analytics_pipeline.to_deployment(
        name="analytics-pipeline-local",
        tags=["local", "dev"],
        description="Local ad-hoc runs.",
    )
    serve(deployment)


def serve_scheduled() -> None:
    """Local worker with daily 01:00 Asia/Bangkok schedule."""
    deployment = analytics_pipeline_daily.to_deployment(
        name="analytics-pipeline-daily",
        schedule=DAILY_01_00_BANGKOK,
        tags=["scheduled", "daily", "prod"],
        description="Daily 01:00 Asia/Bangkok (UTC+7).",
    )
    serve(deployment)


def deploy_to_work_pool(pool: str = "analytics-process-pool") -> None:
    """Push deployment to a process work pool.

    Requires:
        prefect work-pool create --type process analytics-process-pool
    """
    deployment = analytics_pipeline_daily.to_deployment(
        name="analytics-pipeline-daily-prod",
        schedule=DAILY_01_00_BANGKOK,
        tags=["scheduled", "daily", "prod"],
        work_pool_name=pool,
    )
    serve(deployment)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0] if argv else "serve_local"
    handlers = {
        "serve_local": lambda: serve_local(),
        "serve_scheduled": lambda: serve_scheduled(),
        "deploy_to_work_pool": lambda: deploy_to_work_pool(
            argv[1] if len(argv) > 1 else "analytics-process-pool"
        ),
    }
    if mode not in handlers:
        print(f"unknown: {mode!r}. valid: {sorted(handlers)}", file=sys.stderr)
        return 2
    handlers[mode]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
