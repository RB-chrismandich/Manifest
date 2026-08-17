"""Resume, second-opinion, session capture, and payload limits (T009).

Split out of test_delegate_jobs.py, which had grown past the 500-line file
ceiling. That file covers the job LIFECYCLE (dispatch, status, cancel, reap);
this one covers what a follow-up invocation reuses from a finished job — the
captured session ref, the resume argv, and the limits that reject a prompt
before a backend is ever spawned.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_resume.py -q
"""

import json

from _delegate_harness import _new_job_id, _run, _stub_entry


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
                    "findings": [
                        {
                            "title": "Session isolation",
                            "detail": "The source run isolates session state.",
                            "severity": "low",
                        }
                    ],
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
            "-",
            input_text="hi",
        )
        assert second.returncode == 0
        assert "same" in second.stderr.lower() or "warning" in second.stderr.lower()

    def test_second_opinion_job_record_excludes_original_task_material(
        self, env_factory
    ):
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
                    "findings": [
                        {
                            "title": "Distinctive finding",
                            "detail": "Review the isolated behavior only.",
                            "severity": "medium",
                        }
                    ],
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
            "-",
            input_text="hi",
        )
        assert second.returncode == 0, second.stderr
        second_id = _new_job_id(env_factory, known_ids={first_id})

        record_path = next(
            p
            for p in env_factory.delegations_dir.rglob("record.json")
            if p.parent.name == second_id
        )
        record = json.loads(record_path.read_text())
        assert "XYZZY" not in json.dumps(record), record
        assert record["second_opinion_of"] == first_id
        assert record["second_opinion_attempt_id"]
        assert record["second_opinion_findings_digest"]

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
