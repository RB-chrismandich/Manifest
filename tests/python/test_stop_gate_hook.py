"""stop_gate_hook.py — the Stop-hook thin wrapper around `delegate.py gate`.

A hook must never crash or block the session it's attached to, so every
failure path here (malformed stdin, gate disabled downstream) has to fail
open: exit 0 with a `systemMessage` explaining why the gate was skipped,
never a non-zero exit or an unhandled traceback.
"""

import json
import pathlib
import subprocess
import sys

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "plugins/manifest-delegate/scripts/stop_gate_hook.py"
)


def _run(stdin_text, timeout=30):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_help_exits_zero_within_15_lines():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert len(result.stdout.splitlines()) <= 15
    assert "usage" in result.stdout.lower()


def test_malformed_stdin_json_allows_stop():
    result = _run("{not valid json")
    assert result.returncode == 0
    payload = json.loads(result.stdout.strip())
    assert "systemMessage" in payload
    assert "skipped" in payload["systemMessage"].lower()


def test_missing_transcript_path_allows_stop():
    result = _run(json.dumps({"hook_event_name": "Stop"}))
    assert result.returncode == 0
    payload = json.loads(result.stdout.strip())
    assert "systemMessage" in payload
    assert "no transcript_path" in payload["systemMessage"]


def test_empty_stdin_allows_stop():
    result = _run("")
    assert result.returncode == 0
    payload = json.loads(result.stdout.strip())
    assert "systemMessage" in payload
