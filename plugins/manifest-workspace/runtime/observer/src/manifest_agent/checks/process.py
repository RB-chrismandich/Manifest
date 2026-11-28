"""Bounded subprocess primitive for check consumers."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

_DRAIN_GRACE_SECONDS = 0.25


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


@dataclass(frozen=True)
class ProcessResult:
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    error: str | None = None


def _close_pipe(pipe) -> None:
    if pipe is None:
        return
    with contextlib.suppress(OSError):
        pipe.close()


def _timeout_result(process: subprocess.Popen, start: float) -> ProcessResult:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    try:
        stdout, stderr = process.communicate(timeout=_DRAIN_GRACE_SECONDS)
        drain_error = None
    except subprocess.TimeoutExpired as drain:
        stdout, stderr = _text(drain.stdout), _text(drain.stderr)
        drain_error = "timed-out process left detached descendants holding pipes"
        _close_pipe(process.stdout)
        _close_pipe(process.stderr)
    return ProcessResult(
        None,
        stdout,
        stderr[-65536:],
        time.monotonic() - start,
        True,
        drain_error,
    )


def run_argv(
    argv: tuple[str, ...], cwd: Path, env: dict[str, str], timeout_seconds: float
) -> ProcessResult:
    start = time.monotonic()
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env or None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as error:
        return ProcessResult(None, "", "", time.monotonic() - start, False, str(error))
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return ProcessResult(
            process.returncode,
            stdout,
            stderr[-65536:],
            time.monotonic() - start,
            False,
        )
    except subprocess.TimeoutExpired:
        return _timeout_result(process, start)
