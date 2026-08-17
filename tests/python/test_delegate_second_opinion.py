#!/usr/bin/env python3
"""Second-opinion dispatch: context injection, read-only forcing, attribution.

Split out of the former test_delegate_dispatcher.py, which had grown past the
500-line file ceiling; the split follows the manifest_delegate package's own
module boundaries. Shared loader and registry-entry factory live in
_delegate_inproc.py.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_second_opinion.py -q
"""

import io
import sys
import threading

from _delegate_inproc import _valid_backend, delegate

# ---------------------------------------------------------------------------
# Second opinion (T022, US3)
# ---------------------------------------------------------------------------


class _SOArgs:
    backend = None
    background = False
    wait = True
    write = False
    model = None
    budget = None
    resume = None
    resume_last = False
    fresh = False
    second_opinion = True
    of = None
    task_file = None
    prompt_file = None
    prompt = None
    json = True


class TestSecondOpinion:
    def _setup(self, tmp_path, monkeypatch, backend_id="claude"):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        store = delegate.JobStore(cwd=str(tmp_path))
        original = store.create("codex")
        attempt_id = "attempt-original"
        store.mutate(
            original["job_id"],
            lambda r: {
                **r,
                "state": "completed",
                "attempt_id": attempt_id,
                "result_attempt_id": attempt_id,
                "findings_attempt_id": attempt_id,
                "prompt_summary": "must never be reused",
                "envelope": {
                    "outcome": "success",
                    "raw_output": "must never be reused",
                    "findings": [
                        {
                            "severity": "low",
                            "text": "Password hashing: The implementation uses bcrypt.",
                        }
                    ],
                },
            },
        )
        return store, original["job_id"]

    def _args(self, tmp_path, of_id, backend="claude"):
        task_file = tmp_path / "second-opinion-task.txt"
        task_file.write_text("compare the authentication approaches", encoding="utf-8")
        args = _SOArgs()
        args.backend = backend
        args.of = of_id
        args.task_file = str(task_file)
        return args

    def test_second_opinion_injects_referenced_context(
        self, tmp_path, monkeypatch, capsys
    ):
        _store, of_id = self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["prompt"] = prompt_bytes.decode("utf-8")
            captured["write"] = record.get("write")
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = self._args(tmp_path, of_id)
        rc = delegate.cmd_task(
            args, [_valid_backend("codex"), _valid_backend("claude")], {}, set()
        )
        assert rc == 0
        assert of_id in captured["prompt"]
        assert "Password hashing" in captured["prompt"]
        assert "uses bcrypt" in captured["prompt"]
        assert "compare the authentication approaches" in captured["prompt"]
        assert "must never be reused" not in captured["prompt"]

    def test_second_opinion_wait_output_attributes_original_job_id(
        self, tmp_path, monkeypatch, capsys
    ):
        """Regression test: `task --second-opinion --of <id> --wait` text output
        must surface the ORIGINAL job's id, not just the new second-opinion
        job's own id. The smoke fixture greps the second-opinion output for
        the original job id to prove attribution."""
        _store, of_id = self._setup(tmp_path, monkeypatch)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = self._args(tmp_path, of_id)
        args.json = False
        rc = delegate.cmd_task(
            args, [_valid_backend("codex"), _valid_backend("claude")], {}, set()
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert of_id in out
        assert f"second_opinion_of: {of_id}" in out

    def test_same_backend_warns_and_lists_ready_alternatives(
        self, tmp_path, monkeypatch, capsys
    ):
        _store, of_id = self._setup(tmp_path, monkeypatch, backend_id="codex")

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {"state": "completed", "envelope": {"outcome": "success"}}

        def fake_probe(entry, user_config, services_disabled):
            return {"state": "ready" if entry["id"] == "claude" else "unavailable"}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        monkeypatch.setattr(delegate.readiness, "probe_backend_readiness", fake_probe)
        args = self._args(tmp_path, of_id, backend="codex")
        rc = delegate.cmd_task(
            args,
            [
                _valid_backend("codex"),
                _valid_backend("claude"),
                _valid_backend("gemini"),
            ],
            {},
            set(),
        )
        err = capsys.readouterr().err
        assert rc == 0
        assert "same as the original job's backend" in err
        assert "claude" in err
        assert "gemini" not in err.split("alternatives:")[1]

    def test_second_opinion_forces_read_only_despite_write_flag(
        self, tmp_path, monkeypatch, capsys
    ):
        _store, of_id = self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["write"] = record.get("write")
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = self._args(tmp_path, of_id)
        args.write = True
        rc = delegate.cmd_task(
            args, [_valid_backend("codex"), _valid_backend("claude")], {}, set()
        )
        assert rc == 0
        assert captured["write"] is False

    def test_second_opinion_without_resubmitted_task_is_rejected(
        self, tmp_path, monkeypatch, capsys
    ):
        """Missing explicit input must fail before touching an attached TTY."""
        _store, of_id = self._setup(tmp_path, monkeypatch)
        args = _SOArgs()
        args.backend = "claude"
        args.of = of_id

        def unexpected_read(_args):
            raise AssertionError("second opinion attempted to read implicit stdin")

        monkeypatch.setattr(delegate.backend, "_read_prompt", unexpected_read)
        rc = delegate.cmd_task(
            args, [_valid_backend("codex"), _valid_backend("claude")], {}, set()
        )
        assert rc == 2
        assert "explicit '-'" in capsys.readouterr().err

    def test_second_opinion_without_prompt_terminates_quickly(
        self, tmp_path, monkeypatch, capsys
    ):
        """End-to-end guard: cmd_task must return well within a short timeout
        when no prompt is supplied, proving the hang is gone even if the
        stdin short-circuit above were ever bypassed by a refactor."""
        _store, of_id = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"fresh task")))

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _SOArgs()
        args.backend = "claude"
        args.of = of_id
        args.prompt = "-"

        result = {}

        def _call():
            result["rc"] = delegate.cmd_task(
                args, [_valid_backend("codex"), _valid_backend("claude")], {}, set()
            )

        thread = threading.Thread(target=_call, daemon=True)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive(), (
            "cmd_task did not return within 5s -- likely hung on stdin"
        )
        assert result["rc"] == 0

    def test_task_prompt_injects_shared_result_envelope_contract(
        self, tmp_path, monkeypatch
    ):
        _store, of_id = self._setup(tmp_path, monkeypatch)
        args = self._args(tmp_path, of_id)
        prompt, _write, error = delegate._build_task_prompt(args, None)

        assert error is None
        assert "End your final message with exactly one fenced JSON block" in prompt
        assert '"attempted"' in prompt
        assert '"follow_ups"' in prompt
        assert '"findings"' in prompt

    def test_second_opinion_create_rejects_source_mutation_under_cas(
        self, tmp_path, monkeypatch, capsys
    ):
        store, of_id = self._setup(tmp_path, monkeypatch)
        args = self._args(tmp_path, of_id)
        real_create = delegate.task.jobstore.JobStore.create_second_opinion

        def mutate_before_create(self, source_job_id, backend_id, **kwargs):
            def replace_attempt(record):
                return {
                    **record,
                    "attempt_id": "attempt-replaced",
                    "result_attempt_id": "attempt-replaced",
                    "findings_attempt_id": "attempt-replaced",
                }

            replace_attempt.allow_terminal_reentry = True
            store.mutate(
                source_job_id,
                replace_attempt,
            )
            return real_create(self, source_job_id, backend_id, **kwargs)

        monkeypatch.setattr(
            delegate.task.jobstore.JobStore,
            "create_second_opinion",
            mutate_before_create,
        )

        rc = delegate.cmd_task(
            args, [_valid_backend("codex"), _valid_backend("claude")], {}, set()
        )

        assert rc == 2
        assert "source changed" in capsys.readouterr().err
        children = [
            store.read(job_id) for job_id in store.list_job_ids() if job_id != of_id
        ]
        assert children == []


class TestSecondOpinionAtomicBinding:
    _setup = TestSecondOpinion._setup

    def test_atomic_second_opinion_child_binds_source_identity(
        self, tmp_path, monkeypatch
    ):
        store, of_id = self._setup(tmp_path, monkeypatch)
        source = delegate.task._validated_second_opinion_context(
            store.read_locked(of_id)
        )

        child = store.create_second_opinion(
            of_id,
            "claude",
            expected_version=source["version"],
            attempt_id=source["attempt_id"],
            findings_digest=source["findings_digest"],
            validator=delegate.task._validated_second_opinion_context,
            extra={"kind": "task"},
        )

        assert child["second_opinion_of"] == of_id
        assert child["second_opinion_source_version"] == source["version"]
        assert child["second_opinion_attempt_id"] == source["attempt_id"]
        assert child["second_opinion_findings_digest"] == source["findings_digest"]

    def test_prune_eligible_source_does_not_deadlock_or_vanish(
        self, tmp_path, monkeypatch
    ):
        """The source job is held under flock; create()'s prune must skip it.

        flock is per open file description, so pruning the source would
        re-open its .lock and block on the lock this call already holds.
        """
        store, of_id = self._setup(tmp_path, monkeypatch)
        # Retention 0 makes every terminal job -- including the source -- a
        # prune candidate, which is the deadlock trigger.
        monkeypatch.setattr(
            sys.modules["manifest_delegate.jobstore_prune"].constants,
            "KEEP_LAST_N",
            0,
        )
        source = delegate.task._validated_second_opinion_context(
            store.read_locked(of_id)
        )
        result = {}

        def _create():
            result["child"] = store.create_second_opinion(
                of_id,
                "claude",
                expected_version=source["version"],
                attempt_id=source["attempt_id"],
                findings_digest=source["findings_digest"],
                validator=delegate.task._validated_second_opinion_context,
                extra={"kind": "task"},
            )

        worker = threading.Thread(target=_create, daemon=True)
        worker.start()
        worker.join(timeout=10)

        assert not worker.is_alive(), "create_second_opinion deadlocked on its own lock"
        assert result["child"]["second_opinion_of"] == of_id
        assert store.read(of_id)["job_id"] == of_id
