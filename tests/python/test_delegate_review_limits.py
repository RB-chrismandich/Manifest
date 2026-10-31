"""Resource limits apply before review or Stop-gate Git output is buffered."""

import subprocess

import pytest
from _delegate_inproc import _valid_backend, delegate
from test_delegate_review import _init_git_repo, _ReviewArgs


@pytest.mark.parametrize("scope", ["working-tree", "auto", "branch"])
def test_large_tracked_diff_fails_closed(tmp_path, scope):
    _init_git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("x" * (2 * delegate.backend.TASK_LIMIT))
    base = "HEAD"
    if scope == "branch":
        subprocess.run(["git", "commit", "-qam", "large"], cwd=tmp_path, check=True)
        base = "HEAD~1"
    with pytest.raises(delegate.ReviewDiffError, match="limit"):
        delegate.assemble_review_diff(scope, base, cwd=str(tmp_path))


def test_untracked_diffs_share_tracked_byte_budget(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("a" * 600_000)
    (tmp_path / "untracked.txt").write_text("b" * 600_000)
    with pytest.raises(delegate.ReviewDiffError, match="limit"):
        delegate.assemble_review_diff("working-tree", None, cwd=str(tmp_path))


def test_untracked_count_rejected_before_per_file_processes(tmp_path, monkeypatch):
    _init_git_repo(tmp_path)
    for index in range(129):
        (tmp_path / f"new-{index}").touch()
    calls = []
    original = delegate.review._run_git

    def tracked(args, cwd, **kwargs):
        calls.append(args)
        return original(args, cwd, **kwargs)

    monkeypatch.setattr(delegate.review, "_run_git", tracked)
    with pytest.raises(delegate.ReviewDiffError, match=r"untracked.*limit"):
        delegate.assemble_review_diff("working-tree", None, cwd=str(tmp_path))
    assert not any("--no-index" in args for args in calls)


def test_review_overflow_is_visible_without_dispatch(tmp_path, monkeypatch, capsys):
    _init_git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("x" * (2 * delegate.backend.TASK_LIMIT))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "jobs"))
    monkeypatch.setattr(
        delegate.task, "_check_task_backend_ready", lambda *a: (None, 0)
    )
    assert delegate.cmd_review(_ReviewArgs(), [_valid_backend()], {}, set()) == 2
    assert "limit" in capsys.readouterr().err
    assert not list((tmp_path / "jobs").rglob("record.json"))


def test_gate_prompt_overflow_returns_no_partial_prompt(tmp_path, monkeypatch):
    _init_git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("x" * (2 * delegate.backend.TASK_LIMIT))
    monkeypatch.chdir(tmp_path)
    prompt, encoded, error = delegate.gate._gate_build_prompt(_valid_backend())
    assert prompt is encoded is None
    assert error == "could not assemble review diff"


def test_untracked_binary_messages_share_budget(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "image.bin").write_bytes(b"\x00binary")
    expected = "Binary file image.bin (untracked)\n"
    assert (
        delegate.review._untracked_diff(tmp_path, max_bytes=len(expected)) == expected
    )
    with pytest.raises(delegate.ReviewDiffError, match="byte limit"):
        delegate.review._untracked_diff(tmp_path, max_bytes=len(expected) - 1)


def test_quoted_untracked_paths_preserve_content(tmp_path):
    _init_git_repo(tmp_path)
    for path in ["space name", "tab\tname", "line\nname", "é.txt", "--output=bad"]:
        (tmp_path / path).write_text("complete change\n")
    diff = delegate.review._untracked_diff(tmp_path)
    assert diff.count("+complete change") == 5


def test_tracked_diff_is_complete_and_unchanged(tmp_path):
    _init_git_repo(tmp_path)
    expected = subprocess.check_output(["git", "diff", "HEAD"], cwd=tmp_path).decode()
    assert (
        delegate.assemble_review_diff("working-tree", None, str(tmp_path)) == expected
    )
