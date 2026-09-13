"""Behavioral contracts for cgroup-v2 delegate containment."""

import errno
import os
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delegate_inproc import delegate

containment = delegate.containment


def _fake_cgroup_root(tmp_path):
    root = tmp_path / "cgroup"
    root.mkdir()
    (root / "cgroup.controllers").write_text("cpu memory")
    for name in ("cgroup.procs", "cgroup.kill"):
        (root / name).write_text("")
    return root


def _write_containment_marker(tmp_path, job_dir, monkeypatch):
    root = _fake_cgroup_root(tmp_path)
    path = root / f"manifest-delegate-{job_dir.name}"
    path.mkdir()
    for name in ("cgroup.procs", "cgroup.kill"):
        (path / name).write_text("")
    (job_dir / containment.CGROUP_DIR_FILENAME).write_text(str(path))
    monkeypatch.setenv(containment.CGROUP_ROOT_ENV, str(root))
    return path


class TestContainmentOperations:
    def test_probe_requires_unified_writable_root_and_cgroup_kill(self, tmp_path):
        root = _fake_cgroup_root(tmp_path)
        assert containment.probe(str(root)) == (
            True,
            "cgroup v2 delegated root with writable membership and cgroup.kill",
        )
        (root / "cgroup.kill").unlink()
        available, reason = containment.probe(str(root))
        assert available is False
        assert "cgroup.kill" in reason

    def test_probe_requires_writable_parent_membership_control(self, tmp_path):
        root = _fake_cgroup_root(tmp_path)
        (root / "cgroup.procs").chmod(0o444)

        available, reason = containment.probe(str(root))

        assert available is False
        assert "cgroup.procs is not writable" in reason

    def test_create_requires_writable_child_membership_and_kill_controls(
        self, tmp_path, monkeypatch
    ):
        root = _fake_cgroup_root(tmp_path)
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        monkeypatch.setenv(containment.CGROUP_ROOT_ENV, str(root))
        real_makedirs = containment.os.makedirs

        def make_incomplete_cgroup(path, *args, **kwargs):
            real_makedirs(path, *args, **kwargs)
            open(os.path.join(path, "cgroup.kill"), "w").close()

        monkeypatch.setattr(containment.os, "makedirs", make_incomplete_cgroup)

        _path, state, reason = containment.create(str(job_dir))

        assert state == containment.STATE_DEGRADED
        assert "cgroup.procs is not writable" in reason

    def test_create_persists_contained_state_after_job_directory_exists(
        self, tmp_path, monkeypatch
    ):
        root = _fake_cgroup_root(tmp_path)
        job_dir = tmp_path / "job"
        monkeypatch.setenv(containment.CGROUP_ROOT_ENV, str(root))
        job_dir.mkdir()
        real_makedirs = containment.os.makedirs

        def make_cgroup(path, *args, **kwargs):
            real_makedirs(path, *args, **kwargs)
            open(os.path.join(path, "cgroup.kill"), "w").close()
            open(os.path.join(path, "cgroup.procs"), "w").close()

        monkeypatch.setattr(containment.os, "makedirs", make_cgroup)
        path, state, reason = containment.create(str(job_dir), root=str(root))
        assert state == containment.STATE_CONTAINED
        assert (
            reason
            == "cgroup v2 delegated root with writable membership and cgroup.kill"
        )
        assert containment.read_path(str(job_dir)) == path

    @pytest.mark.parametrize(
        "marker_factory",
        (
            lambda root, expected, sibling: root,
            lambda root, expected, sibling: root.parent / "outside",
            lambda root, expected, sibling: sibling,
            lambda root, expected, sibling: root / "alias",
            lambda root, expected, sibling: expected.parent / f"not-{expected.name}",
        ),
    )
    def test_reap_rejects_every_marker_except_the_canonical_job_child(
        self, tmp_path, monkeypatch, marker_factory
    ):
        root = _fake_cgroup_root(tmp_path)
        job_dir = tmp_path / "job-a"
        job_dir.mkdir()
        expected = root / "manifest-delegate-job-a"
        sibling = root / "manifest-delegate-job-b"
        for path in (expected, sibling):
            path.mkdir()
            (path / "cgroup.kill").write_text("")
            (path / "cgroup.procs").write_text("")
        outside = root.parent / "outside"
        outside.mkdir()
        (outside / "cgroup.kill").write_text("")
        alias = root / "alias"
        alias.symlink_to(expected, target_is_directory=True)
        marker = marker_factory(root, expected, sibling)
        (job_dir / containment.CGROUP_DIR_FILENAME).write_text(str(marker))
        monkeypatch.setenv(containment.CGROUP_ROOT_ENV, str(root))

        assert containment.reap(str(job_dir), required=True) is False
        assert (expected / "cgroup.kill").read_text() == ""
        assert (sibling / "cgroup.kill").read_text() == ""
        assert (outside / "cgroup.kill").read_text() == ""

    def test_reap_rejects_a_symlinked_marker_file(self, tmp_path, monkeypatch):
        root = _fake_cgroup_root(tmp_path)
        job_dir = tmp_path / "job-a"
        job_dir.mkdir()
        expected = root / "manifest-delegate-job-a"
        expected.mkdir()
        (expected / "cgroup.kill").write_text("")
        (expected / "cgroup.procs").write_text("")
        target = tmp_path / "marker-target"
        target.write_text(str(expected))
        (job_dir / containment.CGROUP_DIR_FILENAME).symlink_to(target)
        monkeypatch.setenv(containment.CGROUP_ROOT_ENV, str(root))

        assert containment.reap(str(job_dir), required=True) is False
        assert (expected / "cgroup.kill").read_text() == ""

    def test_cleanup_retains_marker_when_cgroup_directory_cannot_be_removed(
        self, tmp_path, monkeypatch
    ):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        cgroup = _write_containment_marker(tmp_path, job_dir, monkeypatch)
        (cgroup / "member").write_text("still active")
        assert containment.cleanup(str(job_dir)) is False
        assert containment.read_path(str(job_dir)) == str(cgroup)

    def test_cleanup_removes_marker_only_after_cgroup_directory_is_gone(
        self, tmp_path, monkeypatch
    ):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        _write_containment_marker(tmp_path, job_dir, monkeypatch)
        for name in ("cgroup.procs", "cgroup.kill"):
            (
                containment.read_path(str(job_dir))
                and Path(containment.read_path(str(job_dir))) / name
            ).unlink()
        monkeypatch.setattr(containment, "reap", lambda *_args, **_kwargs: True)
        assert containment.cleanup(str(job_dir)) is True
        assert containment.read_path(str(job_dir)) is None

    def test_cleanup_retries_transient_busy_cgroup_removal(self, tmp_path, monkeypatch):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        cgroup = _write_containment_marker(tmp_path, job_dir, monkeypatch)
        for name in ("cgroup.procs", "cgroup.kill"):
            (cgroup / name).unlink()
        real_rmdir = containment.os.rmdir
        attempts = 0

        def transient_busy(path):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError(errno.EBUSY, "descendants still exiting")
            real_rmdir(path)

        monkeypatch.setattr(containment, "reap", lambda *_args, **_kwargs: True)
        monkeypatch.setattr(containment.os, "rmdir", transient_busy)
        monkeypatch.setattr(containment.time, "sleep", lambda _seconds: None)
        assert containment.cleanup(str(job_dir)) is True
        assert attempts == 2
        assert containment.read_path(str(job_dir)) is None

    def test_join_failure_aborts_backend_launch_before_setsid(
        self, tmp_path, monkeypatch
    ):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        _write_containment_marker(tmp_path, job_dir, monkeypatch)
        monkeypatch.setattr(
            containment, "join", lambda path: (_ for _ in ()).throw(OSError("denied"))
        )
        with pytest.raises(subprocess.SubprocessError):
            delegate.process._launch_backend(["true"], "devnull", str(job_dir))

    def test_reap_reports_degraded_separately_from_contained_failure(self, tmp_path):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        assert containment.reap(str(job_dir)) is None
        cgroup = tmp_path / "contained"
        cgroup.mkdir()
        (cgroup / "cgroup.kill").mkdir()
        (job_dir / containment.CGROUP_DIR_FILENAME).write_text(str(cgroup))
        assert containment.reap(str(job_dir)) is False


class TestContainmentProcessLifecycle:
    def test_cancel_attempts_pgid_and_worker_fallback_after_failed_cgroup_reap(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        record.update(
            pgid=1234,
            worker_pid=5678,
            foreground=False,
            containment={"state": containment.STATE_CONTAINED},
        )
        attempts = []
        monkeypatch.setattr(containment, "reap", lambda *_args, **_kwargs: False)
        monkeypatch.setattr(delegate.process, "_backend_alive", lambda *_args: True)
        monkeypatch.setattr(
            delegate.process,
            "_kill_pgid",
            lambda *_args: attempts.append("pgid") or True,
        )
        monkeypatch.setattr(delegate.process, "_worker_alive", lambda *_args: True)
        monkeypatch.setattr(
            delegate.jobs_cli.os,
            "kill",
            lambda pid, sig: attempts.append(("worker", pid, sig)),
        )

        assert (
            delegate.jobs_cli._terminate_job_processes(store, record["job_id"], record)
            is False
        )
        assert attempts == ["pgid", ("worker", 5678, delegate.jobs_cli.signal.SIGKILL)]

    def test_orphan_reaper_attempts_pgid_fallback_after_failed_cgroup_reap(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        record.update(
            pgid=1234,
            containment={"state": containment.STATE_CONTAINED},
        )
        attempts = []
        monkeypatch.setattr(containment, "reap", lambda *_args, **_kwargs: False)
        monkeypatch.setattr(delegate.process, "_backend_alive", lambda *_args: True)
        monkeypatch.setattr(
            delegate.process,
            "_kill_pgid",
            lambda *_args: attempts.append("pgid") or True,
        )
        monkeypatch.setattr(
            delegate.process, "_clear_pgid_tracking", lambda *_args: None
        )

        assert (
            delegate.process._reap_cancelled_orphan(store, record["job_id"], record)
            is False
        )
        assert attempts == ["pgid"]

    def test_orphan_recovery_reaps_containment_without_pgid(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_dir = Path(store.job_dir(record["job_id"]))
        cgroup = _write_containment_marker(tmp_path, job_dir, monkeypatch)
        kill_file = cgroup / "cgroup.kill"

        delegate.process._reap_cancelled_orphan(
            store, record["job_id"], store.read(record["job_id"])
        )

        assert kill_file.read_text() == "1"

    def test_contained_record_fails_closed_when_marker_is_missing(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_id = record["job_id"]
        store.mutate(
            job_id,
            lambda current: dict(
                current,
                state="failed",
                containment={"state": containment.STATE_CONTAINED},
            ),
        )
        monkeypatch.setattr(delegate.jobs_cli.jobstore, "JobStore", lambda: store)

        args = SimpleNamespace(
            job_id=job_id, expected_version=None, recovery_id=None, json=True
        )
        assert delegate.jobs_cli.cmd_cancel(args) == 1
        assert store.read(job_id)["containment_cleanup_failed"] is True
        assert Path(store.job_dir(job_id)).exists()

    def test_recovery_retains_contained_job_with_dangling_marker(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_id = record["job_id"]
        job_dir = Path(store.job_dir(job_id))
        (job_dir / containment.CGROUP_DIR_FILENAME).symlink_to(tmp_path / "missing")
        store.mutate(
            job_id,
            lambda current: dict(
                current,
                containment={"state": containment.STATE_CONTAINED},
                created_at=0,
            ),
        )

        recovered = store.reap_if_dead(job_id)

        assert recovered["state"] == "queued"
        assert recovered["containment_cleanup_failed"] is True

    def test_prune_retains_contained_job_when_marker_is_dangling(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_id = record["job_id"]
        job_dir = Path(store.job_dir(job_id))
        (job_dir / containment.CGROUP_DIR_FILENAME).symlink_to(tmp_path / "missing")
        store.mutate(
            job_id,
            lambda current: dict(
                current,
                state="failed",
                containment={"state": containment.STATE_CONTAINED},
            ),
        )

        assert store._delete_job_locked(job_id) is False
        assert job_dir.exists()


class TestContainmentCleanupCheckpoint:
    def test_terminal_cancel_marks_cleanup_complete_before_removing_marker(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_id = record["job_id"]
        job_dir = Path(store.job_dir(job_id))
        _write_containment_marker(tmp_path, job_dir, monkeypatch)
        for name in ("cgroup.procs", "cgroup.kill"):
            (
                containment.read_path(str(job_dir))
                and Path(containment.read_path(str(job_dir))) / name
            ).unlink()
        store.mutate(
            job_id,
            lambda current: dict(
                current,
                state="failed",
                containment={"state": containment.STATE_CONTAINED},
            ),
        )
        monkeypatch.setattr(containment, "reap", lambda *_args, **_kwargs: True)
        monkeypatch.setattr(delegate.jobs_cli.jobstore, "JobStore", lambda: store)
        args = SimpleNamespace(
            job_id=job_id, expected_version=None, recovery_id=None, json=True
        )

        assert delegate.jobs_cli.cmd_cancel(args) == 0
        assert store.read(job_id)["containment"]["state"] == "cleaned"
        assert delegate.jobs_cli.cmd_cancel(args) == 0

    def test_prune_accepts_successfully_cleaned_containment(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_id = record["job_id"]
        job_dir = Path(store.job_dir(job_id))
        store.mutate(
            job_id,
            lambda current: dict(
                current,
                state="failed",
                containment={"state": "cleaned"},
            ),
        )
        assert store._delete_job_locked(job_id) is True
        assert not job_dir.exists()

    def test_prune_persists_cleanup_checkpoint_without_relocking(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_id = record["job_id"]
        job_dir = Path(store.job_dir(job_id))
        _write_containment_marker(tmp_path, job_dir, monkeypatch)
        for name in ("cgroup.procs", "cgroup.kill"):
            (
                containment.read_path(str(job_dir))
                and Path(containment.read_path(str(job_dir))) / name
            ).unlink()
        store.mutate(
            job_id,
            lambda current: dict(
                current,
                state="failed",
                containment={"state": containment.STATE_CONTAINED},
            ),
        )
        monkeypatch.setattr(containment, "reap", lambda *_args, **_kwargs: True)
        result = []
        pruning = threading.Thread(
            target=lambda: result.append(store._delete_job_locked(job_id)), daemon=True
        )

        pruning.start()
        pruning.join(timeout=1)

        assert not pruning.is_alive(), "prune deadlocked while persisting cleanup"
        assert result == [True]
        assert not job_dir.exists()

    def test_cancelled_recovery_retains_pgid_when_contained_marker_is_missing(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_id = record["job_id"]
        store.mutate(
            job_id,
            lambda current: dict(
                current,
                state="cancelled",
                pgid=12345,
                containment={"state": containment.STATE_CONTAINED},
            ),
        )

        recovered = store.reap_if_dead(job_id)

        assert recovered["containment_cleanup_failed"] is True
        assert recovered["pgid"] == 12345
