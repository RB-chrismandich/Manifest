"""Strict JSON fallback coverage for the Stop review gate."""

import json
import os
import subprocess
import sys

import pytest

from tests.python.test_stop_gate_hook import (
    PLUGIN_ROOT,
    SCRIPT,
    SHELL,
    _decision,
    _path_without,
    _run_launcher_raw,
    _run_shell,
)


def _run_without_home(tmp_path, extra_env):
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"HOME", "XDG_CONFIG_HOME", "MANIFEST_CONFIG_DIR"}
    }
    environment.update(CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT), **extra_env)
    payload = {"hook_event_name": "Stop", "transcript_path": "/missing.jsonl"}
    return subprocess.run(
        ["/bin/sh", str(SHELL)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
        cwd=tmp_path,
    )


def test_unavailable_home_fails_closed(tmp_path):
    """With no HOME and no explicit config root the gate's location is
    unknowable, so an enabled gate must never be skipped as disabled."""
    decision = _decision(_run_without_home(tmp_path, {}))
    assert decision["decision"] == "block"
    assert "home_unavailable" in decision["reason"]


def test_explicit_config_root_works_without_home(tmp_path):
    """An explicit MANIFEST_CONFIG_DIR still decides the gate without HOME."""
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.json").write_text(
        '{"review_gate":{"enabled":false}}', encoding="utf-8"
    )
    result = _run_without_home(tmp_path, {"MANIFEST_CONFIG_DIR": str(config_dir)})
    assert _decision(result) == {"decision": "approve", "reason": "gate disabled"}


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


def test_missing_jq_and_python_approves_only_top_level_guard(tmp_path):
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
    assert _decision(result) == {"decision": "approve", "reason": "stop-hook-active"}

    nested = _run_shell(
        {"hook_event_name": "Stop", "metadata": {"stop_hook_active": True}},
        tmp_path,
        {"PATH": no_parser_path},
    )
    # With no parser available the non-guard payload is unverifiable, so the
    # disabled gate fails closed instead of approving like the jq path.
    nested_decision = _decision(nested)
    assert nested_decision["decision"] == "block"
    assert "invalid_input" in nested_decision["reason"]


def test_missing_parsers_follow_final_duplicate_guard_value(tmp_path):
    result = _run_launcher_raw(
        '{"stop_hook_active":true,"stop_hook_active":false}',
        tmp_path,
        {"PATH": _path_without(tmp_path, "jq", "python3")},
    )
    # The awk guard sees the final value is not `true`, so the payload is not
    # a guarded follow-up; with no parser left it is unverifiable and blocks.
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "invalid_input" in decision["reason"]


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
def test_missing_parsers_block_malformed_guard_payload(tmp_path, payload: str) -> None:
    config_dir = tmp_path / "delegate-config"
    config_dir.mkdir()
    (config_dir / "delegation.json").write_text(
        '{"review_gate":{"enabled":true}}', encoding="utf-8"
    )
    result = _run_launcher_raw(
        payload,
        tmp_path,
        {
            "MANIFEST_CONFIG_DIR": str(config_dir),
            "PATH": _path_without(tmp_path, "jq", "python3"),
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


@pytest.mark.parametrize(
    ("stdin_text", "expected"),
    [
        ('{"some_field":1}', "not_stop_event"),
        ('{"hook_event_name":"Stop"}', "missing_transcript"),
        (
            '{"hook_event_name":"Stop","transcript_path":"/missing.jsonl"}',
            None,
        ),
    ],
)
def test_no_jq_disabled_gate_applies_stop_contract(
    tmp_path, stdin_text: str, expected: str | None
) -> None:
    """With jq gone the disabled gate must enforce the same object/event/
    transcript contract as the jq path — via the python3 fallback parser."""
    result = _run_launcher_raw(
        stdin_text,
        tmp_path,
        {"PATH": _path_without(tmp_path, "jq")},
    )
    decision = _decision(result)
    if expected is None:
        assert decision == {"decision": "approve", "reason": "gate disabled"}
    else:
        assert decision["decision"] == "block"
        assert expected in decision["reason"]


@pytest.mark.parametrize(
    "stdin_text",
    [
        '{"some_field":1}',
        '{"hook_event_name":"Stop"}',
        '{"hook_event_name":"Stop","transcript_path":"/missing.jsonl"}',
    ],
)
def test_no_jq_no_python_disabled_gate_fails_closed(tmp_path, stdin_text: str) -> None:
    """With neither jq nor python3, the disabled gate cannot verify the input
    at all and must fail closed — even for a payload that would be valid."""
    result = _run_launcher_raw(
        stdin_text,
        tmp_path,
        {"PATH": _path_without(tmp_path, "jq", "python3")},
    )
    decision = _decision(result)
    assert decision["decision"] == "block"
    assert "invalid_input" in decision["reason"]
