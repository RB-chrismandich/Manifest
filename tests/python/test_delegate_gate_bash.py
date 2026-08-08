#!/usr/bin/env python3
"""Gate detection of shell-mediated edits (Codex round-10 finding).

The edit-tool allowlist misses changes made via Bash (sed -i, redirection,
formatters). The gate now also reviews when the finishing turn used Bash AND the
working tree has a pending diff — without over-triggering on a Bash turn that
changed nothing. Own module (test_delegate_gate_block.py is at the 500-line
ceiling).

Run with: uv run --project configs/claude pytest tests/python/test_delegate_gate_bash.py -q
"""

import json
import subprocess

from _delegate_inproc import _valid_backend, delegate


class _GateArgs:
    transcript = ""
    stop_hook_active = False
    json = False


def _bash_transcript(tmp_path):
    """A finishing turn whose only tool_use is Bash (no dedicated edit tool)."""
    path = tmp_path / "transcript.jsonl"
    lines = [
        {"type": "user", "message": {"role": "user", "content": "run a script"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "Bash", "input": {}}],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return str(path)


def _gate_setup(tmp_path, monkeypatch):
    monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
    monkeypatch.setattr(
        delegate.review, "assemble_review_diff", lambda scope, base, cwd=None: "d\n"
    )


def _run_gate(transcript):
    args = _GateArgs()
    args.transcript = transcript
    args.json = True  # emit a {"decision": ...} line for both allow and block
    return delegate.cmd_gate(
        args,
        [_valid_backend("codex")],
        {"review_gate": {"enabled": True, "backend": "codex"}},
        set(),
    )


def test_bash_turn_with_pending_diff_runs_the_gate(tmp_path, monkeypatch, capsys):
    """Codex HIGH: a finishing turn that changed files only via Bash (here an
    untracked file in a real git repo) must NOT bypass the gate. With Bash used
    and a non-empty working tree, the gate runs and can block."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "shell_made.txt").write_text("written by a shell command\n")
    _gate_setup(tmp_path, monkeypatch)
    raw_output = (
        "```json\n"
        '{"backend": "codex", "model": "gpt-5", "outcome": "success",\n'
        ' "attempted": "reviewed diff", "changes": [], "succeeded": [],\n'
        ' "failed": [], "follow_ups": [],\n'
        ' "findings": [{"severity": "high", "text": "shell edit introduced a bug"}]}\n'
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
    rc = _run_gate(_bash_transcript(tmp_path))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out.get("decision") == "block", "Bash-mediated change bypassed the gate"
    assert "shell edit" in out["reason"].lower()


def test_bash_turn_with_clean_tree_still_allows(tmp_path, monkeypatch, capsys):
    """No over-trigger: a Bash turn whose working tree is clean allows with
    'no code edits' and never reaches the backend. `_working_tree_has_changes`
    is forced False here so the test asserts the gate's decision logic directly,
    independent of what test scaffolding (transcript, job dir) leaves in cwd or
    whether a backend binary is installed."""
    _gate_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        delegate.gate, "_working_tree_has_changes", lambda cwd=None: False
    )
    rc = _run_gate(_bash_transcript(tmp_path))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert '"decision": "block"' not in json.dumps(out)
    assert out.get("reason") == "no code edits" or "no code edits" in json.dumps(out)
