#!/usr/bin/env python3
"""Job-record store and result-envelope normalization (data-model.md, SC-004).

Split out of the former test_delegate_dispatcher.py, which had grown past the
500-line file ceiling; the split follows the manifest_delegate package's own
module boundaries. Shared loader and registry-entry factory live in
_delegate_inproc.py.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_jobstore.py -q
"""

import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import ClassVar

from _delegate_inproc import REPO_ROOT, delegate

# ---------------------------------------------------------------------------
# Job-record store (T007)
# ---------------------------------------------------------------------------


class TestJobStore:
    def test_delegations_dir_env_override_honored(self, tmp_path, monkeypatch):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path))
        root = delegate.delegations_root()
        assert str(root) == str(tmp_path) or Path(root) == tmp_path

    def test_workspace_dir_is_0700(self, tmp_path, monkeypatch):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        mode = stat.S_IMODE(os.stat(store.workspace_dir).st_mode)
        assert mode == 0o700

    def test_create_writes_0700_job_dir_and_0600_files(self, tmp_path, monkeypatch):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_dir = store.job_dir(record["job_id"])
        assert stat.S_IMODE(os.stat(job_dir).st_mode) == 0o700
        for fname in ("record.json", "output.txt", "job.log"):
            fpath = os.path.join(job_dir, fname)
            assert os.path.exists(fpath)
            assert stat.S_IMODE(os.stat(fpath).st_mode) == 0o600

    def test_create_initial_state_is_queued(self, tmp_path, monkeypatch):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        assert record["state"] == "queued"
        assert record["backend"] == "codex"

    def test_terminal_state_is_immutable(self, tmp_path, monkeypatch):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_id = record["job_id"]

        def _complete(rec):
            rec["state"] = "completed"
            return rec

        result = store.mutate(job_id, _complete)
        assert result["state"] == "completed"

        def _cancel(rec):
            rec["state"] = "cancelled"
            return rec

        # Attempting to mutate a terminal record must be refused (no-op).
        after = store.mutate(job_id, _cancel)
        assert after["state"] == "completed"

    def test_queued_to_cancelled_transition_allowed(self, tmp_path, monkeypatch):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_id = record["job_id"]

        def _cancel(rec):
            rec["state"] = "cancelled"
            return rec

        result = store.mutate(job_id, _cancel)
        assert result["state"] == "cancelled"

    def test_reap_marks_dead_worker_as_failed(self, tmp_path, monkeypatch):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        job_id = record["job_id"]

        def _mark_running(rec):
            rec["state"] = "running"
            rec["worker_pid"] = 999999999  # almost certainly not a live pid
            rec["pgid"] = None
            # Age past the worker-startup grace so a missing worker reads as death.
            rec["created_at"] = time.time() - delegate.WORKER_STARTUP_GRACE_SECONDS - 1
            return rec

        store.mutate(job_id, _mark_running)
        store.reap_if_dead(job_id)
        after = store.read(job_id)
        assert after["state"] == "failed"
        assert after["error"]

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


# ---------------------------------------------------------------------------
# Result-envelope normalization (T008)
# ---------------------------------------------------------------------------


class TestEnvelopeNormalization:
    VALID_ENVELOPE: ClassVar[dict] = {
        "backend": "codex",
        "model": "auto",
        "outcome": "success",
        "attempted": "did the thing",
        "changes": ["foo.py"],
        "succeeded": ["tests passed"],
        "failed": [],
        "follow_ups": [],
    }

    def test_extracts_last_fenced_json_block(self):
        raw = (
            "some prose\n"
            "```json\n" + json.dumps({"scratch": True}) + "\n```\n"
            "more prose\n"
            "```json\n" + json.dumps(self.VALID_ENVELOPE) + "\n```\n"
        )
        result = delegate.normalize_envelope(raw, "codex", "auto")
        assert result["outcome"] == "success"
        assert result["backend"] == "codex"

    def test_no_fenced_block_is_failure_never_fabricated(self):
        raw = "the backend just talked and talked with no structure at all"
        result = delegate.normalize_envelope(raw, "codex", "auto")
        assert result["outcome"] == "failure"
        assert "backend returned nothing usable" in result["error"]

    def test_empty_output_is_failure(self):
        result = delegate.normalize_envelope("", "codex", "auto")
        assert result["outcome"] == "failure"
        assert result["error"]

    def test_malformed_json_block_is_failure(self):
        raw = "```json\n{not valid json at all\n```\n"
        result = delegate.normalize_envelope(raw, "codex", "auto")
        assert result["outcome"] == "failure"

    def test_missing_required_fields_is_failure(self):
        raw = "```json\n" + json.dumps({"backend": "codex"}) + "\n```\n"
        result = delegate.normalize_envelope(raw, "codex", "auto")
        assert result["outcome"] == "failure"
        assert result["error"]

    def test_failure_outcome_without_error_gets_synthesized_error(self):
        envelope = dict(self.VALID_ENVELOPE)
        envelope["outcome"] = "failure"
        envelope.pop("error", None)
        raw = "```json\n" + json.dumps(envelope) + "\n```\n"
        result = delegate.normalize_envelope(raw, "codex", "auto")
        assert result["outcome"] == "failure"
        assert result.get("error")

    def test_valid_envelope_satisfies_schema_required_fields(self):
        schema_path = (
            REPO_ROOT
            / "specs"
            / "675-multi-agent-delegation"
            / "contracts"
            / "result-envelope.schema.json"
        )
        schema = json.loads(schema_path.read_text())
        raw = "```json\n" + json.dumps(self.VALID_ENVELOPE) + "\n```\n"
        result = delegate.normalize_envelope(raw, "codex", "auto")
        for field in schema["required"]:
            assert field in result, f"missing required field {field}"

    def test_spoofed_backend_and_model_are_overwritten_with_provenance(self):
        envelope = dict(self.VALID_ENVELOPE)
        envelope["backend"] = "not-the-real-backend"
        envelope["model"] = "not-the-real-model"
        raw = "```json\n" + json.dumps(envelope) + "\n```\n"
        result = delegate.normalize_envelope(raw, "codex", "auto")
        assert result["backend"] == "codex"
        assert result["model"] == "auto"

    def test_invalid_outcome_enum_value_is_failure(self):
        envelope = dict(self.VALID_ENVELOPE)
        envelope["outcome"] = "definitely-not-valid"
        raw = "```json\n" + json.dumps(envelope) + "\n```\n"
        result = delegate.normalize_envelope(raw, "codex", "auto")
        assert result["outcome"] == "failure"
        assert result["error"]

    def test_wrong_typed_array_field_is_failure(self):
        envelope = dict(self.VALID_ENVELOPE)
        envelope["changes"] = "not-a-list"
        raw = "```json\n" + json.dumps(envelope) + "\n```\n"
        result = delegate.normalize_envelope(raw, "codex", "auto")
        assert result["outcome"] == "failure"
        assert result["error"]


class TestSpawnBackendStdoutCapture:
    """Regression coverage for the capture path: even when a backend's argv
    mimics codex's --output-last-message flag (writing a separate file the
    stub never populates), _spawn_backend must still surface the envelope
    from raw stdout so normalize_envelope can extract it (contracts/
    delegate-cli.md raw-output contract)."""

    def test_stub_stdout_only_envelope_survives_output_file_combine(self, tmp_path):
        envelope = {
            "backend": "stub",
            "model": "auto",
            "outcome": "success",
            "attempted": "did the thing",
            "changes": [],
            "succeeded": ["ok"],
            "failed": [],
            "follow_ups": [],
        }
        stub = tmp_path / "stub.py"
        stub.write_text(
            "import sys\n"
            f"sys.stdout.write('```json\\n' + {json.dumps(envelope)!r} + '\\n```\\n')\n"
        )
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        argv = [
            sys.executable,
            str(stub),
            "--output-last-message",
            os.path.join(str(job_dir), "output.txt"),
            "-",
        ]
        entry = {"input": {"transport": "stdin"}}
        returncode, combined, _pgid, timed_out, _session_ref = delegate._spawn_backend(
            entry, argv, b"", str(job_dir), budget=10
        )
        assert not timed_out
        assert returncode == 0
        result = delegate.normalize_envelope(combined, "stub", "auto")
        assert result["outcome"] == "success"
        assert result["backend"] == "stub"
