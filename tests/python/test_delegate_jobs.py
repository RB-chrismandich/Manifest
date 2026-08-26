"""Pytest tests for plugins/manifest-delegate/scripts/delegate.py (T009).

CLI-subprocess-level job-lifecycle coverage: task (foreground/background),
status, result, cancel — driven against stub backend executables on PATH.
In-process JobStore/envelope unit coverage already lives in
test_delegate_dispatcher.py (TestJobStore / TestEnvelopeNormalization); this
file intentionally does not duplicate that and instead exercises delegate.py
as a real subprocess end to end.
"""

import json
import stat
import time
from pathlib import Path

from _delegate_harness import (
    _dispatch_background_async,
    _known_job_ids,
    _new_job_id,
    _poll_new_job_id,
    _registry,
    _run,
    _stub_entry,
)


class TestForegroundTask:
    def test_foreground_completion_returns_envelope(self, env_factory):
        env = env_factory(
            control={
                "envelope": {
                    "backend": "stub",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                }
            }
        )
        result = _run(env, "task", "--json", "hello world")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["backend"] == "stub"
        assert payload["outcome"] == "success"
        assert payload["job_id"], (
            "json envelope must carry job_id (attribution for --second-opinion --of)"
        )

    def test_foreground_human_output_includes_job_id(self, env_factory):
        env = env_factory(
            control={
                "envelope": {
                    "backend": "stub",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                }
            }
        )
        result = _run(env, "task", "hello world")
        assert result.returncode == 0, result.stderr
        job_id_lines = [
            line for line in result.stdout.splitlines() if line.startswith("job_id: ")
        ]
        assert len(job_id_lines) == 1, result.stdout
        job_id = job_id_lines[0].split("job_id: ", 1)[1].strip()
        assert job_id == _new_job_id(env_factory)

    def test_foreground_backend_failure_exit_1(self, env_factory):
        env = env_factory(control={"exit_code": 1, "raw_text": "boom"})
        result = _run(env, "task", "--json", "hi")
        assert result.returncode == 1

    def test_unknown_backend_exit_2(self, env_factory):
        env = env_factory()
        result = _run(env, "task", "--backend", "nope", "hi")
        assert result.returncode == 2
        assert "nope" in result.stderr

    def test_unknown_cli_arg_exits_2(self, env_factory):
        """J3: an unrecognized flag must be rejected, not silently dropped."""
        env = env_factory()
        result = _run(env, "status", "--definitely-unknown")
        assert result.returncode == 2
        assert "unrecognized arguments" in result.stderr
        assert "--definitely-unknown" in result.stderr

    def test_permissions_0700_0600(self, env_factory):
        env = env_factory(
            control={
                "envelope": {
                    "backend": "stub",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                }
            }
        )
        result = _run(env, "task", "--json", "hi")
        assert result.returncode == 0, result.stderr
        (json.loads(result.stdout)["job_id"] if "job_id" in result.stdout else None)
        delegations_dir = env_factory.delegations_dir
        job_dirs = [
            p
            for p in delegations_dir.rglob("*")
            if p.is_dir() and (p / "record.json").exists()
        ]
        assert job_dirs, "expected at least one job dir"
        for job_dir in job_dirs:
            assert stat.S_IMODE(job_dir.stat().st_mode) == 0o700
            for fname in ("record.json", "output.txt", "job.log"):
                fpath = job_dir / fname
                if fpath.exists():
                    assert stat.S_IMODE(fpath.stat().st_mode) == 0o600


class TestBackgroundLifecycle:
    def test_background_spawn_status_result(self, env_factory):
        env = env_factory(
            control={
                "envelope": {
                    "backend": "stub",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                }
            }
        )
        result = _run(env, "task", "--background", "--json", "hi")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        job_id = payload["job_id"]

        deadline = time.time() + 15
        state = None
        while time.time() < deadline:
            status = _run(env, "status", job_id, "--json")
            state = json.loads(status.stdout).get("state")
            if state in ("completed", "failed", "timeout"):
                break
            time.sleep(0.3)
        assert state == "completed", f"final state={state!r}"

        result_out = _run(env, "result", job_id, "--json")
        assert result_out.returncode == 0
        envelope = json.loads(result_out.stdout)
        assert envelope["outcome"] == "success"

    def test_oversized_backend_output_is_capped_and_still_parses_envelope(
        self, env_factory
    ):
        """J5: a backend that emits far more than the capture cap (here 2 MiB of
        filler before the envelope) must not defeat parsing — the dispatcher
        retains a bounded TAIL, which still contains the final fenced envelope.
        Also exercises the bounded-memory capture path (no whole-output buffer)."""
        env = env_factory(
            control={
                "prefix_bytes": 2 * 1024 * 1024,
                "envelope": {
                    "backend": "stub",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                },
            }
        )
        result = _run(env, "task", "--json", "hi")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["outcome"] == "success"

    def test_session_ref_survives_output_larger_than_tail(self, env_factory):
        """O3 (codex round 4): the session id (emitted near the START of the
        stream) must survive a run whose output exceeds the 1 MiB tail — captured
        from the retained head, not the tail. Stub emits `session: <ref>` then
        2 MiB of filler then the envelope; the completed job must carry the ref."""
        env = env_factory(
            control={
                "session_format": "output_scan",
                "session_ref": "sessXYZ",
                "prefix_bytes": 2 * 1024 * 1024,
                "envelope": {
                    "backend": "stub",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                },
            }
        )
        result = _run(env, "task", "--json", "hi")
        assert result.returncode == 0, result.stderr
        job_id = json.loads(result.stdout)["job_id"]
        record_path = next(
            p
            for p in env_factory.delegations_dir.rglob("record.json")
            if p.parent.name == job_id
        )
        assert json.loads(record_path.read_text()).get("session_ref") == "sessXYZ"

    def test_result_on_active_job_exit_1(self, env_factory):
        env = env_factory(
            control={
                "sleep": 5,
                "envelope": {
                    "backend": "stub",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                },
            }
        )
        result = _run(env, "task", "--background", "--json", "hi")
        job_id = json.loads(result.stdout)["job_id"]
        result_out = _run(env, "result", job_id)
        assert result_out.returncode == 1

    def test_cancel_active_job(self, env_factory):
        env = env_factory(
            control={
                "sleep": 10,
                "envelope": {
                    "backend": "stub",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                },
            }
        )
        result = _run(env, "task", "--background", "--json", "hi")
        job_id = json.loads(result.stdout)["job_id"]
        time.sleep(0.5)
        cancel = _run(env, "cancel", job_id, "--json")
        assert cancel.returncode == 0, cancel.stderr

        deadline = time.time() + 10
        state = None
        while time.time() < deadline:
            status = _run(env, "status", job_id, "--json")
            state = json.loads(status.stdout).get("state")
            if state != "running" and state != "queued":
                break
            time.sleep(0.3)
        assert state == "cancelled"

    def test_cancel_immediately_after_dispatch_never_runs_backend(
        self, env_factory, tmp_path
    ):
        """G1: cancel racing a fresh --background dispatch must win the claim
        so the backend executable never spawns. A sentinel file is written by
        the stub backend unconditionally on process start (before any sleep),
        so its absence proves cmd_worker's queued->running claim failed and
        _run_backend_and_finish was never called."""
        sentinel = tmp_path / "sentinel.txt"
        env = env_factory(
            control={
                "sentinel_file": str(sentinel),
                "envelope": {
                    "backend": "stub",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                },
            }
        )
        # Cancel as soon as the job dir lands on disk — before `task` returns —
        # so we race the worker spawn, not a fast stub backend that can finish
        # before the cancel subprocess starts after a blocking `_run(task)`.
        known_ids = _known_job_ids(env_factory.delegations_dir)
        dispatch = _dispatch_background_async(env, "--json", "hi")
        try:
            job_id = _poll_new_job_id(env_factory.delegations_dir, known_ids)
            assert job_id is not None, "background job never appeared on disk"
            cancel = _run(env, "cancel", job_id, "--json")
            assert cancel.returncode == 0, cancel.stderr
        finally:
            dispatch.wait(timeout=30)

        assert dispatch.returncode == 0, dispatch.stderr

        deadline = time.time() + 10
        state = None
        while time.time() < deadline:
            status = _run(env, "status", job_id, "--json")
            state = json.loads(status.stdout).get("state")
            if state not in ("queued", "running"):
                break
            time.sleep(0.2)
        assert state == "cancelled", f"final state={state!r}"
        assert not sentinel.exists(), (
            "backend executable ran despite cancel winning the race"
        )

    def test_cancel_already_terminal_is_noop_exit_0(self, env_factory):
        env = env_factory(
            control={
                "envelope": {
                    "backend": "stub",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                }
            }
        )
        result = _run(env, "task", "--json", "hi")
        assert result.returncode == 0, result.stderr
        job_id = _new_job_id(env_factory)
        cancel = _run(env, "cancel", job_id, "--json")
        assert cancel.returncode == 0
        status = _run(env, "status", job_id, "--json")
        assert json.loads(status.stdout)["state"] == "completed"


class TestTimeoutAndReaping:
    def test_timeout_marks_job_timeout(self, env_factory):
        env = env_factory(control={"sleep": 5})
        entries = [_stub_entry(id_="stub")]
        registry_path = Path(env["MANIFEST_DELEGATE_REGISTRY_PATH"])
        registry_path.write_text(json.dumps(_registry(entries)))
        result = _run(env, "task", "--background", "--budget", "1", "--json", "hi")
        job_id = json.loads(result.stdout)["job_id"]

        deadline = time.time() + 15
        state = None
        while time.time() < deadline:
            status = _run(env, "status", job_id, "--json")
            state = json.loads(status.stdout).get("state")
            if state in ("completed", "failed", "timeout"):
                break
            time.sleep(0.3)
        assert state == "timeout"


class TestConcurrencyAndRetention:
    def test_concurrent_jobs_get_disjoint_dirs(self, env_factory):
        env = env_factory(
            control={
                "envelope": {
                    "backend": "stub",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                }
            }
        )
        job_ids = set()
        for _ in range(3):
            result = _run(env, "task", "--json", "hi")
            assert result.returncode == 0, result.stderr
            job_ids.add(_new_job_id(env_factory, known_ids=job_ids))
        assert len(job_ids) == 3
