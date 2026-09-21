"""Behavioral contracts for the approved cgroup-v2 containment prerequisite."""

import errno
import os
import subprocess
from pathlib import Path

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


def test_package_import_exposes_containment_module():
    assert delegate.containment is containment

def test_join_hook_uses_the_owned_marker_path(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    cgroup = _write_containment_marker(tmp_path, job_dir, monkeypatch)
    joined = []
    monkeypatch.setattr(containment, "join", joined.append)

    hook = containment.join_hook(str(job_dir))

    assert hook is not None
    hook()
    assert joined == [str(cgroup)]


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
        assert reason == "cgroup v2 delegated root with writable membership and cgroup.kill"
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
            path = containment.read_path(str(job_dir))
            assert path is not None
            (Path(path) / name).unlink()
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
