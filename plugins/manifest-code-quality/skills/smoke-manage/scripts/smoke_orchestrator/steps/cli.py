"""CLI/shell step runner — subprocess with an argument array (T016).

Security (research R2, Constitution Tier-1): the command is ALWAYS an argument
list and is executed without a shell (no ``shell=True``). Resolved ``${state.*}``
values land in discrete argv elements, so a captured token can never inject a
second command. Captures pull a regex group (or whole match) from stdout.
"""

from __future__ import annotations

import re
import subprocess

from . import CaptureError, StepOutcome


def run(step: dict, *, timeout_s: float) -> StepOutcome:
    args = step["command"]  # validated: non-empty list[str]; already resolved
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return StepOutcome(False, f"timed out after {timeout_s:g}s")
    except FileNotFoundError:
        return StepOutcome(False, f"command not found: {args[0]!r}")
    except (
        OSError
    ) as exc:  # e.g. PermissionError / IsADirectoryError — fail the step, not the run
        return StepOutcome(
            False, f"could not execute {args[0]!r}: {type(exc).__name__}"
        )
    expect = step.get("expect_exit", 0)
    if proc.returncode != expect:
        stderr = (proc.stderr or "").strip()[:200]
        return StepOutcome(
            False, f"exit {proc.returncode} (expected {expect}); stderr: {stderr}"
        )
    return StepOutcome(True, captures=_extract(step.get("captures", {}), proc.stdout))


def _extract(captures: dict, stdout: str) -> dict:
    out: dict = {}
    for name, pattern in captures.items():
        m = re.search(pattern, stdout)
        if m is None:
            raise CaptureError(
                f"cli capture {name!r}: pattern {pattern!r} matched nothing in stdout"
            )
        out[name] = m.group(1) if m.groups() else m.group(0)
    return out
