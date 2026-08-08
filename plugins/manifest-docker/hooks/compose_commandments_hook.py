#!/usr/bin/env python3
# help-coverage: exempt — PostToolUse adapter invoked by the harness with hook JSON
# on stdin, never by a user with flags.
"""PostToolUse adapter: audit a just-edited compose file against DC-001..DC-010.

Reads the Claude Code PostToolUse payload on stdin, and only for recognised
compose filenames runs the checker and writes its report to stderr.

Advisory by construction. Every failure path — malformed payload, missing
PyYAML, checker crash, timeout — exits 0, because a linting hook that can block
an edit is worse than no hook at all.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Set before the first local import: importing the checker to read the filename
# registry would otherwise litter __pycache__/ through an installed plugin, which
# has broken repo naming gates before.
sys.dont_write_bytecode = True

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
CHECKER = PLUGIN_ROOT / "scripts" / "compose_check.py"
TIMEOUT_SECONDS = 20
# The hook audits the whole file on every edit. Real stacks run ~5 findings per
# service, so an uncapped report on a large compose file would bury the edit the
# user actually made. The CLI stays uncapped.
HOOK_FINDING_LIMIT = 12


def edited_path(payload: dict) -> str:
    """The file the tool touched. Payload shape varies across Claude Code versions."""
    # Validated, not assumed: a corrupted or reshaped payload can put a scalar
    # where the mapping belongs, and `.get` on a string would raise outside the
    # protective try below — turning an advisory hook into a failed edit.
    tool_input = payload.get("tool_input")
    nested = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    raw = nested or payload.get("file_path") or ""
    return raw if isinstance(raw, str) else ""


def is_recognised(path: Path) -> bool:
    """True when the filename is one the rule registry claims."""
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
    from compose_check import is_compose_file, load_config

    return is_compose_file(path, load_config())


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    raw = edited_path(payload if isinstance(payload, dict) else {})
    if not raw:
        return 0
    path = Path(raw)
    if not path.is_file():
        return 0

    try:
        if not is_recognised(path):
            return 0
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(CHECKER),
                str(path),
                "--limit",
                str(HOOK_FINDING_LIMIT),
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    # constitution: exempt C-ERR — an advisory hook must never break the tool it
    # wraps; anything unexpected here means "stay quiet", not "fail the edit".
    except Exception:
        return 0

    report = (result.stdout or "").strip()
    if report:
        print(report, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
