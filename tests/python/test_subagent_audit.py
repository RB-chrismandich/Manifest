"""Audit completeness must survive missing, malformed and historical evidence."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "configs/claude/scripts"
SINCE = "2026-09-01T00:00:00Z"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
    root = tmp_path / "projects"
    root.mkdir()
    return root


def dispatch(
    root, name="a", *, model="sonnet", served="claude-sonnet-5", channel="agent-tool"
):
    directory = root / "project/session/subagents"
    if channel == "workflow":
        directory /= "workflows/run"
    directory.mkdir(parents=True, exist_ok=True)
    meta = {
        "agentType": "general-purpose",
        "model": model,
        "description": "PRIVATE TASK TEXT",
    }
    path = directory / f"agent-{name}.meta.json"
    path.write_text(json.dumps(meta))
    record = {
        "type": "assistant",
        "timestamp": "2026-09-02T00:00:00Z",
        "message": {"model": served},
    }
    path.with_name(f"agent-{name}.jsonl").write_text(json.dumps(record) + "\n")
    return path


def audit(root, *args):
    output = root.parent / "audit.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "subagent_breakdown.py"),
            "--audit",
            "--root",
            str(root),
            "--since",
            SINCE,
            "--json",
            str(output),
            *args,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    return result, json.loads(output.read_text()) if output.exists() else {}


def test_empty_is_unobserved_not_one_hundred_percent(corpus):
    result, report = audit(corpus)
    assert result.returncode == 2
    assert report["status"] == "incomplete"
    assert "100.0%" not in result.stdout


@pytest.mark.parametrize(
    "damage",
    [
        "missing-meta",
        "missing-transcript",
        "bad-meta",
        "bad-record",
        "unknown-model",
        "no-time",
    ],
)
def test_damaged_evidence_never_disappears_into_success(corpus, damage):
    path = dispatch(corpus)
    transcript = path.with_name("agent-a.jsonl")
    if damage == "missing-meta":
        path.unlink()
    elif damage == "missing-transcript":
        transcript.unlink()
    elif damage == "bad-meta":
        path.write_text("[]")
    elif damage == "bad-record":
        transcript.write_text('{"type":"assistant","message":[]}\n')
    elif damage == "unknown-model":
        dispatch(corpus, served="unknown-future-model")
    else:
        transcript.write_text(
            '{"type":"assistant","message":{"model":"claude-sonnet-5"}}\n'
        )
    result, report = audit(corpus)
    assert result.returncode == 2
    assert report["status"] == "incomplete"
    assert "Traceback" not in result.stderr


def test_current_frontmatter_cannot_certify_a_historical_request(corpus):
    path = dispatch(corpus, model=None, served="claude-opus-5")
    meta = json.loads(path.read_text())
    meta["agentType"] = "verifier"
    path.write_text(json.dumps(meta))
    definitions = Path(os.environ["CLAUDE_PROJECT_DIR"]) / ".claude/agents"
    definitions.mkdir(parents=True)
    definitions.joinpath("verifier.md").write_text(
        "---\nname: verifier\nmodel: opus\n---\n"
    )
    result, report = audit(corpus)
    assert result.returncode == 2
    row = report["records"][0]
    assert row["requested"] is None
    assert row["resolved"] is None
    assert row["served"] == ["claude-opus-5"]


def test_requested_pin_is_not_proof_of_served_model(corpus):
    dispatch(corpus, model="sonnet", served="claude-opus-5")
    result, report = audit(corpus)
    assert (
        result.returncode == 2
    )  # substitution/override needs investigation, not silent approval
    assert report["records"][0]["status"] == "model-mismatch"


def test_channels_and_unknowns_are_in_json_even_outside_scope(corpus):
    dispatch(corpus)
    dispatch(corpus, "w", model=None, served="claude-opus-5", channel="workflow")
    result, report = audit(corpus)
    assert result.returncode == 0  # explicitly scoped to observed Agent traffic
    assert report["coverage"]["workflow"]["observed"] == 1
    assert report["coverage"]["workflow"]["audited"] is False
    for channel in ("fork", "teams", "external-cli", "unknown"):
        assert channel in report["coverage"]
    assert report["coverage"]["teams"]["status"] == "unsupported"
    assert "PRIVATE TASK TEXT" not in json.dumps(report) + result.stdout


def test_fork_does_not_inflate_pin_compliance(corpus):
    path = dispatch(corpus, model=None, served="claude-opus-5")
    path.write_text('{"agentType":"fork"}')
    result, report = audit(corpus, "--channel", "all")
    assert result.returncode == 2
    assert report["pinned"] == 0
    assert report["coverage"]["fork"]["observed"] == 1


def test_inherit_sentinel_does_not_inflate_pin_compliance(corpus):
    dispatch(corpus, model="inherit", served="claude-sonnet-5")
    result, report = audit(corpus)
    assert result.returncode == 0
    assert report["records"][0]["status"] == "observed"
    assert report["pinned"] == 0


def test_channel_with_only_incomplete_evidence_is_not_observed(corpus):
    dispatch(corpus)
    path = dispatch(corpus, "w", channel="workflow")
    path.with_name("agent-w.jsonl").unlink()
    result, report = audit(corpus, "--channel", "all")
    assert result.returncode == 2
    assert report["coverage"]["workflow"]["status"] == "unobserved"
    assert report["coverage"]["workflow"]["observed"] == 0


def test_until_and_invalid_windows_are_honored(corpus):
    dispatch(corpus)
    result, report = audit(corpus, "--until", "2026-09-01T12:00:00Z")
    assert result.returncode == 2
    assert report["dispatches"] == 0
    result, _ = audit(corpus, "--until", "2026-08-01T00:00:00Z")
    assert result.returncode == 2


def test_audit_output_limit_preserves_full_counts(corpus):
    for index in range(8):
        dispatch(corpus, str(index))
    result, report = audit(corpus, "--limit", "2")
    assert result.returncode == 0
    assert report["dispatches"] == 8
    assert len(report["records"]) == 2
    assert report["omitted_records"] == 6


def test_source_pricing_wins_over_ambient_deployed_module(corpus):
    scripts = Path(os.environ["HOME"]) / ".claude/scripts"
    scripts.mkdir(parents=True)
    scripts.joinpath("model_pricing.py").write_text(
        "raise RuntimeError('ambient import')\n"
    )
    dispatch(corpus)
    result, _ = audit(corpus)
    assert result.returncode == 0


def test_provenance_detects_stale_deployment_receipt(corpus):
    dispatch(corpus)
    config = corpus.parent / "home/.claude/config"
    config.mkdir(parents=True)
    stamp = config / "deploy_stamp"
    stamp.write_text(
        "head_sha="
        + "a" * 40
        + "\ndeployed_at=2026-09-01T00:00:00Z\nruntime_merge_status=merged\n"
    )
    (config.parent / "settings.json").write_text("{}")
    (config / "runtime_settings_merge.json").write_text(
        json.dumps(
            {"status": "merged", "settings_sha256": "b" * 64, "host_version": "2.1.263"}
        )
    )
    result, report = audit(corpus, "--stamp", str(stamp))
    assert result.returncode == 0  # actual serving evidence is independent
    assert report["provenance"]["repository_revision"] == "a" * 40
    assert report["provenance"]["runtime_merge_status"] == "stale"


def test_saved_report_failure_does_not_print_ok(corpus):
    dispatch(corpus)
    result, _ = audit(corpus, "--json", str(corpus.parent))
    assert result.returncode == 2
    assert "OK —" not in result.stdout
