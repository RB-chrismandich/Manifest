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
    prompt_file = None
    prompt = "compare approaches"
    json = True


class TestSecondOpinion:
    def _setup(self, tmp_path, monkeypatch, backend_id="claude"):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        store = delegate.JobStore(cwd=str(tmp_path))
        original = store.create("codex")
        store.mutate(
            original["job_id"],
            lambda r: {
                **r,
                "state": "completed",
                "prompt_summary": "review auth flow",
                "envelope": {"outcome": "success", "findings": ["uses bcrypt"]},
            },
        )
        return store, original["job_id"]

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
        args = _SOArgs()
        args.backend = "claude"
        args.of = of_id
        rc = delegate.cmd_task(
            args, [_valid_backend("codex"), _valid_backend("claude")], {}, set()
        )
        assert rc == 0
        assert of_id in captured["prompt"]
        assert "review auth flow" in captured["prompt"]
        assert "uses bcrypt" in captured["prompt"]

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
        args = _SOArgs()
        args.backend = "claude"
        args.of = of_id
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
        args = _SOArgs()
        args.backend = "codex"
        args.of = of_id
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
        args = _SOArgs()
        args.backend = "claude"
        args.of = of_id
        args.write = True
        rc = delegate.cmd_task(
            args, [_valid_backend("codex"), _valid_backend("claude")], {}, set()
        )
        assert rc == 0
        assert captured["write"] is False

    def test_second_opinion_without_prompt_never_reads_stdin(
        self, tmp_path, monkeypatch, capsys
    ):
        """Regression test for the --second-opinion hang: with no positional
        prompt (args.prompt is None, the real CLI shape when only --of is
        given), _build_task_prompt must not fall back to sys.stdin.read().
        A stdin.read() call here would block forever waiting for input that
        is never piped in second-opinion mode."""
        _store, of_id = self._setup(tmp_path, monkeypatch)
        captured = {}

        class _BoomStdin:
            def read(self):
                raise AssertionError(
                    "sys.stdin.read() must not be called in --second-opinion mode"
                )

        monkeypatch.setattr(sys, "stdin", _BoomStdin())

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["prompt"] = prompt_bytes.decode("utf-8")
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _SOArgs()
        args.backend = "claude"
        args.of = of_id
        args.prompt = None  # no positional prompt supplied, as in real usage
        rc = delegate.cmd_task(
            args, [_valid_backend("codex"), _valid_backend("claude")], {}, set()
        )
        assert rc == 0
        assert of_id in captured["prompt"]

    def test_second_opinion_without_prompt_terminates_quickly(
        self, tmp_path, monkeypatch, capsys
    ):
        """End-to-end guard: cmd_task must return well within a short timeout
        when no prompt is supplied, proving the hang is gone even if the
        stdin short-circuit above were ever bypassed by a refactor."""
        _store, of_id = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        args = _SOArgs()
        args.backend = "claude"
        args.of = of_id
        args.prompt = None

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
