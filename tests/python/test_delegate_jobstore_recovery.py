#!/usr/bin/env python3
"""Job-record store and result-envelope normalization (data-model.md, SC-004).

Split out of the former test_delegate_dispatcher.py, which had grown past the
500-line file ceiling; the split follows the manifest_delegate package's own
module boundaries. Shared loader and registry-entry factory live in
_delegate_inproc.py.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_jobstore.py -q
"""

import time

import pytest
from _delegate_inproc import delegate

# ---------------------------------------------------------------------------
# Job-record store (T007)
# ---------------------------------------------------------------------------


class TestJobStoreDispatchRecovery:
    @pytest.mark.parametrize(
        ("reaped", "expected_state"),
        ((True, "fallback_pending"), (False, "dispatch_unknown")),
    )
    # constitution: exempt C-SIZE -- one parameterized fault transcript covers both durable outcomes.
    def test_post_popen_bookkeeping_failure_never_blindly_retries(
        self, tmp_path, monkeypatch, reaped, expected_state
    ):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        recovery = {
            "recovery_id": "recovery-launch",
            "next_tier": "flash",
            "next_index": 1,
            "requires_task_resubmission": True,
        }
        failure_summary = {"failure_class": "rate_limit"}
        store.write_recovery(record["job_id"], recovery)
        store.mutate(
            record["job_id"],
            lambda rec: dict(
                rec,
                recovery=recovery,
                failure_summary=failure_summary,
            ),
        )

        class FakeProcess:
            pid = 424242

            def poll(self):
                return 0 if reaped else None

            def wait(self, timeout=None):
                del timeout
                return 0

        monkeypatch.setattr(
            delegate.worker.subprocess, "Popen", lambda *args, **kwargs: FakeProcess()
        )
        monkeypatch.setattr(delegate.worker.os, "getpgid", lambda pid: pid)
        monkeypatch.setattr(
            delegate.process, "_terminate_and_reap_worker", lambda proc: reaped
        )
        real_mutate = store.mutate

        def fail_spawned_checkpoint(job_id, mutator, expected_version=None):
            if mutator.__name__ == "_spawned":
                raise OSError("injected checkpoint failure")
            return real_mutate(job_id, mutator, expected_version=expected_version)

        store.mutate = fail_spawned_checkpoint

        with pytest.raises(OSError, match="checkpoint failure"):
            delegate.worker._spawn_worker(store, record["job_id"], b"fresh task")
        if reaped:
            delegate.worker._restore_fallback_pending(
                store,
                record["job_id"],
                recovery,
                failure_summary,
            )

        final = store.read(record["job_id"])
        assert final["state"] == expected_state
        if reaped:
            assert store.read_recovery(record["job_id"]) == recovery
        else:
            assert final["recovery"] == recovery
            assert final["recovery_audit"]["resumable"] is False
            assert store.read_recovery(record["job_id"]) == recovery

    def test_unknown_checkpoint_failure_remains_non_resumable(
        self, tmp_path, monkeypatch
    ):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        recovery = {
            "recovery_id": "recovery-double-fault",
            "next_tier": "flash",
            "next_index": 1,
            "requires_task_resubmission": True,
        }
        store.write_recovery(record["job_id"], recovery)
        store.mutate(
            record["job_id"],
            lambda rec: dict(rec, recovery=recovery, fallback_pending=False),
        )

        class FakeProcess:
            pid = 424243

        monkeypatch.setattr(
            delegate.worker.subprocess, "Popen", lambda *args, **kwargs: FakeProcess()
        )
        monkeypatch.setattr(delegate.worker.os, "getpgid", lambda pid: pid)
        monkeypatch.setattr(
            delegate.process, "_terminate_and_reap_worker", lambda proc: False
        )
        real_mutate = store.mutate

        def fail_checkpoints(job_id, mutator, expected_version=None):
            if mutator.__name__ in {"_spawned", "_unknown"}:
                raise OSError(f"injected {mutator.__name__} failure")
            return real_mutate(job_id, mutator, expected_version=expected_version)

        store.mutate = fail_checkpoints

        with pytest.raises(
            delegate.worker.DispatchUnknownPersistenceError,
            match="failed closed",
        ):
            delegate.worker._spawn_worker(store, record["job_id"], b"fresh task")

        restored = delegate.worker._restore_fallback_pending(
            store,
            record["job_id"],
            recovery,
            {"failure_class": "rate_limit"},
        )
        assert restored["state"] == "queued"
        assert store.has_dispatch_unknown_audit(record["job_id"])
        assert store.read_recovery(record["job_id"]) == recovery

    def test_spawn_checkpoint_termination_and_audit_triple_failure_retains_exclusion(
        self, tmp_path, monkeypatch
    ):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        recovery = {
            "recovery_id": "recovery-triple-fault",
            "next_tier": "flash",
            "next_index": 1,
            "requires_task_resubmission": True,
        }
        store.write_recovery(record["job_id"], recovery)
        store.mutate(
            record["job_id"],
            lambda rec: dict(rec, recovery=recovery, fallback_pending=False),
        )

        class FakeProcess:
            pid = 424244

        monkeypatch.setattr(
            delegate.worker.subprocess, "Popen", lambda *args, **kwargs: FakeProcess()
        )
        monkeypatch.setattr(delegate.worker.os, "getpgid", lambda pid: pid)
        monkeypatch.setattr(
            delegate.process, "_terminate_and_reap_worker", lambda proc: False
        )
        real_mutate = store.mutate

        def fail_spawned(job_id, mutator, expected_version=None):
            if mutator.__name__ == "_spawned":
                raise OSError("injected spawned checkpoint failure")
            return real_mutate(job_id, mutator, expected_version=expected_version)

        store.mutate = fail_spawned
        monkeypatch.setattr(
            store,
            "write_dispatch_unknown_audit",
            lambda job_id, audit: (_ for _ in ()).throw(OSError("audit failed")),
        )

        with pytest.raises(delegate.worker.DispatchUnknownPersistenceError):
            delegate.worker._spawn_worker(store, record["job_id"], b"fresh task")

        restored = delegate.worker._restore_fallback_pending(
            store,
            record["job_id"],
            recovery,
            {"failure_class": "rate_limit"},
        )
        assert restored["state"] == "queued"
        assert store.has_launch_exclusion(record["job_id"])
        assert store.read_recovery(record["job_id"]) == recovery


class TestJobStoreRetention:
    def test_reap_noop_on_terminal_job(self, tmp_path, monkeypatch):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_id = record["job_id"]

        def _complete(rec):
            rec["state"] = "completed"
            return rec

        store.mutate(job_id, _complete)
        store.reap_if_dead(job_id)
        after = store.read(job_id)
        assert after["state"] == "completed"

    def test_keep_last_50_prunes_oldest(self, tmp_path, monkeypatch):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))

        def _complete(rec):
            rec["state"] = "completed"
            return rec

        ids = []
        for _ in range(delegate.KEEP_LAST_N + 5):
            rec = store.create("codex")
            store.mutate(rec["job_id"], _complete)
            ids.append(rec["job_id"])
            time.sleep(0.001)
        # Pruning runs inside create(), before the just-created record is
        # itself marked terminal, so at most one extra (not-yet-completed)
        # record can be present beyond the cap at any single snapshot.
        remaining = store.list_job_ids()
        assert len(remaining) <= delegate.KEEP_LAST_N + 1

    def test_prune_never_deletes_active_jobs(self, tmp_path, monkeypatch):
        """Non-terminal (queued/running) jobs must never be pruned, even when
        they are the oldest records and terminal jobs outnumber KEEP_LAST_N."""
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))

        # Oldest job stays queued (active) and must survive pruning.
        active = store.create("codex")
        time.sleep(0.001)

        def _complete(rec):
            rec["state"] = "completed"
            return rec

        for _ in range(delegate.KEEP_LAST_N + 5):
            rec = store.create("codex")
            store.mutate(rec["job_id"], _complete)
            time.sleep(0.001)

        remaining = store.list_job_ids()
        assert active["job_id"] in remaining
        assert store.read(active["job_id"])["state"] == "queued"

    def test_prune_never_deletes_unresolved_fallback_pending_jobs(
        self, tmp_path, monkeypatch
    ):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        pending = store.create("codex")

        def _pending(record):
            record["state"] = "fallback_pending"
            record["fallback_pending"] = True
            return record

        store.mutate(pending["job_id"], _pending)
        time.sleep(0.001)

        def _complete(record):
            record["state"] = "completed"
            return record

        for _ in range(delegate.KEEP_LAST_N + 5):
            record = store.create("codex")
            store.mutate(record["job_id"], _complete)
            time.sleep(0.001)

        assert pending["job_id"] in store.list_job_ids()
        assert store.read(pending["job_id"])["state"] == "fallback_pending"


# ---------------------------------------------------------------------------
# Result-envelope normalization (T008)
# ---------------------------------------------------------------------------
