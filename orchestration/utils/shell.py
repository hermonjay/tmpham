"""Subprocess runner with timeout + structured logging.

Captures stdout/stderr, logs on completion, raises ``ShellError`` on failure.
All stdout/stderr lines are streamed through the logger so they appear in
Prefect UI.
"""
from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Sequence

from orchestration.utils.logging import log_dict

# ANSI colour codes — strip before logging to keep output clean.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class ShellError(RuntimeError):
    """Non-zero or timed-out subprocess."""

    def __init__(
        self,
        cmd: Sequence[str],
        returncode: int,
        stdout: str,
        stderr: str,
        *,
        timed_out: bool = False,
    ):
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        label = "timed out" if timed_out else f"exited {returncode}"
        super().__init__(
            f"{shlex.join(self.cmd)}: {label}"
            f"\n  stderr: {stderr[-500:]!r}"
            f"\n  stdout: {stdout[-500:]!r}"
        )


@dataclass
class ShellResult:
    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def run_shell(
    cmd: Sequence[str],
    *,
    cwd: str | None = None,
    timeout_seconds: int | None = None,
    logger=None,
    env: dict[str, str] | None = None,
) -> ShellResult:
    """Run subprocess, capture output, log every line, raise on failure."""
    cmd_list = list(cmd)
    pretty = shlex.join(cmd_list)

    if logger:
        log_dict(logger, "info", "shell.run", cmd=pretty, cwd=cwd, timeout=timeout_seconds)

    try:
        proc = subprocess.run(
            cmd_list, cwd=cwd, timeout=timeout_seconds,
            capture_output=True, text=True, env=env, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        if logger:
            log_dict(logger, "error", "shell.timeout", cmd=pretty)
        raise ShellError(
            cmd_list, -1, exc.stdout or "", exc.stderr or "", timed_out=True,
        ) from exc

    level = "info" if proc.returncode == 0 else "error"

    if logger:
        # Stream every stdout line through the logger (visible in Prefect UI).
        for line in (proc.stdout or "").splitlines():
            logger.info(_strip_ansi(line))
        for line in (proc.stderr or "").splitlines():
            getattr(logger, level)(_strip_ansi(line))

        log_dict(logger, level, "shell.done", cmd=pretty,
                 returncode=proc.returncode)

    if proc.returncode != 0:
        raise ShellError(cmd_list, proc.returncode, proc.stdout or "", proc.stderr or "")

    return ShellResult(cmd_list, proc.returncode, proc.stdout or "", proc.stderr or "")
