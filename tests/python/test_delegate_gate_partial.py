#!/usr/bin/env python3
"""Gate decision on a `partial`-outcome review (Codex round-8 false-green).

Kept in its own module because test_delegate_gate_block.py sits at the 500-line
ceiling. Self-contained minimal harness (no cross-file test deps beyond the
shared _delegate_inproc loader).

Run with: uv run --project configs/claude pytest tests/python/test_delegate_gate_partial.py -q
"""

import json

from _delegate_inproc import _valid_backend, delegate


class _GateArgs:
    transcript = ""
    stop_hook_active = False
    json = False


def _edit_transcript(tmp_path):
    path = tmp_path / "transcript.jsonl"
    lines = [
        {"type": "user", "message": {"role": "user", "content": "do a thing"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return str(path)


def test_gate_partial_outcome_empty_findings_is_not_a_clean_pass(
    tmp_path, monkeypatch, capsys
):
    """A backend returning outcome=partial (it could not inspect the whole diff)
    with empty findings must NOT be reported as a clean 'no findings' review.
    The gate fails open (never traps the turn) but its message must flag the
    incomplete coverage — otherwise incomplete review coverage is a false-green."""
    monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
    monkeypatch.setattr(
        delegate.review, "assemble_review_diff", lambda scope, base, cwd=None: "d\n"
    )
    raw_output = (
        "```json\n"
        "{\n"
        '  "backend": "codex", "model": "gpt-5", "outcome": "partial",\n'
        '  "attempted": "reviewed part of the diff", "changes": [],\n'
        '  "succeeded": [], "failed": [], "follow_ups": [], "findings": []\n'
        "}\n"
        "```\n"
    )
    monkeypatch.setattr(
        delegate.process,
        "_spawn_backend",
        lambda entry, argv, prompt_bytes, job_dir, budget, on_pgid=None: (
            0,
            raw_output,
            None,
            False,
            None,
        ),
    )
    args = _GateArgs()
    args.transcript = _edit_transcript(tmp_path)
    rc = delegate.cmd_gate(
        args,
        [_valid_backend("codex")],
        {"review_gate": {"enabled": True, "backend": "codex"}},
        set(),
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert '"decision": "block"' not in json.dumps(out)
    assert "incomplete" in out.get("systemMessage", "").lower(), (
        "partial coverage must be surfaced as incomplete, not a silent clean pass"
    )
