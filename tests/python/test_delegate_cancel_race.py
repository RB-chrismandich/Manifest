#!/usr/bin/env python3
"""Cancel vs backend fork/publish race (Codex round-8 finding).

Its own module because test_delegate_cancel.py sits at the 500-line ceiling and
TestCancelOrphanReaping is at the 250-line class ceiling. Shares the process-
group harness in _delegate_harness.
"""

import json
import subprocess
import time

from _delegate_harness import (
    _kill_orphan,
    _materialize_workspace,
    _run,
    _spawn_orphan_holding_backend_lock,
)

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
