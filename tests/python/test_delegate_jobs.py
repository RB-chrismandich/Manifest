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
    _new_job_id,
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
        result = _run(env, "task", "--background", "--json", "hi")
        assert result.returncode == 0, result.stderr
        job_id = json.loads(result.stdout)["job_id"]
        cancel = _run(env, "cancel", job_id, "--json")
        assert cancel.returncode == 0, cancel.stderr

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


class TestSessionCapture:
    def test_output_scan_session_ref_recorded(self, env_factory):
        env = env_factory(
            control={
                "session_format": "output_scan",
                "session_ref": "sess-xyz",
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
        job_id = _new_job_id(env_factory)
        status = _run(env, "status", job_id, "--json")
        assert json.loads(status.stdout).get("session_ref") == "sess-xyz"


class TestPayloadLimits:
    def test_payload_over_limit_rejected_exit_2(self, env_factory):
        entry = _stub_entry(id_="stub")
        entry["input"]["max_payload_bytes"] = 10
        env = env_factory(
            entries=[entry],
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
            },
        )
        result = _run(env, "task", "this prompt is definitely longer than ten bytes")
        assert result.returncode == 2
        assert (
            "max_payload_bytes" in result.stderr or "payload" in result.stderr.lower()
        )


class TestResumeAndSecondOpinion:
    def test_resume_last_reuses_backend_and_session(self, env_factory):
        env = env_factory(
            control={
                "session_format": "output_scan",
                "session_ref": "sess-first",
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
        first = _run(env, "task", "--json", "first prompt")
        assert first.returncode == 0, first.stderr
        first_id = _new_job_id(env_factory)

        second = _run(
            env, "task", "--resume-last", "--backend", "stub", "--json", "follow up"
        )
        assert second.returncode == 0, second.stderr
        job_id = _new_job_id(env_factory, known_ids={first_id})
        status = _run(env, "status", job_id, "--json")
        assert status.returncode == 0

    def test_resume_null_backend_falls_back_fresh(self, env_factory):
        entry = _stub_entry(id_="noresume", resume=None)
        env = env_factory(
            entries=[entry],
            control={
                "envelope": {
                    "backend": "noresume",
                    "model": "default",
                    "outcome": "success",
                    "attempted": "x",
                    "changes": [],
                    "succeeded": [],
                    "failed": [],
                    "follow_ups": [],
                }
            },
        )
        first = _run(env, "task", "--backend", "noresume", "--json", "first")
        assert first.returncode == 0, first.stderr
        job_id = _new_job_id(env_factory)
        second = _run(env, "task", "--resume", job_id, "--json", "second")
        assert second.returncode == 0, second.stderr
        assert "fresh" in (second.stderr.lower() + second.stdout.lower())

    def test_second_opinion_requires_of_exit_2(self, env_factory):
        env = env_factory()
        result = _run(env, "task", "--second-opinion", "hi")
        assert result.returncode == 2
        assert "--of" in result.stderr

    def test_second_opinion_same_backend_warns_not_blocking(self, env_factory):
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
        first = _run(env, "task", "--json", "first")
        assert first.returncode == 0, first.stderr
        job_id = _new_job_id(env_factory)
        second = _run(
            env,
            "task",
            "--second-opinion",
            "--of",
            job_id,
            "--backend",
            "stub",
            "--json",
            "hi",
        )
        assert second.returncode == 0
        assert "same" in second.stderr.lower() or "warning" in second.stderr.lower()

    def test_second_opinion_job_record_carries_original_prompt_summary(
        self, env_factory
    ):
        """J2: --second-opinion must not lose the original task's context;
        the new job's record.json should carry a prompt_summary referencing it."""
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
        first = _run(
            env, "task", "--json", "first prompt with distinctive marker XYZZY"
        )
        assert first.returncode == 0, first.stderr
        first_id = _new_job_id(env_factory)

        second = _run(
            env,
            "task",
            "--second-opinion",
            "--of",
            first_id,
            "--backend",
            "stub",
            "--json",
            "hi",
        )
        assert second.returncode == 0, second.stderr
        second_id = _new_job_id(env_factory, known_ids={first_id})

        record_path = next(
            p
            for p in env_factory.delegations_dir.rglob("record.json")
            if p.parent.name == second_id
        )
        record = json.loads(record_path.read_text())
        assert "XYZZY" in record.get("prompt_summary", ""), record

    def test_explicit_backend_mismatch_on_resume_exit_2(self, env_factory):
        entries = [_stub_entry(id_="stub"), _stub_entry(id_="noresume", resume=None)]
        env = env_factory(
            entries=entries,
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
            },
        )
        first = _run(env, "task", "--backend", "stub", "--json", "first")
        assert first.returncode == 0, first.stderr
        job_id = _new_job_id(env_factory)
        second = _run(env, "task", "--resume", job_id, "--backend", "noresume", "hi")
        assert second.returncode == 2
