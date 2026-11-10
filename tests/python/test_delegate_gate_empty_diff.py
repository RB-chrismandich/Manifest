#!/usr/bin/env python3
"""Review gate: an edit-tool turn whose assembled diff is empty.

Edit tools can run without leaving anything for git to show (edits reverted,
git-ignored, or outside the repository). The gate then approves with
"no code edits" instead of dispatching a reviewer with nothing to review.
Own module (test_delegate_gate_block.py is at the 500-line ceiling).

Run with: uv run pytest tests/python/test_delegate_gate_empty_diff.py -q
"""

import json
import subprocess

import pytest
from _delegate_inproc import _valid_backend, delegate

_NO_CODE_EDITS = {"decision": "approve", "reason": "no code edits"}


class _GateArgs:
    transcript = ""
    stop_hook_active = False
    json = True


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


def _clean_repo(tmp_path):
    """A committed repository on `main` with a clean working tree."""
    repo = tmp_path / "repo"
    repo.mkdir()
    for argv in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@example.com"],
        ["git", "config", "user.name", "t"],
        ["git", "config", "commit.gpgsign", "false"],
    ):
        subprocess.run(argv, cwd=repo, check=True)
    (repo / "a.txt").write_text("one\n")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


def _setup(tmp_path, monkeypatch, cwd):
    monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)


def _run(transcript):
    args = _GateArgs()
    args.transcript = transcript
    return delegate.cmd_gate(
        args,
        [_valid_backend("codex")],
        {"review_gate": {"enabled": True, "backend": "codex"}},
        set(),
    )


def _forbid_dispatch(*_args, **_kwargs):
    raise AssertionError("gate dispatched a review for an empty diff")


@pytest.mark.parametrize("diff", ["", "\n", " \n\t\n"])
def test_edit_turn_with_empty_assembled_diff_approves_as_no_code_edits(
    tmp_path, monkeypatch, capsys, diff
):
    _setup(tmp_path, monkeypatch, tmp_path)
    monkeypatch.setattr(
        delegate.review, "assemble_review_diff", lambda scope, base, cwd=None: diff
    )
    monkeypatch.setattr(delegate.gate, "_gate_execute", _forbid_dispatch)

    assert _run(_edit_transcript(tmp_path)) == 0

    assert json.loads(capsys.readouterr().out) == _NO_CODE_EDITS


def test_edit_turn_in_clean_repository_approves_as_no_code_edits(
    tmp_path, monkeypatch, capsys
):
    """Real git, no seam: clean tree on the base branch assembles to nothing."""
    repo = _clean_repo(tmp_path)
    _setup(tmp_path, monkeypatch, repo)
    monkeypatch.setattr(delegate.gate, "_gate_execute", _forbid_dispatch)

    assert _run(_edit_transcript(tmp_path)) == 0

    assert json.loads(capsys.readouterr().out) == _NO_CODE_EDITS


def test_untracked_only_change_is_still_reviewed(tmp_path, monkeypatch):
    """Boundary: a brand-new file is not an empty diff and must reach review."""
    repo = _clean_repo(tmp_path)
    (repo / "new_module.py").write_text("print('new')\n")
    _setup(tmp_path, monkeypatch, repo)
    prompts = []

    def execute_gate(_store, _entry, prompt, *_rest):
        prompts.append(prompt)
        return 0

    monkeypatch.setattr(delegate.gate, "_gate_execute", execute_gate)

    assert _run(_edit_transcript(tmp_path)) == 0

    assert len(prompts) == 1
    assert "new_module.py" in prompts[0]
