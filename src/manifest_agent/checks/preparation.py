"""Candidate-local declared preparation execution."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

from .models import Candidate


def prepare_candidate(
    candidate: Candidate,
    argv: Sequence[str],
    cwd: str = ".",
    timeout_seconds: float = 30,
) -> dict[str, str]:
    try:
        result = subprocess.run(
            argv,
            cwd=candidate.root / cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "BLOCKED", "diagnostics": str(error)}
    return {
        "status": "PASS" if result.returncode == 0 else "BLOCKED",
        "diagnostics": (result.stderr or result.stdout)[-4096:],
    }
