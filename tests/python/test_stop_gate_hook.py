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


def test_wrapper_timeout_outlasts_backend_budget_cap():
    """Codex HIGH: the outer wrapper timeout must exceed the gate's BACKEND
    budget cap by real cleanup overhead. Otherwise a backend near the cap makes
    the wrapper time out FIRST, so subprocess.run kills only delegate.py and
    orphans the detached backend group while the hook fails open. The prior
    test suite only bounded the wrapper at <=840s, which codified the collision
    (equal timeouts) instead of catching it — this asserts strict layering."""
    import importlib.util

    pkg_dir = SCRIPT.parent.parent  # plugins/manifest-delegate
    if str(pkg_dir) not in sys.path:
        sys.path.insert(0, str(pkg_dir))
    from manifest_delegate import config

    spec = importlib.util.spec_from_file_location("stop_gate_hook", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    wrapper = mod.GATE_WRAPPER_TIMEOUT_SECONDS
    cap = config.GATE_BUDGET_CAP_SECONDS
    overhead = wrapper - cap
    assert overhead >= 30, (
        f"wrapper timeout ({wrapper}s) must outlast the backend cap ({cap}s) by "
        f"real cleanup overhead so the gate reaps its backend before the wrapper "
        f"kills delegate.py; got {overhead}s of headroom"
    )


def test_wrapper_timeout_stays_under_the_declared_hook_timeout():
    """The declared hooks.json Stop timeout is the harness's hard ceiling.

    Only the lower bound (wrapper > backend cap) was ever guarded, so the
    wrapper sat at exactly the declared 900s with no room to catch
    TimeoutExpired, format, and flush its fail-open JSON -- Claude Code would
    kill it mid-write and receive no decision at all. Bound the other end too:
    backend cap < wrapper < declared hook timeout.
    """
    import importlib.util

    pkg_dir = SCRIPT.parent.parent
    if str(pkg_dir) not in sys.path:
        sys.path.insert(0, str(pkg_dir))

    spec = importlib.util.spec_from_file_location("stop_gate_hook", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    hooks = json.loads((pkg_dir / "hooks" / "hooks.json").read_text())
    stop_timeouts = [
        hook["timeout"]
        for matcher in hooks["hooks"]["Stop"]
        for hook in matcher["hooks"]
        if "timeout" in hook
    ]
    assert stop_timeouts, "hooks.json declares no Stop timeout to bound against"
    declared = min(stop_timeouts)
    wrapper = mod.GATE_WRAPPER_TIMEOUT_SECONDS
    margin = declared - wrapper
    assert margin >= 15, (
        f"wrapper timeout ({wrapper}s) must stay under the declared Stop hook "
        f"timeout ({declared}s) by enough to catch, format, and flush the "
        f"fail-open decision; got {margin}s of margin"
    )
