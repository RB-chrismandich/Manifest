"""Behavioral contracts for cgroup-v2 delegate containment."""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delegate_harness import _run
from _delegate_inproc import delegate

containment = delegate.containment


def _fake_cgroup_root(tmp_path):
    root = tmp_path / "cgroup"
    root.mkdir()
    (root / "cgroup.controllers").write_text("cpu memory")
    (root / "cgroup.procs").write_text("")
    (root / "cgroup.kill").write_text("")
    return root


class TestContainmentContract:
    def test_probe_requires_unified_writable_root_and_cgroup_kill(self, tmp_path):
        root = _fake_cgroup_root(tmp_path)
        assert containment.probe(str(root)) == (True, "cgroup v2 with cgroup.kill")
        (root / "cgroup.kill").unlink()
        available, reason = containment.probe(str(root))
        assert available is False
        assert "cgroup.kill" in reason

    def test_create_persists_contained_state_after_job_directory_exists(
        self, tmp_path, monkeypatch
    ):
        root = _fake_cgroup_root(tmp_path)
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        real_makedirs = containment.os.makedirs

        def make_cgroup(path, *args, **kwargs):
            real_makedirs(path, *args, **kwargs)
            open(os.path.join(path, "cgroup.kill"), "w").close()
            open(os.path.join(path, "cgroup.procs"), "w").close()

        monkeypatch.setattr(containment.os, "makedirs", make_cgroup)
        path, state, reason = containment.create(str(job_dir), root=str(root))
        assert state == containment.STATE_CONTAINED
        assert reason == "cgroup v2 with cgroup.kill"
        assert containment.read_path(str(job_dir)) == path

    def test_cleanup_retains_marker_when_cgroup_directory_cannot_be_removed(
        self, tmp_path
    ):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        cgroup = tmp_path / "cgroup"
        cgroup.mkdir()
        (cgroup / "member").write_text("still active")
        (job_dir / containment.CGROUP_DIR_FILENAME).write_text(str(cgroup))
        assert containment.cleanup(str(job_dir)) is False
        assert containment.read_path(str(job_dir)) == str(cgroup)

    def test_cleanup_waits_for_cgroup_procs_to_drain_before_rmdir(
        self, tmp_path, monkeypatch
    ):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        cgroup = tmp_path / "cgroup"
        cgroup.mkdir()
        procs = cgroup / "cgroup.procs"
        procs.write_text("12345\n")
        (cgroup / "cgroup.kill").write_text("")
        (job_dir / containment.CGROUP_DIR_FILENAME).write_text(str(cgroup))
        monkeypatch.setattr(containment, "reap", lambda *_args, **_kwargs: True)

        def drain_then_empty(path, timeout=containment._REAP_DRAIN_TIMEOUT_SECONDS):
            if procs.read_text().strip():
                procs.write_text("")
            return containment._wait_cgroup_empty(path, timeout)

        monkeypatch.setattr(containment, "_wait_cgroup_empty", drain_then_empty)
        assert containment.cleanup(str(job_dir)) is True
        assert containment.read_path(str(job_dir)) is None
        assert not cgroup.exists()

    def test_cleanup_removes_marker_only_after_cgroup_directory_is_gone(
        self, tmp_path, monkeypatch
    ):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        cgroup = tmp_path / "cgroup"
        cgroup.mkdir()
        (job_dir / containment.CGROUP_DIR_FILENAME).write_text(str(cgroup))
        monkeypatch.setattr(containment, "reap", lambda *_args, **_kwargs: True)
        assert containment.cleanup(str(job_dir)) is True
        assert containment.read_path(str(job_dir)) is None

    def test_join_failure_aborts_backend_launch_before_setsid(
        self, tmp_path, monkeypatch
    ):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        (job_dir / containment.CGROUP_DIR_FILENAME).write_text("/cannot/join")
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

    def test_orphan_recovery_reaps_containment_without_pgid(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_dir = Path(store.job_dir(record["job_id"]))
        cgroup = tmp_path / "contained"
        cgroup.mkdir()
        kill_file = cgroup / "cgroup.kill"
        kill_file.write_text("")
        (job_dir / containment.CGROUP_DIR_FILENAME).write_text(str(cgroup))

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
        cgroup = tmp_path / "cgroup"
        cgroup.mkdir()
        (job_dir / containment.CGROUP_DIR_FILENAME).write_text(str(cgroup))
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
        cgroup = tmp_path / "cgroup"
        cgroup.mkdir()
        (job_dir / containment.CGROUP_DIR_FILENAME).write_text(str(cgroup))
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


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux containment venue"
)
@pytest.mark.native
def test_linux_ci_requires_writable_cgroup_venue():
    if not os.environ.get("CI"):
        pytest.skip("local Linux lacks the delegated CI venue")
    available, reason = containment.probe()
    assert available, reason


@pytest.mark.native
@pytest.mark.skipif(
    not (sys.platform.startswith("linux") and containment.probe()[0]),
    reason="requires delegated cgroup v2",
)
def test_reap_kills_double_setsid_descendant(tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    path, state, _reason = containment.create(str(job_dir))
    assert state == containment.STATE_CONTAINED
    script = "import os,sys,time; os.setsid();\nif os.fork()==0:\n os.setsid(); print(os.getpid(),flush=True); time.sleep(300)"
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        text=True,
        preexec_fn=lambda: containment.join(path),
    )
    child = int(proc.stdout.readline().strip())
    proc.wait(timeout=30)
    assert containment.reap(str(job_dir)) is True
    for _ in range(100):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("cgroup reap did not kill double-setsid descendant")
    assert containment.cleanup(str(job_dir)) is True


def _wait_for_path(path, description):
    deadline = time.time() + 10
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    pytest.fail(f"{description} was not created")


def _assert_dead(pid, description):
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail(f"{description} remained alive")


@pytest.mark.native
@pytest.mark.skipif(
    not (sys.platform.startswith("linux") and containment.probe()[0]),
    reason="requires delegated cgroup v2",
)
def test_timeout_reaps_double_setsid_descendant_through_worker(tmp_path, env_factory):
    pidfile = tmp_path / "timeout.pid"
    env = env_factory(control={"detached_holder_secs": 300, "sleep": 300})
    env["MANIFEST_CGROUP_ROOT"] = containment.cgroup_root()
    env["STUB_DETACHED_PIDFILE"] = str(pidfile)
    env["STUB_DETACHED_CLOSE_STREAMS"] = "1"
    config_path = Path(env["MANIFEST_CONFIG_DIR"]) / "delegation.json"
    config_path.write_text(
        '{"default_backend":"stub","backends":{"stub":{"budget_seconds":1}}}'
    )

    result = _run(env, "task", "--json", "timeout")

    assert result.returncode == 1, result.stderr
    _wait_for_path(pidfile, "double-setsid descendant pidfile")
    pid = int(pidfile.read_text())
    _assert_dead(pid, "timeout descendant")
    record_path = next(Path(env["MANIFEST_DELEGATIONS_DIR"]).rglob("record.json"))
    job_dir = record_path.parent
    assert not (job_dir / containment.CGROUP_DIR_FILENAME).exists()


@pytest.mark.native
@pytest.mark.skipif(
    not (sys.platform.startswith("linux") and containment.probe()[0]),
    reason="requires delegated cgroup v2",
)
def test_cancel_reaps_double_setsid_descendant_through_cmd_cancel(
    tmp_path, env_factory
):
    pidfile = tmp_path / "cancel.pid"
    env = env_factory(control={"detached_holder_secs": 300, "sleep": 300})
    env["MANIFEST_CGROUP_ROOT"] = containment.cgroup_root()
    env["STUB_DETACHED_PIDFILE"] = str(pidfile)
    env["STUB_DETACHED_CLOSE_STREAMS"] = "1"
    launched = _run(env, "task", "--background", "--json", "cancel")
    assert launched.returncode == 0, launched.stderr
    record_path = next(Path(env["MANIFEST_DELEGATIONS_DIR"]).rglob("record.json"))
    _wait_for_path(pidfile, "double-setsid descendant pidfile")
    job_dir = record_path.parent
    marker = job_dir / containment.CGROUP_DIR_FILENAME
    _wait_for_path(marker, "containment marker")

    cancelled = _run(env, "cancel", job_dir.name, "--json")

    assert cancelled.returncode == 0, cancelled.stderr
    _assert_dead(int(pidfile.read_text()), "cancelled descendant")
    deadline = time.time() + 5
    while marker.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert not marker.exists()
