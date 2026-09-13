"""Invoke `manifest check` via argv, no shell, with the real deadline and
process-group kill `checks/process.py::run_argv` already implements and
tests — this module never reimplements that mechanism."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from manifest_agent.process import redact_text

from ..checks.process import run_argv

_BOOTSTRAP = (
    "import runpy,sys;"
    "sys.path.insert(0,sys.argv.pop(1));"
    "runpy.run_module('manifest_agent',run_name='__main__',alter_sys=True)"
)

DIAGNOSTIC_CAP = 4096
RECURSION_ENV_VAR = "MANIFEST_HOOK_ACTIVE"
DEADLINE_ENV_VAR = "MANIFEST_HOOK_DEADLINE_MONOTONIC"
FORWARDED_ENV_KEYS = (
    "HOME",
    "PATH",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONPYCACHEPREFIX",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "XDG_STATE_HOME",
)


def run_manifest_check(
    *, profile: str, project_config: Path, base: str, cwd: Path, timeout_seconds: float
) -> tuple[str, str]:
    """Run the trusted coordinator without importing from the project cwd."""
    runtime_root = Path(__file__).resolve().parents[2]
    argv = (
        sys.executable,
        "-B",
        "-I",
        "-c",
        _BOOTSTRAP,
        str(runtime_root),
        "check",
        profile,
        "--project-config",
        str(project_config),
        "--base",
        base,
        "--json",
    )
    env = {key: os.environ[key] for key in FORWARDED_ENV_KEYS if key in os.environ}
    env[RECURSION_ENV_VAR] = "1"
    env["MANIFEST_HOOK_RUNTIME_ROOT"] = str(runtime_root)
    env[DEADLINE_ENV_VAR] = str(time.monotonic() + timeout_seconds)
    result = run_argv(argv, cwd=cwd, env=env, timeout_seconds=timeout_seconds)
    if result.timed_out:
        return "BLOCKED", "manifest check exceeded the adapter deadline"
    if result.error:
        return "BLOCKED", redact_text(result.error)[:DIAGNOSTIC_CAP]
    if result.returncode not in {0, 2, 3}:
        return "BLOCKED", "manifest check returned an invalid exit status"
    try:
        report = json.loads(result.stdout)
    except ValueError:
        return "BLOCKED", "manifest check returned invalid JSON"
    status = report.get("status") if isinstance(report, dict) else None
    expected_returncode = {"PASS": 0, "FAIL": 2, "BLOCKED": 3}
    if (
        status not in expected_returncode
        or result.returncode != expected_returncode[status]
    ):
        return "BLOCKED", "manifest check status and exit code were inconsistent"
    diagnostics = redact_text(result.stdout + result.stderr)[:DIAGNOSTIC_CAP]
    return status, diagnostics
