"""Structured JSON logging for Prefect tasks.

NOTE: we deliberately never pass ``name=`` to ``get_run_logger()``.
Prefect 3.x stores that kwarg in the adapter's ``extra`` dict, which
then conflicts with the built-in ``LogRecord.name`` attribute and raises
``KeyError("Attempt to overwrite 'name' in LogRecord")``.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

from prefect.logging import get_run_logger


class JsonFormatter(logging.Formatter):
    """One JSON object per log line — container-friendly."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in (
            "flow_run_id", "flow_run_name",
            "task_run_id", "task_run_name",
            "deployment_id", "deployment_name",
        ):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def install_json_handler(level: str = "INFO") -> None:
    """Attach JSON stdout handler to root logger. Idempotent."""
    root = logging.getLogger()
    target = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(target)

    for h in root.handlers:
        if getattr(h, "_orch_json", False):
            h.setLevel(target)
            return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(target)
    handler.setFormatter(JsonFormatter())
    handler._orch_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)


def get_logger():
    """Prefect run logger inside a flow/task; stdlib logger otherwise.

    Never passes ``name=`` to ``get_run_logger()`` to avoid the
    ``KeyError("Attempt to overwrite 'name' in LogRecord")`` bug in
    Prefect 3.x.
    """
    try:
        return get_run_logger()
    except Exception:
        install_json_handler()
        return logging.getLogger("orchestration")


def log_dict(logger: logging.Logger, level: str, message: str, **fields: Any) -> None:
    """Emit structured log. Fields are embedded in the message as JSON.

    We avoid ``extra={...}`` because Prefect's ``PrefectLogAdapter``
    also sets ``extra`` keys internally, and collisions with built-in
    ``LogRecord`` attributes cause ``KeyError``.
    """
    if fields:
        message = f"{message} | {json.dumps(fields, default=str)}"
    getattr(logger, level.lower(), logger.info)(message)
