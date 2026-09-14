"""Malformed records and missing IDs cannot corrupt dispatch usage accounting."""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "configs/claude/scripts"


@pytest.fixture(params=["subagent_breakdown", "opus_attribution_report"])
def report(request, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        request.param, SCRIPTS / f"{request.param}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fold(module, records):
    output = {}
    function = getattr(module, "fold", None) or module.fold_file
    function(
        io.StringIO("\n".join(map(json.dumps, records))), "fixture", output, None, None
    )
    return output


def test_missing_ids_do_not_collapse_distinct_records(report):
    rows = [
        {
            "type": "assistant",
            "message": {"model": "fixture-model", "usage": {"input_tokens": n}},
        }
        for n in (10, 20)
    ]
    result = fold(report, rows)
    assert len(result) == 2
    assert sum(entry["input"] for entry in result.values()) == 30


@pytest.mark.parametrize(
    "record",
    [
        ["assistant"],
        {"type": "assistant", "message": []},
        {"type": "assistant", "message": {"usage": {"input_tokens": -1}}},
        {"type": "assistant", "message": {"usage": {"output_tokens": "bad"}}},
    ],
)
def test_malformed_records_are_skipped_with_diagnostic(report, record, capsys):
    assert fold(report, [record]) == {}
    assert "skipped" in capsys.readouterr().err


def test_hook_preserves_process_default_and_force(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "deliberate-model")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "subagent_model_default.py")],
        input='{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose"}}',
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_malformed_input_is_observable_without_blocking(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setenv("HOME", str(tmp_path))
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "subagent_model_default.py")],
        input="private malformed task",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert "fail-open" in result.stderr
    assert "private malformed task" not in result.stderr


def test_hook_alternate_config_directory_preserves_frontmatter_pin(
    tmp_path, monkeypatch
):
    import subprocess

    monkeypatch.setenv("HOME", str(tmp_path / "unused"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    agents = tmp_path / "config/agents"
    agents.mkdir(parents=True)
    (agents / "reviewer.md").write_text("---\nname: reviewer\nmodel: opus\n---\n")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "subagent_model_default.py")],
        input='{"tool_name":"Agent","tool_input":{"subagent_type":"reviewer"}}',
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "message", [{"model": []}, {"content": 42}, {"content": [{"type": []}]}]
)
def test_malformed_model_or_content_cannot_crash_tallies(report, message, capsys):
    message["usage"] = {"input_tokens": 1}
    assert fold(report, [{"type": "assistant", "message": message}]) == {}
    assert "skipped" in capsys.readouterr().err


def test_deployed_hook_cannot_override_unknown_native_pins(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_SUBAGENT_MODEL", raising=False)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "subagent_model_default.py"),
            "--native-default-only",
        ],
        input='{"tool_name":"Agent","tool_input":{"subagent_type":"managed-security-reviewer"}}',
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert "native default unobserved" in result.stderr
