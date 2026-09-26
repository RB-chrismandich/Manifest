#!/usr/bin/env python3
# help-coverage: covered by tests/bats/help_coverage.bats
"""Fail-closed Python boundary for the manifest-delegate Stop review gate.

The POSIX launcher owns interpreter availability and validates this script's
decision before forwarding it. This layer parses the Stop payload, handles the
exact boolean recursion guard, invokes ``delegate.py gate --json`` with the same
managed interpreter, and turns every unverified result into a sanitized block.
Raw subprocess output and stderr are never relayed.
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

# The backend cap is 840 seconds. This wrapper must leave it cleanup headroom
# while still finishing before hooks.json's 900-second harness deadline.
GATE_WRAPPER_TIMEOUT_SECONDS = 870


def _read_payload(argv):
    # type: (list[str] | None) -> tuple[dict | None, str | None]
    """Return one object payload and a stable error code."""
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

    try:
        if args.stdin_json:
            with open(args.stdin_json, encoding="utf-8") as fh:
                raw = fh.read()
        else:
            raw = sys.stdin.read()
    except (OSError, UnicodeError):
        return None, "input_unreadable"
    if not raw.strip():
        return None, "empty_input"
    try:
        payload = json.loads(raw)
    except ValueError:
        return None, "invalid_input"
    if not isinstance(payload, dict):
        return None, "invalid_input"
    return payload, None


def _relay_gate_decision(result):
    # type: (subprocess.CompletedProcess) -> None
    """Validate and canonicalize the gate decision; never relay raw stderr."""
    if result.returncode != 0:
        _fail_closed("delegate_failed")
        return
    out = result.stdout.strip()
    if not out:
        _fail_closed("empty_decision")
        return
    try:
        decision = json.loads(out)
    except ValueError:
        _fail_closed("invalid_decision")
        return
    if (
        not isinstance(decision, dict)
        or decision.get("decision") not in {"approve", "block"}
        or not isinstance(decision.get("reason"), str)
        or not decision["reason"].strip()
    ):
        _fail_closed("invalid_decision")
        return
    print(json.dumps({"decision": decision["decision"], "reason": decision["reason"]}))


def main(argv=None):
    # type: (list[str] | None) -> int
    """Run one bounded review decision and always speak native hook JSON."""
    payload, error_reason = _read_payload(argv)
    if error_reason:
        _fail_closed(error_reason)
        return 0

    # Only the native boolean activates loop safety. This must precede every
    # transcript check, import, and subprocess launch so a blocked turn can be
    # reported to the developer without recursively reviewing that report.
    if payload.get("stop_hook_active") is True:
        print(json.dumps({"decision": "approve", "reason": "stop-hook-active"}))
        return 0

    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path.strip():
        _fail_closed("missing_transcript")
        return 0

    cmd = [
        sys.executable,
        DELEGATE_PY,
        "gate",
        "--transcript",
        transcript_path,
        "--json",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=GATE_WRAPPER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        _fail_closed("delegate_timeout")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        _fail_closed("delegate_unavailable")
        return 0

    _relay_gate_decision(result)
    return 0


_SAFE_FAILURE_REASONS = frozenset(
    {
        "delegate_failed",
        "delegate_timeout",
        "delegate_unavailable",
        "empty_decision",
        "empty_input",
        "input_unreadable",
        "invalid_decision",
        "invalid_input",
        "missing_transcript",
    }
)


def _fail_closed(reason_code):
    # type: (str) -> None
    """Emit the fixed refusal shape using only an allowlisted reason code."""
    if reason_code not in _SAFE_FAILURE_REASONS:
        reason_code = "delegate_failed"
    reason = (
        f"Review gate could not verify this turn ({reason_code}); make no tool calls or "
        "edits; report the failure to the developer for a decision."
    )
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    sys.exit(main())
