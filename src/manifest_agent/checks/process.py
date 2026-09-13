"""Bounded subprocess primitive for check consumers."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool


def run_argv(
    argv: tuple[str, ...], cwd: Path, env: dict[str, str], timeout_seconds: float
) -> ProcessResult:
    start = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env or None,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return ProcessResult(
            result.returncode,
            result.stdout,
            result.stderr[-65536:],
            time.monotonic() - start,
            False,
        )
    except subprocess.TimeoutExpired as error:
        return ProcessResult(
            None,
            error.stdout or "",
            (error.stderr or "")[-65536:],
            time.monotonic() - start,
            True,
        )
