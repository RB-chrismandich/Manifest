"""Strict JSON fallback coverage for the Stop review gate."""

from __future__ import annotations

import pytest

from tests.python.test_stop_gate_hook import (
    _decision,
    _path_without,
    _run_launcher_raw,
    _run_shell,
)


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
    assert _decision(nested)["reason"] == "gate disabled"


def test_missing_parsers_follow_final_duplicate_guard_value(tmp_path):
    result = _run_launcher_raw(
        '{"stop_hook_active":true,"stop_hook_active":false}',
        tmp_path,
        {"PATH": _path_without(tmp_path, "jq", "python3")},
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
