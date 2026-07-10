"""LLM invocation seam (FR-008, FR-012; research D4/D11).

Prompts travel via stdin (ARG_MAX-safe, llm-invoke-stdin); argv carries only
fixed flags. Every invocation gets exactly one retry (call failure or validator
rejection), then the run aborts fail-closed. Per-call timeout is additionally
capped by the remaining whole-run budget.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable

from . import AbortError

Runner = Callable[[list, str, float], tuple]


def default_runner(argv: list, prompt: str, timeout: float) -> tuple:
    proc = subprocess.run(
        argv, input=prompt, capture_output=True, text=True, timeout=timeout
    )
    return proc.returncode, proc.stdout, proc.stderr


def invoke_role(
    model: str,
    prompt: str,
    config,
    *,
    runner: Runner | None = None,
    deadline: float | None = None,
    validator: Callable[[str], str | None] | None = None,
    role_name: str = "role",
) -> str:
    """Invoke the CLI for one role; return raw stdout or raise AbortError.

    validator(output) returns None when acceptable, else a problem description
    that is fed back in the single retry prompt (verdict-format contract).
    """
    run = runner or default_runner
    argv = [config.cli, "-p", "--model", model]
    attempt_prompt = prompt
    last_error = "unknown failure"

    for _attempt in (1, 2):
        timeout = float(config.invoke_timeout_s)
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AbortError(
                    f"run deadline expired before invoking {role_name} (FR-008)"
                )
            timeout = min(timeout, remaining)
        try:
            returncode, stdout, stderr = run(argv, attempt_prompt, timeout)
        except subprocess.TimeoutExpired:
            returncode, stdout, stderr = None, "", f"timed out after {timeout:.0f}s"

        if returncode == 0 and (stdout or "").strip():
            problem = validator(stdout) if validator else None
            if problem is None:
                return stdout
            last_error = problem
        else:
            last_error = (
                stderr or ""
            ).strip() or f"exit {returncode} with empty output"

        attempt_prompt = (
            prompt
            + "\n\n[cddl retry] Your previous response was not usable: "
            + str(last_error)
            + ". Follow the required output format exactly and try again."
        )

    raise AbortError(f"{role_name} invocation failed twice: {last_error}")
