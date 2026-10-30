"""Exercise capture limits against real child processes, not buffered mocks."""

import os
import sys
import time

import pytest
from _delegate_inproc import delegate

git_capture = delegate.review.review_git


def _fake_git(tmp_path, monkeypatch, body):
    binary = tmp_path / "git"
    binary.write_text(f"#!{sys.executable}\nimport os, sys, time\n{body}\n")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")


def test_exact_byte_boundary_and_diff_exit_one(tmp_path, monkeypatch):
    _fake_git(tmp_path, monkeypatch, "os.write(1, 'éé'.encode()); sys.exit(1)")
    assert delegate.review._run_git([], tmp_path, max_bytes=4) == "éé"
    with pytest.raises(delegate.ReviewDiffError, match="byte limit"):
        delegate.review._run_git([], tmp_path, max_bytes=3)
    assert delegate.review._git_or_none([], tmp_path) is None
    assert delegate.gate._working_tree_has_changes(tmp_path) is None


@pytest.mark.parametrize("fd", [1, 2])
def test_flood_is_stopped_without_reading_complete_output(tmp_path, monkeypatch, fd):
    _fake_git(
        tmp_path, monkeypatch, f"os.write({fd}, b'x' * 8_000_000); time.sleep(10)"
    )
    real_read = os.read
    received = []

    def observe(descriptor, size):
        chunk = real_read(descriptor, size)
        received.append(len(chunk))
        return chunk

    monkeypatch.setattr(git_capture.os, "read", observe)
    start = time.monotonic()
    with pytest.raises(delegate.ReviewDiffError, match="byte limit"):
        git_capture.capture_git([], tmp_path, max_bytes=4096)
    assert time.monotonic() - start < 3
    cap = 4096 if fd == 1 else git_capture.MAX_FAILURE_STREAM_BYTES
    assert sum(received) <= cap + 1


def test_overflow_kills_inherited_pipe_holder(tmp_path, monkeypatch):
    marker = tmp_path / "child-survived"
    _fake_git(
        tmp_path,
        monkeypatch,
        "if os.fork() == 0:\n"
        "    time.sleep(0.8)\n"
        f"    open({str(marker)!r}, 'w').write('survived')\n"
        "    os._exit(0)\n"
        "os.write(1, b'x' * 100_000)\n"
        "time.sleep(10)",
    )
    with pytest.raises(delegate.ReviewDiffError, match="byte limit"):
        git_capture.capture_git([], tmp_path, max_bytes=4096)
    time.sleep(1)
    assert not marker.exists()


@pytest.mark.parametrize("close_pipes", [False, True])
def test_timeout_covers_pipe_drain_and_process_exit(tmp_path, monkeypatch, close_pipes):
    body = "os.close(1); os.close(2); " if close_pipes else ""
    _fake_git(tmp_path, monkeypatch, body + "time.sleep(10)")
    start = time.monotonic()
    with pytest.raises(delegate.ReviewDiffError, match="time limit"):
        git_capture.capture_git([], tmp_path, deadline=start + 0.15)
    assert time.monotonic() - start < 3


def test_branch_probe_overflow_does_not_fall_back(tmp_path, monkeypatch):
    _fake_git(tmp_path, monkeypatch, "os.write(1, b'x' * 100_000)")
    with pytest.raises(delegate.ReviewDiffError, match="byte limit"):
        delegate.review._resolve_branch_base(None, tmp_path)


def test_status_overflow_is_unknown_not_no_changes(tmp_path, monkeypatch):
    _fake_git(tmp_path, monkeypatch, "os.write(1, b'x' * 2_000_000)")
    assert delegate.gate._working_tree_has_changes(tmp_path) is None


def test_missing_ref_still_allows_next_candidate(tmp_path, monkeypatch):
    _fake_git(
        tmp_path,
        monkeypatch,
        "if sys.argv[-1] != 'origin/main': sys.exit(128)\nprint('abcdef1234')",
    )
    assert delegate.review._resolve_branch_base(None, tmp_path) == "abcdef1234"


def test_collection_deadline_prevents_launch(tmp_path, monkeypatch):
    def unexpected_spawn(*args, **kwargs):
        pytest.fail("expired collection started another Git process")

    monkeypatch.setattr(git_capture.subprocess, "Popen", unexpected_spawn)
    with pytest.raises(delegate.ReviewDiffError, match="limit"):
        delegate.review._scope_diff(["HEAD"], tmp_path, deadline=time.monotonic() - 1)
