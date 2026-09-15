#!/usr/bin/env python3
"""Cancel vs backend fork/publish race (Codex round-8 finding).

Its own module because test_delegate_cancel.py sits at the 500-line ceiling and
TestCancelOrphanReaping is at the 250-line class ceiling. Shares the process-
group harness in _delegate_harness.
"""

import json
import os
import subprocess
import time

from _delegate_harness import (
    _kill_orphan,
    _materialize_workspace,
    _run,
    _spawn_orphan_holding_backend_lock,
    _stub_entry,
)
from _delegate_inproc import delegate

# `env_factory` is a fixture exposed globally via tests/python/conftest.py — used
# as a test parameter, never imported (importing it would shadow the fixture).


class TestCancelForkPublishRace:
    def test_cancel_waits_for_pgid_published_after_cancel_begins(self, env_factory):
        """The worker is SIGKILLed after Popen forked the backend (which holds
        the inherited backend.lock) but BEFORE the child wrote backend.pgid in
        preexec. A single read at cancel time would miss the pgid and
        _clear_pgid_tracking would orphan a write-capable backend under a
        terminal `cancelled` record. cancel must use the held lock as a handshake
        — wait for the pgid to publish, then kill the group. Here the orphan
        holds the lock and publishes backend.pgid 0.4s late; the record starts
        with NO pgid and no backend.pgid file. Pre-fix, the orphan survived."""
        env = env_factory()
        workspace_dir = _materialize_workspace(env_factory, env)
        job_dir = workspace_dir / ("f00dbabe" * 4)
        orphan, orphan_pgid = _spawn_orphan_holding_backend_lock(
            job_dir, publish_pgid_after=0.4
        )
        try:
            (job_dir / "record.json").write_text(
                json.dumps(
                    {
                        "job_id": job_dir.name,
                        "state": "running",
                        "worker_pid": 2**31 - 1,
                        "created_at": time.time(),
                        "updated_at": time.time(),
                    }
                )
            )
            assert not (job_dir / "backend.pgid").exists()

            cancel = _run(env, "cancel", job_dir.name, "--json")
            assert cancel.returncode == 0, cancel.stderr
            assert json.loads(cancel.stdout)["state"] == "cancelled"
            try:
                orphan.wait(timeout=5)
            except subprocess.TimeoutExpired as exc:
                raise AssertionError(
                    f"orphaned backend (pgid {orphan_pgid}) survived cancel — "
                    "the fork/publish race was not handled"
                ) from exc
        finally:
            _kill_orphan(orphan)


class TestSpawnAuthorizationBarrier:
    """The pre-Popen authorization (dispatch.backend_launched) that decides the
    cancel-vs-spawn race deterministically, in both directions."""

    @staticmethod
    def _job(monkeypatch, tmp_path, state, phase="backend_started"):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        store = delegate.JobStore(cwd=str(tmp_path))
        job_id = store.create("stub")["job_id"]

        def _stage(record):
            record["dispatch"] = {"phase": phase}
            return record

        store.mutate(job_id, _stage)
        if state != "running":
            store.mutate(job_id, lambda record: dict(record, state=state))
        else:
            store.mutate(job_id, lambda record: dict(record, state="running"))
        return store, job_id

    def _attempt(self, store, job_id, sentinel):
        argv = ["/bin/sh", "-c", f"touch {sentinel}"]
        return delegate.worker_backend._capture_attempt(
            _stub_entry(),
            argv,
            b"",
            store.job_dir(job_id),
            10,
            store,
            job_id,
        )

    def test_cancelled_record_denies_the_spawn_before_fork(self, monkeypatch, tmp_path):
        """Cancel won the CAS, so the authorization taken under the job lock
        immediately before Popen must refuse: no process, no fabricated exit
        status (which would be classified as a provider failure and could
        trigger a fallback for a cancelled job)."""
        store, job_id = self._job(monkeypatch, tmp_path, "cancelled")
        sentinel = tmp_path / "ran.txt"

        assert self._attempt(store, job_id, sentinel) is None
        assert not sentinel.exists(), "backend executable ran for a cancelled job"
        dispatch = store.read(job_id).get("dispatch") or {}
        assert not dispatch.get("backend_launched")

    def test_running_record_authorizes_and_records_the_launch(
        self, monkeypatch, tmp_path
    ):
        """The positive control: the guard is not vacuous, and it leaves the
        evidence a later cancel reads to answer `was_alive` truthfully. `phase`
        must stay "backend_started" -- jobstore_reaper._DISPATCH_OWNERSHIP_PHASES,
        worker._restore_fallback_pending and _return_dispatch_to_worker all
        enumerate it, so a new phase would silently drop out of all three."""
        store, job_id = self._job(monkeypatch, tmp_path, "running")
        sentinel = tmp_path / "ran.txt"

        assert self._attempt(store, job_id, sentinel) is not None
        assert sentinel.exists()
        dispatch = store.read(job_id).get("dispatch") or {}
        assert dispatch.get("backend_launched") is True
        assert dispatch.get("phase") == "backend_started"

    def test_cancel_reports_a_launch_it_lost_as_alive(self, env_factory, tmp_path):
        """The race's other order: the worker reserved its spawn before cancel's
        CAS landed. `was_alive` False is consumed as "cancel won the claim
        before anything spawned", so it must be True here -- a short-lived
        backend can fork, run and exit before cancel probes, leaving no pgid to
        kill and no held backend.lock, which is exactly the ~1/75 flake."""
        env = env_factory()
        workspace_dir = _materialize_workspace(env_factory, env)
        job_id = "cafed00d" * 4
        job_dir = workspace_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "record.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "state": "running",
                    "worker_pid": 2**31 - 1,
                    "dispatch": {"phase": "backend_started", "backend_launched": True},
                    "created_at": time.time(),
                    "updated_at": time.time(),
                }
            )
        )
        assert not (job_dir / "backend.pgid").exists()
        assert not os.path.exists(job_dir / "backend.lock")

        cancel = _run(env, "cancel", job_id, "--json")
        assert cancel.returncode == 0, cancel.stderr
        payload = json.loads(cancel.stdout)
        assert payload["state"] == "cancelled"
        assert payload["was_alive"] is True
