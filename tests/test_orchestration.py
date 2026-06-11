"""Smoke tests for orchestration.

Run:
    uv run pytest tests/test_orchestration.py -v
"""
from __future__ import annotations

import json
import logging
import os
from unittest import mock

import pytest

from orchestration.utils.config import OrchestrationConfig
from orchestration.utils.logging import JsonFormatter, install_json_handler, log_dict
from orchestration.utils.shell import ShellError, run_shell


# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
def test_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKDB_PATH", "/tmp/test.duckdb")
    monkeypatch.setenv("DBT_TARGET", "ci")
    monkeypatch.setenv("DBT_FULL_REFRESH", "true")
    monkeypatch.setenv("ORCH_RUNNER", "direct")
    cfg = OrchestrationConfig()
    assert str(cfg.duckdb_path) == "/tmp/test.duckdb"
    assert cfg.dbt_target == "ci"
    assert cfg.dbt_full_refresh is True
    assert cfg.dbt_argv("debug") == [
        "dbt", "debug",
        "--project-dir", "dbt",
        "--profiles-dir", "dbt",
        "--target", "ci",
    ]


def test_config_defaults() -> None:
    for k in ("DUCKDB_PATH", "DBT_TARGET", "DBT_FULL_REFRESH", "ORCH_RUNNER"):
        os.environ.pop(k, None)
    cfg = OrchestrationConfig()
    assert cfg.dbt_argv("run")[:3] == ["uv", "run", "dbt"]
    assert cfg.ingest_retries == 2
    assert cfg.dbt_timeout == 1800


# ------------------------------------------------------------------
# Shell runner
# ------------------------------------------------------------------
def test_shell_ok() -> None:
    res = run_shell(["echo", "hello"], logger=logging.getLogger("test"))
    assert res.ok
    assert "hello" in res.stdout


def test_shell_nonzero_raises() -> None:
    with pytest.raises(ShellError) as exc:
        run_shell(["sh", "-c", "exit 7"])
    assert exc.value.returncode == 7
    assert not exc.value.timed_out


def test_shell_timeout() -> None:
    with pytest.raises(ShellError) as exc:
        run_shell(["sleep", "5"], timeout_seconds=1)
    assert exc.value.timed_out


# ------------------------------------------------------------------
# JSON logging
# ------------------------------------------------------------------
def test_json_formatter() -> None:
    rec = logging.LogRecord(
        "test", logging.INFO, __file__, 1, "hello %s", ("world",), None,
    )
    payload = json.loads(JsonFormatter().format(rec))
    assert payload["msg"] == "hello world"
    assert payload["level"] == "INFO"


def test_install_handler_idempotent() -> None:
    install_json_handler("DEBUG")
    n = len(logging.getLogger().handlers)
    install_json_handler("INFO")
    assert len(logging.getLogger().handlers) == n


# ------------------------------------------------------------------
# Flow smoke (tasks stubbed)
# ------------------------------------------------------------------
def test_flow_with_stubbed_tasks() -> None:
    from orchestration.flows.pipeline import analytics_pipeline

    fake = {
        "dbt_debug": {"step": "debug", "all_checks_passed": True},
        "dbt_run": {"step": "run", "full_refresh": False},
        "dbt_build": {"step": "build", "full_refresh": False},
    }

    class _F:
        def __init__(self, v): self.v = v
        def result(self): return self.v

    def _stub(name):
        def _fn(*a, **kw): return _F(fake[name])
        return _fn

    patches = [
        mock.patch(f"orchestration.flows.pipeline.{n}.submit", side_effect=_stub(n))
        for n in fake
    ]
    with patches[0], patches[1], patches[2]:
        result = analytics_pipeline(OrchestrationConfig())

    assert result["build"]["step"] == "build"
