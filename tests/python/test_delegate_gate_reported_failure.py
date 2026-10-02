#!/usr/bin/env python3
"""Gate decision when the reviewer reports outcome=failure alongside findings.

Codex read the unqualified `outcome` enum as "did the diff pass review" and
returned outcome=failure with valid blocking findings. The worker classified
that as malformed output and discarded it, so the gate reported
`backend_error` and the findings never reached the developer.

Run with: PYTHONNOUSERSITE=1 uv run pytest tests/python/test_delegate_gate_reported_failure.py -q
"""

import json

from _delegate_inproc import _valid_backend, delegate


class _GateArgs:
    transcript = ""
    stop_hook_active = False
    json = False


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


def _run_with_backend_output(tmp_path, monkeypatch, raw_output):
    monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
    monkeypatch.setattr(
        delegate.review, "assemble_review_diff", lambda *_args, **_kwargs: "d\n"
    )
    monkeypatch.setattr(
        delegate.process,
        "_spawn_backend",
        lambda *_args, **_kwargs: (0, raw_output, None, False, None),
    )
    args = _GateArgs()
    args.transcript = _edit_transcript(tmp_path)
    return delegate.cmd_gate(
        args,
        [_valid_backend("codex")],
        {"review_gate": {"enabled": True, "backend": "codex"}},
        set(),
    )


def _envelope(outcome, findings):
    return (
        "```json\n"
        + json.dumps(
            {
                "backend": "codex",
                "model": "gpt-5",
                "outcome": outcome,
                "attempted": "reviewed the diff",
                "changes": [],
                "succeeded": [],
                "failed": [],
                "follow_ups": [],
                "findings": findings,
            }
        )
        + "\n```\n"
    )


def test_reported_failure_with_findings_blocks_on_the_findings(
    tmp_path, monkeypatch, capsys
):
    finding = {"severity": "high", "text": "grader rewards a broken fix"}
    rc = _run_with_backend_output(
        tmp_path, monkeypatch, _envelope("failure", [finding])
    )

    assert rc == 0
    decision = json.loads(capsys.readouterr().out)
    assert decision["decision"] == "block"
    assert "grader rewards a broken fix" in decision["reason"]
    assert "backend_error" not in decision["reason"]


def test_reported_failure_without_findings_stays_fail_closed(
    tmp_path, monkeypatch, capsys
):
    rc = _run_with_backend_output(tmp_path, monkeypatch, _envelope("failure", []))

    assert rc == 0
    decision = json.loads(capsys.readouterr().out)
    assert decision["decision"] == "block"
    assert "could not verify" in decision["reason"]


def test_prompt_defines_outcome_as_review_completion():
    instructions = delegate.gate._GATE_PROMPT_INSTRUCTIONS
    assert '"outcome" describes whether YOUR REVIEW RUN completed' in instructions
    assert 'Never use "failure" to report defects' in instructions
