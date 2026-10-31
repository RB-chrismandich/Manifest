"""Synthetic transcript credentials never cross the injected provider seam."""

import json
import os
import sys
from contextlib import suppress
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))
from skillclaw import evolve as ev
from skillclaw import ingest, scrub


def session(text, kind="text"):
    block = {"kind": kind, "text": text}
    if kind == "tool_use":
        block = {"kind": kind, "name": "tool", "input": {"nested": {"password": text}}}
    elif kind == "tool_result":
        block = {"kind": kind, "output": text, "is_error": False}
    return {"session_id": "s", "turns": [{"role": "user", "blocks": [block]}]}


def run_evolve(tmp_path, records, calls):
    root = tmp_path / "sessions"
    root.mkdir(exist_ok=True)
    for index, record in enumerate(records):
        (root / f"{index}.json").write_text(json.dumps(record))
    template = tmp_path / "template"
    template.write_text("{{LIBRARY}}\n{{SESSIONS}}")
    return ev.evolve(
        root,
        tmp_path / "candidates",
        template,
        token_budget=1,
        runner=lambda prompt: calls.append(prompt) or "NO_SKILLS",
    )


@pytest.mark.parametrize("kind", ["text", "thinking", "tool_use", "tool_result"])
def test_structured_credentials_do_not_reach_provider(tmp_path, kind):
    value = "synthetic-" + "credential"[::-1]
    text = value if kind == "tool_use" else json.dumps({"password": value})
    calls = []
    run_evolve(tmp_path, [session(text, kind)], calls)
    assert calls
    assert all(value not in prompt for prompt in calls)


@pytest.mark.parametrize(
    "family", ["cloud", "source-control", "oauth", "cookie", "private-key"]
)
def test_credential_families_do_not_reach_provider(tmp_path, family):
    values = {
        "cloud": "AK" + "IA" + "QWERTYUIOPASDFGH",
        "source-control": "gl" + "pat-" + "AbCdEf0123456789xyZQ",
        "oauth": "gh" + "u_" + "AbCdEf0123456789" * 3,
        "cookie": "Cookie: session=" + "synthetic-session-value",
        "private-key": "-----BEGIN "
        + "RSA PRIVATE KEY-----\n"
        + "synthetic-key-material\n-----END RSA PRIVATE KEY-----",
    }
    calls = []
    with suppress(RuntimeError):
        run_evolve(tmp_path, [session(values[family])], calls)
    assert all(values[family] not in prompt for prompt in calls)


def test_later_chunk_failure_prevents_all_provider_calls(tmp_path):
    calls = []
    with pytest.raises(RuntimeError):
        run_evolve(
            tmp_path,
            [session("ordinary"), session("password = '''\nprivate contents\n'''")],
            calls,
        )
    assert calls == []


def test_missing_detector_prevents_provider_call(tmp_path, monkeypatch):
    commands = tmp_path / "bin"
    commands.mkdir()
    detector = commands / "gitleaks"
    detector.write_text("#!/bin/sh\nexit 127\n")
    detector.chmod(0o755)
    monkeypatch.setenv("PATH", f"{commands}:{os.environ['PATH']}")
    calls = []
    with pytest.raises(RuntimeError):
        run_evolve(tmp_path, [session("ordinary")], calls)
    assert calls == []


def test_ingest_scrubs_before_tool_truncation(tmp_path):
    value = "synthetic-" + "secretvalue"[::-1] * 100
    source = tmp_path / "s.jsonl"
    source.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"password": value},
                        }
                    ],
                },
            }
        )
    )
    record = ingest.parse_transcript(source, max_tool_output_chars=12)
    assert "synthetic-" not in json.dumps(record)


def test_scrub_decodes_json_before_redacting(tmp_path):
    path = tmp_path / "s.json"
    value = "synthetic-" + "credential"[::-1]
    path.write_text(json.dumps(session(json.dumps({"password": value}))))
    assert scrub.scrub_file(path) is True
    assert value not in path.read_text()


def test_clean_sessions_keep_tool_context_and_chunking(tmp_path):
    calls = []
    record = session("ordinary")
    record["turns"][0]["blocks"].append(
        {"kind": "tool_use", "name": "Bash", "input": {"command": "ls"}}
    )
    run_evolve(tmp_path, [record, session("another task")], calls)
    assert len(calls) == 2
    assert "Bash" in calls[0] and "ls" in calls[0]


def test_direct_subprocess_runner_blocks_residual_before_dispatch(monkeypatch):
    from manifest_model_policy import CliRoute

    calls = []
    monkeypatch.setattr(ev, "load_default_policy", lambda: {})
    monkeypatch.setattr(ev, "resolve_cli_route", lambda *a, **k: CliRoute("claude"))
    monkeypatch.setattr(
        ev, "run_headless_prompt", lambda *a, **k: calls.append(a) or "NO_SKILLS"
    )
    with pytest.raises(RuntimeError):
        ev.subprocess_runner("AK" + "IA" + "QWERTYUIOPASDFGH")
    assert calls == []


@pytest.mark.parametrize("source", ["template", "library"])
def test_final_prompt_context_is_also_checked(tmp_path, source):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "s.json").write_text(json.dumps(session("ordinary")))
    template = tmp_path / "template"
    template.write_text("{{LIBRARY}}\n{{SESSIONS}}")
    library = tmp_path / "library"
    (library / "skill").mkdir(parents=True)
    value = "AK" + "IA" + "QWERTYUIOPASDFGH"
    if source == "template":
        template.write_text(value + "\n{{SESSIONS}}")
    else:
        (library / "skill/SKILL.md").write_text(
            "---\nname: skill\ndescription: " + value + "\n---\n"
        )
    calls = []
    with pytest.raises(RuntimeError):
        ev.evolve(
            sessions,
            tmp_path / "out",
            template,
            committed_dir=library,
            runner=lambda prompt: calls.append(prompt) or "NO_SKILLS",
        )
    assert calls == []


@pytest.mark.parametrize("failure", ["timeout", "malformed", "nonzero"])
def test_inconclusive_scan_never_dispatches(tmp_path, monkeypatch, failure):
    import subprocess

    from skillclaw import provider_safety

    def failed(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("gitleaks", 30)
        if failure == "nonzero":
            raise subprocess.CalledProcessError(2, "gitleaks")
        return subprocess.CompletedProcess("gitleaks", 0, stdout="{}")

    monkeypatch.setattr(provider_safety.subprocess, "run", failed)
    calls = []
    with pytest.raises(RuntimeError):
        run_evolve(tmp_path, [session("ordinary")], calls)
    assert calls == []


@pytest.mark.parametrize("operation", ["read_text", "write_text"])
def test_scrub_io_failure_returns_failure_without_content(
    tmp_path, monkeypatch, capsys, operation
):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"password": "synthetic-value"}))
    original = getattr(Path, operation)

    def failed(self, *args, **kwargs):
        if self == path:
            raise PermissionError("synthetic-value")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, operation, failed)
    assert scrub.main([str(tmp_path)]) == 1
    assert "synthetic-value" not in capsys.readouterr().err


def test_scrubbed_json_escapes_cannot_hide_credentials(tmp_path):
    calls = []
    record = session('{"pass\\u0077ord": "synthetic-hidden-value"}')
    run_evolve(tmp_path, [record], calls)
    assert calls and "synthetic-hidden-value" not in calls[0]


def test_retained_transcript_is_scanned_before_truncation(tmp_path):
    source = tmp_path / "s.jsonl"
    value = "AK" + "IA" + "QWERTYUIOPASDFGH"
    source.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "tool_result", "content": value}],
                },
            }
        )
    )
    with pytest.raises(RuntimeError):
        ingest.parse_transcript(source, max_tool_output_chars=5)


@pytest.mark.parametrize("operator", [" + ", " "])
def test_non_json_credential_expression_blocks_all_entry_points(
    tmp_path, monkeypatch, operator
):
    from manifest_model_policy import CliRoute

    text = 'settings = {"password": ""' + operator + '"synthetic-private-value"}'
    source = tmp_path / "s.jsonl"
    source.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": text}})
    )
    with pytest.raises(RuntimeError):
        ingest.parse_transcript(source)
    calls = []
    with pytest.raises(RuntimeError):
        run_evolve(tmp_path, [session(text)], calls)
    monkeypatch.setattr(ev, "load_default_policy", lambda: {})
    monkeypatch.setattr(ev, "resolve_cli_route", lambda *a, **k: CliRoute("claude"))
    monkeypatch.setattr(
        ev, "run_headless_prompt", lambda *a, **k: calls.append(a) or "NO_SKILLS"
    )
    with pytest.raises(RuntimeError):
        ev.subprocess_runner(text)
    assert calls == []


def test_detector_suppressions_do_not_waive_provider_check(tmp_path, monkeypatch):
    monkeypatch.setenv("GITLEAKS_CONFIG_TOML", '[allowlist]\nregexes=[".*"]')
    calls = []
    text = "AK" + "IA" + "QWERTYUIOPASDFGH # gitleaks:allow"
    with pytest.raises(RuntimeError):
        run_evolve(tmp_path, [session(text)], calls)
    assert calls == []
