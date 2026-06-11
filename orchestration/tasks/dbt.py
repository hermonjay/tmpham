"""dbt tasks: debug, run, build.

Each task is independently retriable with its own timeout.
All tasks share ``OrchestrationConfig`` for CLI flags.
"""
from __future__ import annotations

from typing import Any

from prefect import task

from orchestration.utils.config import OrchestrationConfig
from orchestration.utils.logging import get_logger, log_dict
from orchestration.utils.shell import ShellError, run_shell


@task(
    name="dbt-debug",
    description="dbt debug — verify connection + profile configuration.",
    retries=1,
    retry_delay_seconds=15,
    timeout_seconds=120,
)
def dbt_debug(cfg: OrchestrationConfig) -> dict[str, Any]:
    """Health-check: confirms dbt can connect to DuckDB and profile is valid.

    dbt debug exit codes are unreliable across versions — some exit 1
    even when the connection works (e.g. missing ``profiles.yml`` entry
    that isn't actually needed). We parse stdout instead.
    """
    logger = get_logger()
    argv = cfg.dbt_argv("debug")
    log_dict(logger, "info", "dbt.debug.start", target=cfg.dbt_target, cmd=" ".join(argv))

    stdout = ""
    try:
        result = run_shell(argv, timeout_seconds=120, logger=logger,
                           cwd=str(cfg.dbt_project_dir))
        stdout = result.stdout or ""
    except ShellError as exc:
        # dbt debug may exit non-zero even with a working connection.
        # Log the output but check the actual test results below.
        stdout = exc.stdout or ""
        log_dict(logger, "warning", "dbt.debug.nonzero",
                 returncode=exc.returncode,
                 stdout_tail=stdout[-600:],
                 stderr_tail=(exc.stderr or "")[-400:])
        for line in stdout.splitlines():
            logger.info("dbt debug | %s", line)

    # Strip ANSI colour codes so string matching works on raw dbt output.
    import re
    plain = re.sub(r"\x1b\[[0-9;]*m", "", stdout)

    # The real test: can dbt reach the database?
    all_passed = "All checks passed" in plain
    connection_ok = all_passed or "Connection test: [OK" in plain

    log_dict(logger, "info", "dbt.debug.done",
             all_checks_passed=all_passed, connection_ok=connection_ok)

    if not connection_ok:
        logger.error("dbt debug output:\n%s", stdout[-2000:])
        raise RuntimeError(
            f"dbt debug: connection failed. stdout tail:\n{stdout[-2000:]}"
        )

    return {"step": "debug", "all_checks_passed": all_passed, "connection_ok": True}


@task(
    name="dbt-run",
    description="dbt run — materialise staging, marts, reports.",
    retries=3,
    retry_delay_seconds=60,
    timeout_seconds=1800,
)
def dbt_run(cfg: OrchestrationConfig, *, full_refresh: bool = False) -> dict[str, Any]:
    """Materialise all models. Optionally ``--full-refresh``."""
    logger = get_logger()
    extra: list[str] = []
    do_full = full_refresh or cfg.dbt_full_refresh
    if do_full:
        extra.append("--full-refresh")
    argv = cfg.dbt_argv("run", *extra)

    log_dict(logger, "info", "dbt.run.start",
             target=cfg.dbt_target, full_refresh=do_full)

    result = run_shell(argv, timeout_seconds=cfg.dbt_timeout, logger=logger,
                        cwd=str(cfg.dbt_project_dir))
    return {
        "step": "run",
        "full_refresh": do_full,
        "stdout_tail": (result.stdout or "")[-800:],
    }


@task(
    name="dbt-build",
    description="dbt build — seeds + models + snapshots + tests in DAG order.",
    retries=3,
    retry_delay_seconds=60,
    timeout_seconds=1800,
)
def dbt_build(cfg: OrchestrationConfig, *, full_refresh: bool = False) -> dict[str, Any]:
    """Full dbt build (seeds → models → snapshots → tests)."""
    logger = get_logger()
    extra: list[str] = []
    do_full = full_refresh or cfg.dbt_full_refresh
    if do_full:
        extra.append("--full-refresh")
    argv = cfg.dbt_argv("build", *extra)

    log_dict(logger, "info", "dbt.build.start",
             target=cfg.dbt_target, full_refresh=do_full)

    result = run_shell(argv, timeout_seconds=cfg.dbt_timeout, logger=logger,
                        cwd=str(cfg.dbt_project_dir))
    return {
        "step": "build",
        "full_refresh": do_full,
        "stdout_tail": (result.stdout or "")[-800:],
    }
