"""Fail-closed Stop-hook wrapper and POSIX launcher contracts.

Every infrastructure or decision-shape failure must emit one sanitized block
decision with exit 0.  The one loop-safety exception is the exact boolean
``stop_hook_active is True`` guard, which approves without starting Python or a
review backend.
"""

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "plugins/manifest-delegate/scripts/stop_gate_hook.py"
)
SHELL = SCRIPT.with_suffix(".sh")
PLUGIN_ROOT = SCRIPT.parent.parent


def _run(stdin_text, timeout=30):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _load_module():
    spec = importlib.util.spec_from_file_location("stop_gate_hook", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decision(result):
    assert result.returncode == 0
    return json.loads(result.stdout.strip())


def _run_shell(payload, home, extra_env=None):
    environment = dict(os.environ)
    environment.update(
        {
            "HOME": str(home),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
        }
    )
    environment.update(extra_env or {})
    return subprocess.run(
        ["/bin/sh", str(SHELL)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
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


def test_malformed_stdin_json_blocks_stop():
    payload = _decision(_run("{not valid json"))
    assert payload["decision"] == "block"
    assert "invalid_input" in payload["reason"]
    assert "not valid json" not in payload["reason"]


def test_missing_transcript_path_blocks_stop():
    payload = _decision(_run(json.dumps({"hook_event_name": "Stop"})))
    assert payload["decision"] == "block"
    assert "missing_transcript" in payload["reason"]


def test_empty_stdin_blocks_stop():
    payload = _decision(_run(""))
    assert payload["decision"] == "block"
    assert "empty_input" in payload["reason"]


def test_wrapper_timeout_outlasts_backend_budget_cap():
    """The outer wrapper must outlast the backend cap so the gate can reap the
    backend before the wrapper emits its fail-closed decision."""
    if str(PLUGIN_ROOT) not in sys.path:
        sys.path.insert(0, str(PLUGIN_ROOT))
    from manifest_delegate import config

    mod = _load_module()

    wrapper = mod.GATE_WRAPPER_TIMEOUT_SECONDS
    cap = config.GATE_BUDGET_CAP_SECONDS
    overhead = wrapper - cap
    assert overhead >= 30, (
        f"wrapper timeout ({wrapper}s) must outlast the backend cap ({cap}s) by "
        f"real cleanup overhead so the gate reaps its backend before the wrapper "
        f"kills delegate.py; got {overhead}s of headroom"
    )


def test_wrapper_timeout_stays_under_the_declared_hook_timeout():
    """The harness deadline must leave time to emit the fail-closed decision."""
    mod = _load_module()

    hooks = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
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
        f"fail-closed decision; got {margin}s of margin"
    )


def test_boolean_recursion_guard_approves_without_spawning(
    tmp_path, monkeypatch, capsys
):
    mod = _load_module()
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"stop_hook_active": True}), encoding="utf-8")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("recursion guard spawned delegate.py")

    monkeypatch.setattr(mod.subprocess, "run", forbidden)
    assert mod.main(["--stdin-json", str(payload)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "decision": "approve",
        "reason": "stop-hook-active",
    }


def test_truthy_non_boolean_recursion_flag_does_not_bypass_review(tmp_path, capsys):
    mod = _load_module()
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"stop_hook_active": "true"}), encoding="utf-8")

    assert mod.main(["--stdin-json", str(payload)]) == 0
    decision = json.loads(capsys.readouterr().out)
    assert decision["decision"] == "block"
    assert "missing_transcript" in decision["reason"]


@pytest.mark.parametrize(
    "stdout",
    (
        '{"decision":"maybe","reason":"no"}',
        '{"decision":"approve"}',
        '{"decision":"block","reason":""}',
        "[]",
        "not-json",
        "",
    ),
)
def test_invalid_gate_decision_blocks(capsys, stdout):
    mod = _load_module()
    result = subprocess.CompletedProcess(
        args=["delegate.py"], returncode=0, stdout=stdout, stderr=""
    )

    mod._relay_gate_decision(result)

    decision = json.loads(capsys.readouterr().out)
    assert decision["decision"] == "block"
    assert any(
        code in decision["reason"] for code in ("empty_decision", "invalid_decision")
    )


def test_delegate_import_crash_blocks_without_relaying_stderr(capsys):
    mod = _load_module()
    result = subprocess.CompletedProcess(
        args=["delegate.py"],
        returncode=1,
        stdout="",
        stderr="Traceback: secret-marker import failed",
    )

    mod._relay_gate_decision(result)

    output = capsys.readouterr().out
    decision = json.loads(output)
    assert decision["decision"] == "block"
    assert "delegate_failed" in decision["reason"]
    assert "secret-marker" not in output


@pytest.mark.skipif(shutil.which("jq") is None, reason="launcher dependency jq absent")
def test_missing_managed_interpreter_blocks_then_guarded_followup_approves(tmp_path):
    first = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"}, tmp_path
    )
    first_decision = _decision(first)
    assert first_decision["decision"] == "block"
    assert "interpreter_unavailable" in first_decision["reason"]

    followup = _run_shell({"stop_hook_active": True}, tmp_path)
    assert _decision(followup) == {
        "decision": "approve",
        "reason": "stop-hook-active",
    }


def test_missing_jq_is_a_hard_refusal(tmp_path):
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    result = _run_shell(
        {"stop_hook_active": True},
        tmp_path,
        {"PATH": str(empty_path)},
    )
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "jq_unavailable" in decision["reason"]


@pytest.mark.skipif(shutil.which("jq") is None, reason="launcher dependency jq absent")
def test_launcher_rejects_invalid_python_decision(tmp_path):
    runtime = tmp_path / ".claude" / ".venv" / "bin" / "python"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("#!/bin/sh\nprintf '%s\\n' 'not-json'\n", encoding="utf-8")
    runtime.chmod(0o755)

    result = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"}, tmp_path
    )
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "invalid_decision" in decision["reason"]
