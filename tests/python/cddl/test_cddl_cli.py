"""US1 follow-up — CLI seams the bats suite can't reach cheaply (audit punch
list): RepoLock owner naming + stale reclaim, backend auth probe, answer
failure paths (T022/T027, FR-012)."""

import json
import os
import time

import pytest
from cddl import PreflightError
from cddl.cli import RepoLock, _probe_backend, main


def test_held_lock_names_owning_run(fixture_repo, state_root):
    RepoLock(fixture_repo, stale_s=3600, state_root=state_root).acquire(
        run_hint="run-abc123"
    )
    with pytest.raises(PreflightError, match="run-abc123"):
        RepoLock(fixture_repo, stale_s=3600, state_root=state_root).acquire(
            run_hint="run-later"
        )


def test_lock_lives_under_state_root(fixture_repo, state_root):
    # FR-017: the lock is state-root confined, never /tmp
    lock = RepoLock(fixture_repo, stale_s=10, state_root=state_root).acquire()
    assert lock.path.is_relative_to(state_root)


def test_stale_lock_is_reclaimed(fixture_repo, state_root):
    first = RepoLock(fixture_repo, stale_s=10, state_root=state_root).acquire(
        run_hint="dead-run"
    )
    old = time.time() - 60  # older than the stale threshold
    os.utime(first.path, (old, old))
    second = RepoLock(fixture_repo, stale_s=10, state_root=state_root).acquire(
        run_hint="new-run"
    )
    assert json.loads(second.path.read_text())["run"] == "new-run"


def test_release_is_idempotent(fixture_repo, state_root):
    lock = RepoLock(fixture_repo, stale_s=10, state_root=state_root).acquire()
    lock.release()
    lock.release()  # second release must not raise
    assert not lock.path.exists()


def _stub_cli(bin_dir, name, script):
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / name
    path.write_text(f"#!/usr/bin/env bash\n{script}\n")
    path.chmod(0o755)
    return path


def test_probe_missing_backend_refused():
    with pytest.raises(PreflightError, match="no usable backend"):
        _probe_backend("definitely-not-a-real-cli-xyz")


def test_probe_logged_out_backend_refused(tmp_path, monkeypatch):
    _stub_cli(
        tmp_path / "bin",
        "fake-claude",
        'if [ "$1" = auth ]; then printf \'{"loggedIn": false}\\n\'; exit 1; fi',
    )
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    with pytest.raises(PreflightError, match="not logged in"):
        _probe_backend("fake-claude")


def test_probe_fails_open_without_auth_subcommand(tmp_path, monkeypatch):
    # A seam CLI that doesn't implement `auth status` must not be refused.
    _stub_cli(tmp_path / "bin", "plain-cli", 'echo "unknown command"; exit 2')
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    _probe_backend("plain-cli")  # must not raise


def test_answer_missing_file_is_usage_error(fixture_repo, monkeypatch, capsys):
    import cddl.cli as cli

    monkeypatch.setattr(cli, "_probe_backend", lambda c: None)
    monkeypatch.chdir(fixture_repo)
    rc = main(["answer", "--run", "whatever", "--answers-file", "/no/such/file"])
    assert rc == 2
    assert "answers file not found" in capsys.readouterr().err


def test_answer_unknown_run_refused(
    fixture_repo, state_root, monkeypatch, tmp_path, capsys
):
    import cddl.cli as cli

    monkeypatch.setattr(cli, "_probe_backend", lambda c: None)
    monkeypatch.chdir(fixture_repo)
    answers = tmp_path / "answers.md"
    answers.write_text("some answer\n")
    rc = main(
        [
            "answer",
            "--run",
            "19990101T000000Z-none",
            "--answers-file",
            str(answers),
            "--state-root",
            str(state_root),
        ]
    )
    assert rc == 6
    assert "no such run" in capsys.readouterr().err


def test_status_by_run_id_from_outside_repo(
    fixture_repo,
    state_root,
    roles_dir,
    fake_runner_cls,
    verdict,
    candidate,
    monkeypatch,
    tmp_path,
    capsys,
):
    from cddl.loop import RunConfig, start_run

    runner = fake_runner_cls(
        [
            verdict("qa_critic", "complete"),
            verdict("arch_critic", "complete"),
            candidate([("greet.py", "hi\n")]),
            verdict("qa_critic", "approve"),
            verdict("arch_critic", "approve"),
        ]
    )
    outcome = start_run(
        fixture_repo,
        RunConfig(cli="stub-cli", verify_cmd="true"),
        state_root=state_root,
        prompts_dir=roles_dir,
        runner=runner,
    )
    elsewhere = tmp_path / "not-a-repo"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    rc = main(["status", "--run", outcome.run_id, "--state-root", str(state_root)])
    assert rc == 0
    assert "success" in capsys.readouterr().out
