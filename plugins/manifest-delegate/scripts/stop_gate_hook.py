#!/usr/bin/env python3
# help-coverage: covered by tests/bats/help_coverage.bats
"""Stop hook thin wrapper for the manifest-delegate soft review gate.

Reads the Stop hook's stdin JSON (session_id, transcript_path, cwd,
hook_event_name, stop_hook_active), forwards transcript_path (and
--stop-hook-active when true) to `delegate.py gate --json`, and passes the
gate's hook-JSON decision straight through to stdout. See
specs/675-multi-agent-delegation/contracts/delegate-cli.md ("gate").
"""

import sys

# --- Early interpreter version probe (D11) --------------------------------
if sys.version_info < (3, 9):  # noqa: UP036 — deliberate runtime guard, see D11
    sys.stderr.write(
        "stop_gate_hook.py: unsupported Python version %s.%s — "  # noqa: UP031
        "manifest-delegate requires Python 3.9 or newer.\n"
        "Install a supported interpreter, e.g.:\n"
        "  macOS:  brew install python@3.11\n"
        "  Linux:  use your distro's python3.9+ package\n"
        "Then re-run with that interpreter's `python3` on PATH.\n"
        % (sys.version_info[0], sys.version_info[1])
    )
    sys.exit(2)

import argparse
import json
import os
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DELEGATE_PY = os.path.join(SCRIPT_DIR, "delegate.py")


def main(argv=None):
    # type: (list[str] | None) -> int
    """Forward the Stop hook's transcript to `delegate.py gate` and relay its JSON.

    Fails open (returns 0, emits a systemMessage) on missing transcript_path,
    malformed stdin JSON, or any subprocess error — a hook must never crash
    or block the session it is attached to.
    """
    parser = argparse.ArgumentParser(
        prog="stop_gate_hook.py",
        description="Stop hook wrapper: forwards transcript to `delegate.py gate`.",
    )
    parser.add_argument(
        "--stdin-json",
        metavar="FILE",
        default=None,
        help="read hook payload from FILE instead of stdin (testing)",
    )
    args = parser.parse_args(argv)

    if args.stdin_json:
        with open(args.stdin_json, encoding="utf-8") as fh:
            raw = fh.read()
    else:
        raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        # Fail open: no transcript means nothing to gate.
        print(
            json.dumps(
                {
                    "systemMessage": "review gate skipped: no transcript_path in Stop payload"
                }
            )
        )
        return 0

    cmd = [
        sys.executable,
        DELEGATE_PY,
        "gate",
        "--transcript",
        transcript_path,
        "--json",
    ]
    if payload.get("stop_hook_active"):
        cmd.append("--stop-hook-active")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=840)
    except Exception as exc:
        _fail_open(f"subprocess error: {exc}")
        return 0

    out = result.stdout.strip()
    if result.returncode != 0:
        _fail_open(
            f"delegate.py gate exited {result.returncode}: {_tail(result.stderr)}"
        )
        return 0
    if not out:
        _fail_open(
            f"delegate.py gate produced no output; stderr: {_tail(result.stderr)}"
        )
        return 0
    try:
        json.loads(out)
    except ValueError as exc:
        _fail_open(
            f"delegate.py gate produced invalid JSON ({exc}); stderr: {_tail(result.stderr)}"
        )
        return 0

    sys.stdout.write(out + "\n")
    return 0


def _tail(stderr, limit=500):
    # type: (str, int) -> str
    """Bounded stderr excerpt for a fail-open systemMessage."""
    text = (stderr or "").strip()
    return text[-limit:] if text else "(no stderr)"


def _fail_open(cause):
    # type: (str) -> None
    """Emit the fail-open hook decision so the gate visibly no-ops."""
    print(json.dumps({"systemMessage": f"review gate skipped: {cause}"}))


if __name__ == "__main__":
    sys.exit(main())
