#!/usr/bin/env python3
"""Fail-closed review-gate infrastructure paths."""

import json

import pytest
from _delegate_inproc import _valid_backend, delegate


class _GateArgs:
    transcript = ""
    stop_hook_active = False
    json = False


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)


def _edit_transcript(tmp_path):
    path = tmp_path / "transcript.jsonl"
    entries = [
        {"type": "user", "message": {"role": "user", "content": "fix"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")
    return str(path)


def _run(transcript):
    args = _GateArgs()
    args.transcript = transcript
    return delegate.cmd_gate(
        args,
        [_valid_backend("codex")],
        {"review_gate": {"enabled": True, "backend": "codex"}},
        set(),
    )


@pytest.mark.parametrize("content", ["", "{not-json}\n", "[]\n"])
def test_empty_or_malformed_transcript_blocks_before_backend(
    tmp_path, monkeypatch, capsys, content
):
    _setup(tmp_path, monkeypatch)
    transcript = tmp_path / "bad.jsonl"
    transcript.write_text(content, encoding="utf-8")

    assert _run(str(transcript)) == 0

    decision = json.loads(capsys.readouterr().out)
    assert decision["decision"] == "block"
    assert "transcript_unreadable" in decision["reason"]


def test_prompt_construction_failure_blocks_without_detail_leak(
    tmp_path, monkeypatch, capsys
):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        delegate.review,
        "assemble_review_diff",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            delegate.review.ReviewDiffError("secret diff failure")
        ),
    )

    assert _run(_edit_transcript(tmp_path)) == 0

    output = capsys.readouterr().out
    decision = json.loads(output)
    assert decision["decision"] == "block"
    assert "prompt_unavailable" in decision["reason"]
    assert "secret diff failure" not in output


def test_unexpected_backend_exception_blocks_without_detail_leak(
    tmp_path, monkeypatch, capsys
):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        delegate.review, "assemble_review_diff", lambda *_args, **_kwargs: "d\n"
    )
    monkeypatch.setattr(
        delegate.worker,
        "_run_backend_and_finish",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("secret backend failure")
        ),
    )

    assert _run(_edit_transcript(tmp_path)) == 0

    output = capsys.readouterr().out
    decision = json.loads(output)
    assert decision["decision"] == "block"
    assert "gate_execution_failed" in decision["reason"]
    assert "secret backend failure" not in output


def test_invalid_findings_block_as_unverified_review(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        delegate.review, "assemble_review_diff", lambda *_args, **_kwargs: "d\n"
    )
    monkeypatch.setattr(
        delegate.worker,
        "_run_backend_and_finish",
        lambda *_args, **_kwargs: {
            "state": "completed",
            "envelope": {"outcome": "success", "findings": "not-a-list"},
        },
    )

    assert _run(_edit_transcript(tmp_path)) == 0

    decision = json.loads(capsys.readouterr().out)
    assert decision["decision"] == "block"
    assert "invalid_review" in decision["reason"]


def test_backend_that_cannot_guarantee_read_only_review_is_unavailable(
    tmp_path, monkeypatch, capsys
):
    _setup(tmp_path, monkeypatch)
    backend = _valid_backend("remote")
    backend["execution"] = {"read_only": False}
    args = _GateArgs()
    args.transcript = _edit_transcript(tmp_path)

    assert (
        delegate.cmd_gate(
            args,
            [backend],
            {"review_gate": {"enabled": True, "backend": "remote"}},
            set(),
        )
        == 0
    )

    decision = json.loads(capsys.readouterr().out)
    assert decision["decision"] == "block"
    assert "backend_unavailable" in decision["reason"]
