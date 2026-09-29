"""Tests for the fail-closed Stop-hook wrapper and POSIX launcher."""

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
    # Isolate delegation-config discovery so host config can never leak in.
    environment.setdefault("MANIFEST_CONFIG_DIR", str(home / "no-config-dir"))
    environment.setdefault("XDG_CONFIG_HOME", str(home / "xdg-config"))
    return subprocess.run(
        ["/bin/sh", str(SHELL)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )


def _path_without(tmp_path, *excluded):
    """Return a PATH that resolves every launcher tool except exclusions."""
    shim = tmp_path / "filtered-path"
    shim.mkdir()
    seen = set(excluded)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not os.path.isdir(entry):
            continue
        for name in os.listdir(entry):
            if name in seen:
                continue
            source = os.path.join(entry, name)
            if os.path.isfile(source) and os.access(source, os.X_OK):
                seen.add(name)
                os.symlink(source, shim / name)
    return str(shim)


def _path_without_jq(tmp_path):
    return _path_without(tmp_path, "jq")


def _run_launcher_raw(
    stdin_text: str, home: pathlib.Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    environment = dict(
        os.environ,
        HOME=str(home),
        CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT),
    )
    environment.update(extra_env or {})
    return subprocess.run(
        ["/bin/sh", str(SHELL)],
        input=stdin_text,
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
def test_disabled_gate_approves_without_managed_interpreter(tmp_path):
    """Plugin-only installs have no ~/.claude/.venv; a disabled gate approves."""
    result = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"}, tmp_path
    )
    assert _decision(result) == {
        "decision": "approve",
        "reason": "gate disabled",
    }


@pytest.mark.skipif(shutil.which("jq") is None, reason="launcher dependency jq absent")
def test_disabled_gate_rejects_non_stop_event(tmp_path):
    """A disabled gate must not approve arbitrary objects that are not Stop events."""
    result = _run_shell(
        {"some_field": 1, "transcript_path": "/missing.jsonl"}, tmp_path
    )
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "not_stop_event" in decision["reason"]


@pytest.mark.skipif(shutil.which("jq") is None, reason="launcher dependency jq absent")
def test_disabled_gate_rejects_stop_without_transcript(tmp_path):
    """A Stop event with no usable transcript is malformed and stays fail-closed."""
    result = _run_shell({"hook_event_name": "Stop"}, tmp_path)
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "missing_transcript" in decision["reason"]


@pytest.mark.skipif(shutil.which("jq") is None, reason="launcher dependency jq absent")
def test_disabled_gate_approves_explicit_disabled_config(tmp_path):
    """An explicit `review_gate.enabled: false` approves a genuine Stop event."""
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.json").write_text(
        json.dumps({"review_gate": {"enabled": False}}), encoding="utf-8"
    )
    result = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"},
        tmp_path,
        {"MANIFEST_CONFIG_DIR": str(config_dir)},
    )
    assert _decision(result) == {
        "decision": "approve",
        "reason": "gate disabled",
    }


@pytest.mark.skipif(shutil.which("jq") is None, reason="launcher dependency jq absent")
def test_missing_managed_interpreter_blocks_then_guarded_followup_approves(tmp_path):
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.json").write_text(
        json.dumps({"review_gate": {"enabled": True}}), encoding="utf-8"
    )
    env = {"MANIFEST_CONFIG_DIR": str(config_dir)}
    first = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"},
        tmp_path,
        env,
    )
    first_decision = _decision(first)
    assert first_decision["decision"] == "block"
    assert "interpreter_unavailable" in first_decision["reason"]

    followup = _run_shell({"stop_hook_active": True}, tmp_path, env)
    assert _decision(followup) == {
        "decision": "approve",
        "reason": "stop-hook-active",
    }


@pytest.mark.skipif(shutil.which("jq") is None, reason="launcher dependency jq absent")
def test_yaml_config_falls_through_to_managed_runtime(tmp_path):
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.yml").write_text(
        "review_gate:\n  enabled: false\n", encoding="utf-8"
    )
    env = {"MANIFEST_CONFIG_DIR": str(config_dir)}
    result = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"},
        tmp_path,
        env,
    )
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "interpreter_unavailable" in decision["reason"]


@pytest.mark.skipif(shutil.which("jq") is None, reason="launcher dependency jq absent")
def test_unparseable_json_config_fails_closed(tmp_path):
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.json").write_text("{not json", encoding="utf-8")
    env = {"MANIFEST_CONFIG_DIR": str(config_dir)}
    result = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"},
        tmp_path,
        env,
    )
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "config_unparseable" in decision["reason"]


def test_missing_jq_and_python_approves_only_top_level_guard(tmp_path):
    """The fallback parser accepts a normal Stop payload, never nested metadata."""
    no_parser_path = _path_without(tmp_path, "jq", "python3")
    result = _run_shell(
        {
            "stop_hook_active": True,
            "hook_event_name": "Stop",
            "transcript_path": "/missing.jsonl",
        },
        tmp_path,
        {"PATH": no_parser_path},
    )
    assert _decision(result) == {
        "decision": "approve",
        "reason": "stop-hook-active",
    }

    nested = _run_shell(
        {"hook_event_name": "Stop", "metadata": {"stop_hook_active": True}},
        tmp_path,
        {"PATH": no_parser_path},
    )
    assert _decision(nested)["reason"] == "gate disabled"


def test_missing_parsers_follow_final_duplicate_guard_value(tmp_path):
    no_parser_path = _path_without(tmp_path, "jq", "python3")
    result = _run_launcher_raw(
        '{"stop_hook_active":true,"stop_hook_active":false}',
        tmp_path,
        {"PATH": no_parser_path},
    )
    assert _decision(result)["reason"] == "gate disabled"



@pytest.mark.parametrize(
    "payload",
    [
        '{"stop_hook_active":true,',
        '{"stop_hook_active":true, garbage}',
        '{"stop_hook_active" true}',
        '{"x":1,,"stop_hook_active":true}',
        '{:1,"stop_hook_active":true}',
        '{"x""stop_hook_active":true}',
        r'{"x":"\q","stop_hook_active":true}',
        '{"x":"line\nbreak","stop_hook_active":true}',
        '{"stop_hook_active":t r u e}',
        '{"x":"raw\ttab","stop_hook_active":true}',
        '{"x":NaN,"stop_hook_active":true}',
    ],
)
def test_missing_parsers_block_malformed_guard_payload(
    tmp_path, payload: str
) -> None:
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.json").write_text(
        '{"review_gate":{"enabled":true}}', encoding="utf-8"
    )
    no_parser_path = _path_without(tmp_path, "jq", "python3")
    result = _run_launcher_raw(
        payload,
        tmp_path,
        {
            "MANIFEST_CONFIG_DIR": str(config_dir),
            "PATH": no_parser_path,
        },
    )
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "jq_unavailable" in decision["reason"]



def test_missing_jq_python_rejects_non_json_constant_with_enabled_gate(tmp_path):
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.json").write_text(
        '{"review_gate":{"enabled":true}}', encoding="utf-8"
    )
    result = _run_launcher_raw(
        '{"x":NaN,"stop_hook_active":true}',
        tmp_path,
        {
            "MANIFEST_CONFIG_DIR": str(config_dir),
            "PATH": _path_without(tmp_path, "jq"),
        },
    )
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "jq_unavailable" in decision["reason"]

def test_missing_jq_disabled_gate_fails_open(tmp_path):
    """jq is an optional bootstrap dependency: without it, the default-disabled
    gate approves rather than trapping the session in a block loop."""
    no_jq_path = _path_without_jq(tmp_path)
    for payload in (
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"},
        {"stop_hook_active": False, "hook_event_name": "Stop"},
    ):
        result = _run_shell(payload, tmp_path, {"PATH": no_jq_path})
        assert _decision(result) == {
            "decision": "approve",
            "reason": "gate disabled",
        }


@pytest.mark.parametrize("config", [{}, {"review_gate": {"enabled": False}}])
def test_missing_jq_disabled_json_config_fails_open(tmp_path, config):
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.json").write_text(json.dumps(config), encoding="utf-8")

    result = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"},
        tmp_path,
        {
            "PATH": _path_without_jq(tmp_path),
            "MANIFEST_CONFIG_DIR": str(config_dir),
        },
    )

    assert _decision(result) == {
        "decision": "approve",
        "reason": "gate disabled",
    }


def test_missing_jq_malformed_json_config_uses_disabled_default(tmp_path):
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.json").write_text(
        json.dumps({"review_gate": "enabled"}), encoding="utf-8"
    )

    result = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"},
        tmp_path,
        {
            "PATH": _path_without_jq(tmp_path),
            "MANIFEST_CONFIG_DIR": str(config_dir),
        },
    )

    assert _decision(result) == {
        "decision": "approve",
        "reason": "gate disabled",
    }


def test_missing_jq_enabled_yaml_config_blocks(tmp_path):
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.yml").write_text(
        "review_gate:\n  enabled: true\n", encoding="utf-8"
    )

    result = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"},
        tmp_path,
        {
            "PATH": _path_without_jq(tmp_path),
            "MANIFEST_CONFIG_DIR": str(config_dir),
        },
    )

    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "jq_unavailable" in decision["reason"]


def test_missing_jq_configured_gate_blocks_once_then_guard_frees_session(tmp_path):
    """A configured gate stays fail-closed when jq is missing, but exactly one
    block — the parsed recursion guard approves the follow-up so the session
    is never trapped, matching the interpreter_unavailable contract."""
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.json").write_text(
        json.dumps({"review_gate": {"enabled": True}}), encoding="utf-8"
    )
    env = {"PATH": _path_without_jq(tmp_path), "MANIFEST_CONFIG_DIR": str(config_dir)}

    first = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"},
        tmp_path,
        env,
    )
    first_decision = _decision(first)
    assert first_decision["decision"] == "block"
    assert "jq_unavailable" in first_decision["reason"]

    nested = _run_shell({"metadata": {"stop_hook_active": True}}, tmp_path, env)
    nested_decision = _decision(nested)
    assert nested_decision["decision"] == "block"
    assert "jq_unavailable" in nested_decision["reason"]

    followup = _run_shell({"stop_hook_active": True}, tmp_path, env)
    assert _decision(followup) == {
        "decision": "approve",
        "reason": "stop-hook-active",
    }


@pytest.mark.skipif(shutil.which("jq") is None, reason="launcher dependency jq absent")
@pytest.mark.parametrize(
    "raw", ["true", "false", "1", '"true"', "[]", "[true]", "null"]
)
def test_launcher_never_treats_non_object_payload_as_recursion_guard(tmp_path, raw):
    result = _run_launcher_raw(raw, tmp_path)
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "invalid_input" in decision["reason"]


@pytest.mark.skipif(shutil.which("jq") is None, reason="launcher dependency jq absent")
def test_launcher_rejects_string_stop_hook_active_flag(tmp_path):
    result = _run_launcher_raw(json.dumps({"stop_hook_active": "true"}), tmp_path)
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert decision["reason"] != "stop-hook-active"


@pytest.mark.skipif(shutil.which("jq") is None, reason="launcher dependency jq absent")
def test_launcher_rejects_invalid_python_decision(tmp_path):
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.json").write_text(
        json.dumps({"review_gate": {"enabled": True}}), encoding="utf-8"
    )
    runtime = tmp_path / ".claude" / ".venv" / "bin" / "python"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("#!/bin/sh\nprintf '%s\\n' 'not-json'\n", encoding="utf-8")
    runtime.chmod(0o755)

    result = _run_shell(
        {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"},
        tmp_path,
        {"MANIFEST_CONFIG_DIR": str(config_dir)},
    )
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "invalid_decision" in decision["reason"]
