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
import time
from pathlib import Path
from typing import ClassVar

import pytest
from _delegate_inproc import REPO_ROOT, delegate
from jsonschema import Draft202012Validator

# ---------------------------------------------------------------------------
# Job-record store (T007)
# ---------------------------------------------------------------------------


class TestJobStore:
    def test_fallback_pending_has_only_explicit_versioned_resolution(self):
        assert {
            "approve",
            "reject",
            "cancel",
        } == delegate.FALLBACK_PENDING_RESOLUTION_ACTIONS
        assert delegate.FALLBACK_PENDING_EXPIRES_AFTER_SECONDS is None

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

    def test_reap_restores_only_proven_spawned_continuation_to_pending(
        self, tmp_path, monkeypatch
    ):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        recovery = {
            "recovery_id": "recovery-claim",
            "next_tier": "flash",
            "next_index": 1,
            "requires_task_resubmission": True,
        }
        store.write_recovery(record["job_id"], recovery)

        def _claim(rec):
            rec["state"] = "queued"
            rec["fallback_pending"] = False
            rec["recovery"] = recovery
            rec["failure_summary"] = {"failure_class": "rate_limit"}
            rec["worker_pid"] = 999999999
            rec["dispatch"] = {
                "phase": "spawned",
                "attempt_id": "attempt-spawned",
                "job_version": rec["version"] + 1,
                "pid": 999999999,
                "pgid": 999999999,
                "process_start_identity": "spawned-identity",
            }
            rec["created_at"] = time.time() - delegate.WORKER_STARTUP_GRACE_SECONDS - 1
            return rec

        store.mutate(record["job_id"], _claim)
        Path(
            store.job_dir(record["job_id"]),
            delegate.process.WORKER_IDENTITY_FILENAME,
        ).write_text("spawned-identity", encoding="ascii")
        recovered = store.reap_if_dead(record["job_id"])

        assert recovered["state"] == "fallback_pending"
        assert recovered["recovery"] == recovery
        assert store.read_recovery(record["job_id"]) == recovery

    @pytest.mark.parametrize("phase", ("worker_owned", "backend_started"))
    def test_reap_marks_owned_or_started_disappearance_dispatch_unknown(
        self, tmp_path, monkeypatch, phase
    ):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        recovery = {
            "recovery_id": "recovery-owned",
            "next_tier": "flash",
            "next_index": 1,
            "requires_task_resubmission": True,
        }
        store.write_recovery(record["job_id"], recovery)

        def _claim(rec):
            rec["state"] = "running"
            rec["recovery"] = recovery
            rec["worker_pid"] = 999999999
            rec["dispatch"] = {
                "phase": phase,
                "attempt_id": "attempt-owned",
                "job_version": rec["version"] + 1,
                "pid": 999999999,
                "pgid": 999999999,
                "process_start_identity": "owned-identity",
            }
            rec["created_at"] = time.time() - delegate.WORKER_STARTUP_GRACE_SECONDS - 1
            return rec

        store.mutate(record["job_id"], _claim)
        recovered = store.reap_if_dead(record["job_id"])

        assert recovered["state"] == "dispatch_unknown"
        assert recovered["recovery"] == recovery
        assert recovered["recovery_audit"]["resumable"] is False
        assert store.read_recovery(record["job_id"]) == recovery

    def test_backend_pgid_ownership_clears_continuation_recovery(
        self, tmp_path, monkeypatch
    ):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        recovery = {
            "recovery_id": "recovery-owned",
            "next_tier": "flash",
            "next_index": 1,
            "requires_task_resubmission": True,
        }
        store.write_recovery(record["job_id"], recovery)
        store.mutate(
            record["job_id"],
            lambda rec: dict(
                rec,
                state="running",
                recovery=recovery,
                failure_summary={"failure_class": "rate_limit"},
            ),
        )

        delegate.process._make_pgid_persister(store, record["job_id"])(43210)
        owned = store.read(record["job_id"])

        assert owned["pgid"] == 43210
        assert "recovery" not in owned
        assert not Path(store.job_dir(record["job_id"]), "recovery.json").exists()

    def test_pgid_ownership_clears_recovery_on_a_terminal_record(
        self, tmp_path, monkeypatch
    ):
        """A cancel racing the spawn makes the job terminal before this runs.

        store.mutate silently refuses terminal records unless the mutator opts
        into re-entry, so without that opt-in the clear no-ops and the finished
        record keeps stale recovery/failure_summary that later readers trust.
        """
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        recovery = {
            "recovery_id": "recovery-owned",
            "next_tier": "flash",
            "next_index": 1,
            "requires_task_resubmission": True,
        }
        store.write_recovery(record["job_id"], recovery)
        store.mutate(
            record["job_id"],
            lambda rec: dict(
                rec,
                state="cancelled",
                recovery=recovery,
                failure_summary={"failure_class": "rate_limit"},
            ),
        )

        delegate.process._make_pgid_persister(store, record["job_id"])(43211)
        owned = store.read(record["job_id"])

        assert owned["state"] == "cancelled"
        assert "recovery" not in owned
        assert "failure_summary" not in owned


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

    def test_production_findings_satisfy_result_envelope_schema(self):
        schema_path = (
            REPO_ROOT
            / "specs"
            / "675-multi-agent-delegation"
            / "contracts"
            / "result-envelope.schema.json"
        )
        schema = json.loads(schema_path.read_text())
        envelope = {
            **self.VALID_ENVELOPE,
            "findings": [{"severity": "high", "text": "unsafe boundary"}],
        }
        raw = "```json\n" + json.dumps(envelope) + "\n```\n"

        result = delegate.normalize_envelope(raw, "codex", "auto")

        Draft202012Validator(schema).validate(result)

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
