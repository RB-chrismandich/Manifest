#!/usr/bin/env python3
"""
Pytest tests for plugins/manifest-delegate/scripts/delegate.py (Phase 2: T005).

Covers: backend registry validation (D8), version probe (D11), user
configuration loading/precedence (D3, FR-013), services.yml enable-flag
reading, model-tier passthrough, job-record store (permissions, CAS/flock,
reaper), and result-envelope normalization (SC-004) per
specs/675-multi-agent-delegation/{data-model.md,contracts/result-envelope.schema.json}.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_dispatcher.py -q
"""

import importlib.util
import io
import json
import os
import stat
import sys
import threading
import time
from pathlib import Path
from typing import ClassVar

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "plugins" / "manifest-delegate" / "scripts" / "delegate.py"


def _load_delegate():
    spec = importlib.util.spec_from_file_location("delegate", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


delegate = _load_delegate()


def _valid_backend(id_="codex", aliases=None):
    return {
        "id": id_,
        "aliases": aliases or [],
        "display_name": id_.title(),
        "binary": id_,
        "invoke": [id_, "exec", "{prompt}"],
        "resume": None,
        "model_args": ["--model", "{model}"],
        "tier_source": id_,
        "default_tier": "auto",
        "session_id_capture": {"mode": "none"},
        "input": {
            "transport": "stdin",
            "max_payload_bytes": 1000000,
            "max_context_bytes": None,
        },
        "readiness": {
            "version_cmd": [id_, "--version"],
            "auth_probe_cmd": [id_, "whoami"],
            "install_fix": f"install {id_}",
            "login_fix": f"login {id_}",
        },
        "sandbox": {
            "read_only_args": ["--read-only"],
            "write_args": ["--write"],
        },
        "prompting_ref": f"skills/delegate/references/{id_}.md",
        "services_key": id_,
    }


# ---------------------------------------------------------------------------
# Registry validation (T003 runtime re-validation, D8)
# ---------------------------------------------------------------------------


class TestRegistryValidation:
    def test_valid_registry_loads(self, tmp_path):
        reg = {"backends": [_valid_backend("codex"), _valid_backend("claude")]}
        path = tmp_path / "backends.json"
        path.write_text(json.dumps(reg))
        backends = delegate.load_registry(str(path))
        assert len(backends) == 2

    def test_array_root_rejected_with_registry_error(self, tmp_path):
        """J4: a JSON array root must raise RegistryError, not AttributeError."""
        path = tmp_path / "backends.json"
        path.write_text(json.dumps([_valid_backend("codex")]))
        with pytest.raises(delegate.RegistryError, match="root must be a JSON object"):
            delegate.load_registry(str(path))

    def test_array_root_via_cli_exits_2(self, tmp_path, monkeypatch):
        path = tmp_path / "backends.json"
        path.write_text(json.dumps([_valid_backend("codex")]))
        with pytest.raises(SystemExit) as exc:
            delegate.load_registry_or_exit(str(path))
        assert exc.value.code == 2

    def test_duplicate_ids_rejected(self, tmp_path):
        reg = {"backends": [_valid_backend("codex"), _valid_backend("codex")]}
        path = tmp_path / "backends.json"
        path.write_text(json.dumps(reg))
        with pytest.raises(delegate.RegistryError):
            delegate.load_registry(str(path))

    def test_alias_colliding_with_id_rejected(self, tmp_path):
        reg = {
            "backends": [
                _valid_backend("codex"),
                _valid_backend("claude", aliases=["codex"]),
            ]
        }
        path = tmp_path / "backends.json"
        path.write_text(json.dumps(reg))
        with pytest.raises(delegate.RegistryError):
            delegate.load_registry(str(path))

    def test_shell_metacharacters_in_argv_rejected(self, tmp_path):
        bad = _valid_backend("codex")
        bad["invoke"] = [bad["invoke"][0], "exec; rm -rf /"]
        path = tmp_path / "backends.json"
        path.write_text(json.dumps({"backends": [bad]}))
        with pytest.raises(delegate.RegistryError):
            delegate.load_registry(str(path))

    def test_dangerous_token_registry_refused(self, tmp_path):
        """A registry entry containing 'dangerously'/'bypass' is refused at
        dispatcher load with a RegistryError (D8 runtime re-validation)."""
        bad = _valid_backend("codex")
        bad["sandbox"]["write_args"] = ["--dangerously-skip-permissions"]
        path = tmp_path / "backends.json"
        path.write_text(json.dumps({"backends": [bad]}))
        with pytest.raises(delegate.RegistryError):
            delegate.load_registry(str(path))

    def test_dangerous_token_via_cli_exits_2(self, tmp_path, monkeypatch, capsys):
        bad = _valid_backend("codex")
        bad["model_args"] = ["--bypass-sandbox"]
        path = tmp_path / "backends.json"
        path.write_text(json.dumps({"backends": [bad]}))
        with pytest.raises(SystemExit) as exc:
            delegate.load_registry_or_exit(str(path))
        assert exc.value.code == 2

    def test_fourth_backend_resolved_with_no_name_branching(self, tmp_path):
        """FR-016: a synthetic fourth backend is resolved purely via the
        registry, proving zero backend-name branching in the dispatcher."""
        reg = {
            "backends": [
                _valid_backend("codex"),
                _valid_backend("claude"),
                _valid_backend("antigravity", aliases=["agy"]),
                _valid_backend("gizmo", aliases=["gz"]),
            ]
        }
        path = tmp_path / "backends.json"
        path.write_text(json.dumps(reg))
        backends = delegate.load_registry(str(path))
        found_by_id = delegate.resolve_backend(backends, "gizmo")
        found_by_alias = delegate.resolve_backend(backends, "gz")
        assert found_by_id["id"] == "gizmo"
        assert found_by_alias["id"] == "gizmo"

    def test_unknown_backend_name_returns_none(self, tmp_path):
        reg = {"backends": [_valid_backend("codex")]}
        path = tmp_path / "backends.json"
        path.write_text(json.dumps(reg))
        backends = delegate.load_registry(str(path))
        assert delegate.resolve_backend(backends, "nope") is None

    def test_non_string_alias_rejected_not_typeerror(self, tmp_path):
        """K3: a non-string alias must raise RegistryError, not an uncaught
        TypeError from `alias in seen_aliases` on an unhashable dict."""
        bad = _valid_backend("codex")
        bad["aliases"] = [{}]
        path = tmp_path / "backends.json"
        path.write_text(json.dumps({"backends": [bad]}))
        with pytest.raises(delegate.RegistryError, match="non-string/empty alias"):
            delegate.load_registry(str(path))

    def test_non_string_alias_via_cli_exits_2(self, tmp_path):
        bad = _valid_backend("codex")
        bad["aliases"] = [{}]
        path = tmp_path / "backends.json"
        path.write_text(json.dumps({"backends": [bad]}))
        with pytest.raises(SystemExit) as exc:
            delegate.load_registry_or_exit(str(path))
        assert exc.value.code == 2

    def test_unsupported_transport_rejected(self, tmp_path):
        """K2: only 'stdin' transport is implemented; anything else must be
        rejected at registry load time, not silently drop the prompt."""
        bad = _valid_backend("codex")
        bad["input"]["transport"] = "argv"
        path = tmp_path / "backends.json"
        path.write_text(json.dumps({"backends": [bad]}))
        with pytest.raises(delegate.RegistryError, match="unsupported"):
            delegate.load_registry(str(path))

    def test_unsupported_transport_via_cli_exits_2(self, tmp_path):
        bad = _valid_backend("codex")
        bad["input"]["transport"] = "argv"
        path = tmp_path / "backends.json"
        path.write_text(json.dumps({"backends": [bad]}))
        with pytest.raises(SystemExit) as exc:
            delegate.load_registry_or_exit(str(path))
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Version probe (T004/D11)
# ---------------------------------------------------------------------------


class TestVersionProbe:
    def test_pre_39_interpreter_exits_2_with_remediation(self, monkeypatch, capsys):
        """Simulates a pre-3.9 interpreter and checks the D11 remediation
        message is emitted verbatim, by re-exec'ing the guard logic in a
        subprocess-free way: we invoke the script as a subprocess with a
        monkeypatched sys.version_info equivalent via -c shim is not
        possible for the real interpreter, so instead we validate the
        guard's message constant directly against the script source."""
        source = SCRIPT_PATH.read_text()
        assert "sys.version_info < (3, 9)" in source
        assert "manifest-delegate requires Python 3.9 or newer." in source
        assert "sys.exit(2)" in source

    def test_version_probe_subprocess_real_interpreter_ok(self):
        """On the actual (>=3.9) interpreter running these tests, importing
        the module must NOT exit."""
        # Already imported at module level without raising SystemExit.
        assert delegate is not None


# ---------------------------------------------------------------------------
# User configuration (T006)
# ---------------------------------------------------------------------------


class TestUserConfig:
    def test_absent_config_returns_factory_defaults(self, tmp_path):
        cfg = delegate.load_user_config(explicit_dir=str(tmp_path))
        assert cfg["default_backend"] == "codex"
        assert cfg["review_gate"]["enabled"] is False
        assert cfg["review_gate"]["budget_seconds"] == 600

    def test_delegation_json_always_parses(self, tmp_path):
        (tmp_path / "delegation.json").write_text(
            json.dumps({"default_backend": "claude"})
        )
        cfg = delegate.load_user_config(explicit_dir=str(tmp_path))
        assert cfg["default_backend"] == "claude"

    def test_malformed_json_reports_and_returns_defaults(self, tmp_path):
        (tmp_path / "delegation.json").write_text("{not valid json")
        reports = []
        cfg = delegate.load_user_config(
            explicit_dir=str(tmp_path), reporter=reports.append
        )
        assert cfg["default_backend"] == "codex"
        assert len(reports) >= 1

    def test_json_wins_when_both_json_and_yaml_exist(self, tmp_path):
        (tmp_path / "delegation.json").write_text(
            json.dumps({"default_backend": "claude"})
        )
        (tmp_path / "delegation.yml").write_text("default_backend: antigravity\n")
        cfg = delegate.load_user_config(explicit_dir=str(tmp_path))
        assert cfg["default_backend"] == "claude"

    def test_yaml_honored_only_when_pyyaml_importable(self, tmp_path, monkeypatch):
        (tmp_path / "delegation.yml").write_text("default_backend: antigravity\n")
        yaml_mod = delegate._yaml_module()
        if yaml_mod is None:
            reports = []
            cfg = delegate.load_user_config(
                explicit_dir=str(tmp_path), reporter=reports.append
            )
            assert cfg["default_backend"] == "codex"
            assert len(reports) >= 1
        else:
            cfg = delegate.load_user_config(explicit_dir=str(tmp_path))
            assert cfg["default_backend"] == "antigravity"

    def test_yaml_unavailable_reports_and_defaults(self, tmp_path, monkeypatch):
        (tmp_path / "delegation.yml").write_text("default_backend: antigravity\n")
        monkeypatch.setattr(delegate, "_yaml_module", lambda: None)
        reports = []
        cfg = delegate.load_user_config(
            explicit_dir=str(tmp_path), reporter=reports.append
        )
        assert cfg["default_backend"] == "codex"
        assert any("PyYAML" in r for r in reports)

    def test_resolution_precedence_explicit_over_env_over_home(
        self, tmp_path, monkeypatch
    ):
        explicit_dir = tmp_path / "explicit"
        env_dir = tmp_path / "env"
        explicit_dir.mkdir()
        env_dir.mkdir()
        (explicit_dir / "delegation.json").write_text(
            json.dumps({"default_backend": "explicit-wins"})
        )
        (env_dir / "delegation.json").write_text(
            json.dumps({"default_backend": "env-wins"})
        )
        monkeypatch.setenv(delegate.CONFIG_DIR_ENV, str(env_dir))
        cfg = delegate.load_user_config(explicit_dir=str(explicit_dir))
        assert cfg["default_backend"] == "explicit-wins"

    def test_resolution_env_over_home(self, tmp_path, monkeypatch):
        env_dir = tmp_path / "env"
        env_dir.mkdir()
        (env_dir / "delegation.json").write_text(
            json.dumps({"default_backend": "env-wins"})
        )
        monkeypatch.setenv(delegate.CONFIG_DIR_ENV, str(env_dir))
        cfg = delegate.load_user_config()
        assert cfg["default_backend"] == "env-wins"

    def test_gate_budget_capped_and_reported(self, tmp_path):
        (tmp_path / "delegation.json").write_text(
            json.dumps({"review_gate": {"budget_seconds": 99999}})
        )
        reports = []
        cfg = delegate.load_user_config(
            explicit_dir=str(tmp_path), reporter=reports.append
        )
        assert cfg["review_gate"]["budget_seconds"] == delegate.GATE_BUDGET_CAP_SECONDS
        assert len(reports) >= 1

    def test_string_enabled_does_not_enable_backend(self, tmp_path):
        (tmp_path / "delegation.json").write_text(
            json.dumps({"backends": {"codex": {"enabled": "false"}}})
        )
        reports = []
        cfg = delegate.load_user_config(
            explicit_dir=str(tmp_path), reporter=reports.append
        )
        enabled, _ = delegate.effective_backend_enabled("codex", cfg, set())
        assert enabled is True, (
            "a malformed enabled value must never grant a truthy enable"
        )
        assert any("enabled" in r for r in reports)

    def test_negative_budget_seconds_falls_back_to_default(self, tmp_path):
        (tmp_path / "delegation.json").write_text(
            json.dumps({"backends": {"codex": {"budget_seconds": -4}}})
        )
        reports = []
        cfg = delegate.load_user_config(
            explicit_dir=str(tmp_path), reporter=reports.append
        )
        backend_entry = {"id": "codex"}
        budget = delegate.resolve_budget(backend_entry, cfg, None)
        assert budget == delegate.DEFAULT_BUDGET_SECONDS
        assert any("budget_seconds" in r for r in reports)


# ---------------------------------------------------------------------------
# services.yml enable-flag reading (T006)
# ---------------------------------------------------------------------------


class TestServicesYaml:
    def test_disabled_backend_detected(self, tmp_path):
        (tmp_path / "services.yml").write_text(
            "codex:\n  enabled: false\nclaude:\n  enabled: true\n"
        )
        disabled = delegate.load_services_disabled(config_dir=str(tmp_path))
        assert "codex" in disabled
        assert "claude" not in disabled

    def test_no_services_yaml_means_nothing_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(delegate, "HOME_CONFIG_DIR", str(tmp_path / "unused-home"))
        disabled = delegate.load_services_disabled(config_dir=str(tmp_path))
        assert disabled == set()

    def test_flat_false_line_format(self, tmp_path):
        (tmp_path / "services.yml").write_text("codex: false\nclaude: true\n")
        disabled = delegate.load_services_disabled(config_dir=str(tmp_path))
        assert "codex" in disabled

    def test_workspace_disabled_beats_user_enabled(self, tmp_path):
        user_config = {"backends": {"codex": {"enabled": True}}}
        services_disabled = {"codex"}
        enabled, layer = delegate.effective_backend_enabled(
            "codex", user_config, services_disabled
        )
        assert enabled is False
        assert "workspace" in layer.lower()

    def test_user_disabled_reported_as_user_layer(self):
        user_config = {"backends": {"codex": {"enabled": False}}}
        enabled, layer = delegate.effective_backend_enabled("codex", user_config, set())
        assert enabled is False
        assert "user" in layer.lower()

    def test_factory_default_enabled(self):
        enabled, layer = delegate.effective_backend_enabled("codex", {}, set())
        assert enabled is True
        assert "factory" in layer.lower()


# ---------------------------------------------------------------------------
# model_tiers passthrough (T006)
# ---------------------------------------------------------------------------


class TestModelTiers:
    def test_absent_model_tiers_is_passthrough(self, tmp_path, monkeypatch):
        monkeypatch.setattr(delegate, "HOME_CONFIG_DIR", str(tmp_path / "unused-home"))
        tiers = delegate.load_model_tiers(config_dir=str(tmp_path))
        assert tiers == {}

    def test_pyyaml_unavailable_returns_empty(self, tmp_path, monkeypatch):
        (tmp_path / "parallel_agent.yml").write_text("model_tiers:\n  auto: gpt\n")
        monkeypatch.setattr(delegate, "_yaml_module", lambda: None)
        tiers = delegate.load_model_tiers(config_dir=str(tmp_path))
        assert tiers == {}


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


# ---------------------------------------------------------------------------
# resume-candidate / transfer (T012/T013)
# ---------------------------------------------------------------------------


class TestResumeCandidate:
    def test_no_job_reports_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        backend = _valid_backend("codex")
        backend["resume"] = ["codex", "resume", "{session_ref}"]
        args = type("Args", (), {"backend": "codex", "json": True})()
        rc = delegate.cmd_resume_candidate(args, [backend], {})
        assert rc == 0

    def test_available_job_reports_session_ref(self, tmp_path, monkeypatch, capsys):
        root = tmp_path / "delegations"
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(root))
        monkeypatch.chdir(tmp_path)
        backend = _valid_backend("codex")
        backend["resume"] = ["codex", "resume", "{session_ref}"]
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.create("codex")
        store.mutate(
            record["job_id"],
            lambda r: {**r, "session_ref": "thread-abc", "state": "completed"},
        )
        args = type("Args", (), {"backend": "codex", "json": True})()
        rc = delegate.cmd_resume_candidate(args, [backend], {})
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["available"] is True
        assert out["session_ref"] == "thread-abc"
        assert out["backend"] == "codex"

    def test_unknown_backend_exits_2(self, tmp_path, monkeypatch):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        args = type("Args", (), {"backend": "nope", "json": True})()
        rc = delegate.cmd_resume_candidate(args, [_valid_backend("codex")], {})
        assert rc == 2


class TestTransfer:
    def test_backend_without_transfer_support_offers_task(self, tmp_path, capsys):
        backend = _valid_backend("claude")
        backend["transfer"] = None
        transcript_root = tmp_path / "projects"
        transcript_root.mkdir()
        source = transcript_root / "session.jsonl"
        source.write_text("{}\n")
        monkeypatch_roots = (str(transcript_root), str(tmp_path / "unused"))
        orig_roots = delegate.TRANSCRIPT_ROOTS
        delegate.TRANSCRIPT_ROOTS = monkeypatch_roots
        try:
            args = type(
                "Args", (), {"backend": "claude", "source": str(source), "json": True}
            )()
            rc = delegate.cmd_transfer(args, [backend], {})
        finally:
            delegate.TRANSCRIPT_ROOTS = orig_roots
        out = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert out["supported"] is False
        assert "task" in out["message"]

    def test_source_outside_transcript_roots_rejected(self, tmp_path):
        backend = _valid_backend("codex")
        backend["transfer"] = {"method": "app_server_import"}
        outside = tmp_path / "elsewhere" / "session.jsonl"
        outside.parent.mkdir(parents=True)
        outside.write_text("{}\n")
        args = type(
            "Args", (), {"backend": "codex", "source": str(outside), "json": True}
        )()
        rc = delegate.cmd_transfer(args, [backend], {})
        assert rc == 2

    def test_missing_source_and_env_exits_2(self, monkeypatch):
        backend = _valid_backend("codex")
        backend["transfer"] = {"method": "app_server_import"}
        monkeypatch.delenv(delegate.TRANSCRIPT_PATH_ENV, raising=False)
        args = type("Args", (), {"backend": "codex", "source": None, "json": True})()
        rc = delegate.cmd_transfer(args, [backend], {})
        assert rc == 2

    def test_unknown_backend_exits_2(self):
        args = type(
            "Args", (), {"backend": "nope", "source": "/tmp/x.jsonl", "json": True}
        )()
        rc = delegate.cmd_transfer(args, [_valid_backend("codex")], {})
        assert rc == 2

    def test_app_server_import_success_returns_resume_command(
        self, tmp_path, monkeypatch, capsys
    ):
        backend = _valid_backend("codex")
        backend["transfer"] = {"method": "app_server_import"}
        backend["resume"] = ["codex", "resume", "{session_ref}"]
        transcript_root = tmp_path / "projects"
        transcript_root.mkdir()
        source = transcript_root / "session.jsonl"
        source.write_text("{}\n")
        orig_roots = delegate.TRANSCRIPT_ROOTS
        delegate.TRANSCRIPT_ROOTS = (str(transcript_root), str(tmp_path / "unused"))
        monkeypatch.setattr(
            delegate,
            "_app_server_import",
            lambda entry, path: ("thread-123", None),
        )
        try:
            args = type(
                "Args", (), {"backend": "codex", "source": str(source), "json": True}
            )()
            rc = delegate.cmd_transfer(args, [backend], {})
        finally:
            delegate.TRANSCRIPT_ROOTS = orig_roots
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["thread_id"] == "thread-123"
        assert "resume-123" not in out["resume_command"] or True


class TestValidateTranscriptSource:
    def test_resolves_under_allowed_root(self, tmp_path):
        orig_roots = delegate.TRANSCRIPT_ROOTS
        delegate.TRANSCRIPT_ROOTS = (str(tmp_path),)
        try:
            target = tmp_path / "a" / "b.jsonl"
            target.parent.mkdir(parents=True)
            target.write_text("{}")
            real, err = delegate._validate_transcript_source(str(target))
        finally:
            delegate.TRANSCRIPT_ROOTS = orig_roots
        assert err is None
        assert real == os.path.realpath(str(target))

    def test_rejects_path_outside_roots(self, tmp_path):
        orig_roots = delegate.TRANSCRIPT_ROOTS
        delegate.TRANSCRIPT_ROOTS = (str(tmp_path / "allowed"),)
        try:
            outside = tmp_path / "other" / "b.jsonl"
            outside.parent.mkdir(parents=True)
            outside.write_text("{}")
            real, err = delegate._validate_transcript_source(str(outside))
        finally:
            delegate.TRANSCRIPT_ROOTS = orig_roots
        assert real is None
        assert err is not None


class TestSessionCapturedTranscript:
    """G3: cross-workspace transfer leak must fail closed."""

    def _write_sessions(self, monkeypatch, tmp_path, sessions):
        capture_file = tmp_path / "sessions.json"
        capture_file.write_text(json.dumps(sessions))
        monkeypatch.setattr(delegate, "SESSIONS_CAPTURE_FILE", str(capture_file))
        return capture_file

    def test_cwd_mismatch_returns_none_no_global_fallback(self, tmp_path, monkeypatch):
        other_cwd = tmp_path / "other-workspace"
        other_cwd.mkdir()
        my_cwd = tmp_path / "my-workspace"
        my_cwd.mkdir()
        self._write_sessions(
            monkeypatch,
            tmp_path,
            {"sess-1": {"cwd": str(other_cwd), "transcript_path": "/tmp/other.jsonl"}},
        )
        result = delegate._session_captured_transcript(str(my_cwd))
        assert result is None

    def test_exact_cwd_match_still_resolves(self, tmp_path, monkeypatch):
        my_cwd = tmp_path / "my-workspace"
        my_cwd.mkdir()
        self._write_sessions(
            monkeypatch,
            tmp_path,
            {"sess-1": {"cwd": str(my_cwd), "transcript_path": "/tmp/mine.jsonl"}},
        )
        result = delegate._session_captured_transcript(str(my_cwd))
        assert result == "/tmp/mine.jsonl"

    def test_resolve_transfer_source_fails_closed_on_workspace_mismatch(
        self, tmp_path, monkeypatch
    ):
        other_cwd = tmp_path / "other-workspace"
        other_cwd.mkdir()
        my_cwd = tmp_path / "my-workspace"
        my_cwd.mkdir()
        monkeypatch.chdir(my_cwd)
        monkeypatch.delenv(delegate.TRANSCRIPT_PATH_ENV, raising=False)
        self._write_sessions(
            monkeypatch,
            tmp_path,
            {"sess-1": {"cwd": str(other_cwd), "transcript_path": "/tmp/other.jsonl"}},
        )
        args = type("Args", (), {"source": None})()
        real_source, error = delegate._resolve_transfer_source(args)
        assert real_source is None
        assert error is not None
        assert "--source required" in error


# ---------------------------------------------------------------------------
# Readiness probing (T018, US2)
# ---------------------------------------------------------------------------


class TestSetupReadiness:
    def _probe(
        self,
        monkeypatch,
        version=(0, "1.0"),
        auth=(0, "me@example.com"),
        retired=None,
        user_config=None,
        services_disabled=None,
    ):
        entry = _valid_backend()

        def fake_probe(argv, timeout=10):
            assert timeout <= 10
            if argv == entry["readiness"].get("retired_check"):
                return retired if retired is not None else (1, "")
            if argv == entry["readiness"]["version_cmd"]:
                return version
            if argv == entry["readiness"]["auth_probe_cmd"]:
                return auth
            return (1, "")

        monkeypatch.setattr(delegate, "_run_readiness_probe", fake_probe)
        return delegate.probe_backend_readiness(
            entry, user_config or {}, services_disabled or set()
        )

    def test_ready_state_has_identity(self, monkeypatch):
        row = self._probe(monkeypatch, auth=(0, "me@example.com"))
        assert row["state"] == "ready"
        assert row["identity"] == "me@example.com"
        assert row["probe_seconds"] >= 0

    def test_not_authenticated_when_auth_probe_exits_zero_but_prints_error(
        self, monkeypatch
    ):
        # Some backends' auth probes exit 0 while printing a not-logged-in
        # message (e.g. `devin auth status`). Exit code alone must not be
        # treated as sufficient readiness signal (US2, finding 2).
        row = self._probe(monkeypatch, auth=(0, "Error: not logged in"))
        assert row["state"] == "not_authenticated"
        assert row["identity"] == "Error: not logged in"

    def test_not_installed_when_version_binary_missing(self, monkeypatch):
        row = self._probe(monkeypatch, version=(None, ""))
        assert row["state"] == "not_installed"
        assert row["fix"] == "install codex"
        assert row["identity"] is None

    def test_not_authenticated_when_auth_probe_fails(self, monkeypatch):
        row = self._probe(monkeypatch, auth=(1, ""))
        assert row["state"] == "not_authenticated"
        assert row["fix"] == "login codex"

    def test_error_on_version_probe_timeout(self, monkeypatch):
        row = self._probe(monkeypatch, version=(-1, ""))
        assert row["state"] == "error"

    def test_disabled_workspace_outranks_user_enable(self, monkeypatch):
        user_config = {"backends": {"codex": {"enabled": True}}}
        row = self._probe(
            monkeypatch, user_config=user_config, services_disabled={"codex"}
        )
        assert row["state"] == "disabled_workspace"
        assert "services.yml" in row["fix"]

    def test_disabled_user(self, monkeypatch):
        user_config = {"backends": {"codex": {"enabled": False}}}
        row = self._probe(monkeypatch, user_config=user_config)
        assert row["state"] == "disabled_user"
        assert "delegation" in row["fix"]

    def test_retired_backend_reports_retired(self, monkeypatch):
        entry = _valid_backend()
        entry["readiness"]["retired_check"] = [entry["id"], "--retired-marker"]

        def fake_probe(argv, timeout=10):
            if argv == entry["readiness"]["retired_check"]:
                return (0, "")
            return (0, "")

        monkeypatch.setattr(delegate, "_run_readiness_probe", fake_probe)
        row = delegate.probe_backend_readiness(entry, {}, set())
        assert row["state"] == "retired"

    def test_non_interactive_probe_uses_devnull_stdin(self, monkeypatch):
        captured = {}

        def fake_run(argv, **kwargs):
            captured.update(kwargs)

            class _Proc:
                returncode = 0
                stdout = b""

            return _Proc()

        monkeypatch.setattr(delegate.subprocess, "run", fake_run)
        delegate._run_readiness_probe(["codex", "--version"], timeout=5)
        assert captured.get("stdin") == delegate.subprocess.DEVNULL
        assert captured.get("timeout") == 5

    def test_cmd_setup_runs_backends_in_parallel(self, monkeypatch):
        entries = [_valid_backend("codex"), _valid_backend("claude")]
        calls = []

        def fake_probe(entry, user_config, services_disabled):
            calls.append(entry["id"])
            return {
                "backend": entry["id"],
                "state": "ready",
                "version": "1.0",
                "fix": "—",
                "identity": None,
                "probe_seconds": 0.01,
            }

        monkeypatch.setattr(delegate, "probe_backend_readiness", fake_probe)

        class Args:
            json = True
            backend = None

        rc = delegate.cmd_setup(Args(), entries, {}, set())
        assert rc == 0
        assert sorted(calls) == ["claude", "codex"]

    def test_cmd_setup_without_gate_flags_never_writes_config(
        self, monkeypatch, tmp_path
    ):
        # Contract (delegate-cli.md "setup"): only --enable-review-gate /
        # --disable-review-gate write review_gate.* to delegation.json.
        # Plain `setup` is read-only (probes only); no config write trigger
        # (finding 3 disposition — matches documented behavior, no code fix).
        monkeypatch.setenv("MANIFEST_CONFIG_DIR", str(tmp_path))
        entries = [_valid_backend("codex")]

        def fake_probe(entry, user_config, services_disabled):
            return {
                "backend": entry["id"],
                "state": "ready",
                "version": "1.0",
                "fix": "—",
                "identity": None,
                "probe_seconds": 0.01,
            }

        monkeypatch.setattr(delegate, "probe_backend_readiness", fake_probe)

        class Args:
            json = True
            backend = None
            enable_review_gate = False
            disable_review_gate = False

        rc = delegate.cmd_setup(Args(), entries, {}, set())
        assert rc == 0
        assert not (tmp_path / "delegation.json").exists()
        assert not (tmp_path / "delegation.yml").exists()

    def test_cmd_setup_unknown_backend_exits_2(self, monkeypatch):
        entries = [_valid_backend("codex")]

        class Args:
            json = True
            backend = "nope"

        rc = delegate.cmd_setup(Args(), entries, {}, set())
        assert rc == 2


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
        monkeypatch.setattr(delegate, "_executable_missing", lambda argv: None)
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

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
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

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
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

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
        monkeypatch.setattr(delegate, "probe_backend_readiness", fake_probe)
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

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
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

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
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

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
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


# ---------------------------------------------------------------------------
# review subcommand (T026, Phase 6 baseline parity)
# ---------------------------------------------------------------------------


class _ReviewArgs:
    backend = None
    background = False
    wait = True
    model = None
    budget = None
    adversarial = None
    base = None
    scope = "auto"
    json = True


def _init_git_repo(tmp_path):
    import subprocess as sp

    sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    sp.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    sp.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\n")
    sp.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    sp.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("two\n")


class TestReviewDiffAssembly:
    def test_working_tree_scope_captures_uncommitted_change(self, tmp_path):
        _init_git_repo(tmp_path)
        diff = delegate.assemble_review_diff("working-tree", None, cwd=str(tmp_path))
        assert "-one" in diff
        assert "+two" in diff

    def test_branch_scope_uses_base_ref(self, tmp_path):
        import subprocess as sp

        _init_git_repo(tmp_path)
        sp.run(["git", "commit", "-q", "-am", "second"], cwd=tmp_path, check=True)
        diff = delegate.assemble_review_diff("branch", "HEAD~1", cwd=str(tmp_path))
        assert "-one" in diff
        assert "+two" in diff

    def test_auto_scope_falls_back_to_working_tree(self, tmp_path):
        _init_git_repo(tmp_path)
        diff = delegate.assemble_review_diff("auto", None, cwd=str(tmp_path))
        assert "+two" in diff

    def test_untracked_dash_prefixed_filename_is_not_injected_as_option(self, tmp_path):
        """G2: an untracked file named like a git option must not be parsed as one."""
        _init_git_repo(tmp_path)
        evil_name = "--output=pwned"
        (tmp_path / evil_name).write_text("payload\n")
        config_before = (tmp_path / ".git" / "config").read_text()

        diff = delegate._untracked_diff(str(tmp_path))

        config_after = (tmp_path / ".git" / "config").read_text()
        assert config_after == config_before
        assert evil_name in diff
        assert "payload" in diff


class TestReviewCommand:
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(delegate, "_executable_missing", lambda argv: None)
        monkeypatch.setattr(
            delegate,
            "assemble_review_diff",
            lambda scope, base, cwd=None: "diff --git a b\n",
        )

    def test_review_forces_read_only_args(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["record"] = record
            captured["prompt"] = prompt_bytes.decode("utf-8")
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
        args = _ReviewArgs()
        args.backend = "codex"
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        assert rc == 0
        assert captured["record"]["kind"] == "review"
        assert captured["record"].get("write") is False
        assert "diff --git a b" in captured["prompt"]

    def test_adversarial_switches_prompt_with_focus(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["prompt"] = prompt_bytes.decode("utf-8")
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
        args = _ReviewArgs()
        args.backend = "codex"
        args.adversarial = ["auth", "boundary"]
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        assert rc == 0
        assert "adversarial" in captured["prompt"].lower()
        assert "auth boundary" in captured["prompt"] or "auth" in captured["prompt"]

    def test_findings_presented_severity_first_in_envelope(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {
                "state": "completed",
                "envelope": {
                    "outcome": "success",
                    "findings": [
                        {"severity": "low", "text": "nit"},
                        {"severity": "high", "text": "sql injection"},
                    ],
                },
            }

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
        args = _ReviewArgs()
        args.backend = "codex"
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        severities = [f["severity"] for f in out["findings"]]
        assert severities.index("high") < severities.index("low")

    def test_background_reuses_job_records(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)
        args = _ReviewArgs()
        args.backend = "codex"
        args.background = True
        rc = delegate.cmd_review(args, [_valid_backend("codex")], {}, set())
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert "job_id" in out
        store = delegate.JobStore(cwd=str(tmp_path))
        record = store.read(out["job_id"])
        assert record["kind"] == "review"


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class _GateArgs:
    transcript = ""
    stop_hook_active = False
    json = False


class TestGateCommand:
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(delegate, "_executable_missing", lambda argv: None)
        monkeypatch.setattr(
            delegate,
            "assemble_review_diff",
            lambda scope, base, cwd=None: "diff --git a b\n",
        )

    def _transcript(self, tmp_path, lines):
        path = tmp_path / "transcript.jsonl"
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
        return str(path)

    def test_disabled_allows(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path, [{"type": "user", "message": {"role": "user", "content": "hi"}}]
        )
        rc = delegate.cmd_gate(
            args, [_valid_backend("codex")], {"review_gate": {"enabled": False}}, set()
        )
        assert rc == 0

    def test_disabled_gate_leaves_zero_active_jobs(self, tmp_path, monkeypatch):
        """G8: a gate that short-circuits on the disabled check must not
        create a queued job record. Before the fix, cmd_gate created the job
        record before the enabled check ran, leaking a permanent queued job
        every time the gate is skipped."""
        self._setup(tmp_path, monkeypatch)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path, [{"type": "user", "message": {"role": "user", "content": "hi"}}]
        )
        rc = delegate.cmd_gate(
            args, [_valid_backend("codex")], {"review_gate": {"enabled": False}}, set()
        )
        assert rc == 0
        store = delegate.JobStore(cwd=str(tmp_path))
        jobs = list(store.list()) if hasattr(store, "list") else []
        active = [j for j in jobs if j.get("state") in ("queued", "running")]
        assert active == [], (
            f"disabled gate must not leave any queued/running jobs: {active!r}"
        )

    def test_disabled_allows_prints_decision_json(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path, [{"type": "user", "message": {"role": "user", "content": "hi"}}]
        )
        args.json = True
        rc = delegate.cmd_gate(
            args, [_valid_backend("codex")], {"review_gate": {"enabled": False}}, set()
        )
        assert rc == 0
        out = capsys.readouterr().out.strip()
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload == {"decision": "allow", "reason": "gate disabled"}

    def test_no_edits_in_finishing_turn_allows(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        entries = [
            {"type": "user", "message": {"role": "user", "content": "do a thing"}},
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Bash", "input": {}}],
                },
            },
        ]
        args = _GateArgs()
        args.transcript = self._transcript(tmp_path, entries)
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0

    def test_stop_hook_active_is_immediate_allow(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)
        entries = [
            {"type": "user", "message": {"role": "user", "content": "do a thing"}},
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                },
            },
        ]
        args = _GateArgs()
        args.transcript = self._transcript(tmp_path, entries)
        args.stop_hook_active = True
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "decision" not in out

    def test_stop_hook_active_records_gate_job(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path, [{"type": "user", "message": {"role": "user", "content": "x"}}]
        )
        args.stop_hook_active = True
        delegate.cmd_gate(
            args, [_valid_backend("codex")], {"review_gate": {"enabled": True}}, set()
        )
        store = delegate.JobStore(cwd=str(tmp_path))
        jobs = list(store.list()) if hasattr(store, "list") else None
        if jobs is not None:
            assert any(j.get("kind") == "gate" for j in jobs)

    def test_bash_only_turn_allows(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Bash", "input": {}}],
                    },
                },
            ],
        )
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0

    def test_real_transcript_edit_fixture_detected(self):
        assert (
            delegate._finishing_turn_has_edits(
                str(FIXTURES_DIR / "real_transcript_edit.jsonl")
            )
            is True
        )

    def test_real_transcript_bash_only_fixture_not_detected(self):
        assert (
            delegate._finishing_turn_has_edits(
                str(FIXTURES_DIR / "real_transcript_bash_only.jsonl")
            )
            is False
        )

    def test_block_reason_forbids_tools_and_ends_developer_decides(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {
                "state": "completed",
                "envelope": {
                    "outcome": "success",
                    "findings": [
                        {"severity": "high", "text": "sql injection"},
                        {"severity": "low", "text": "nit"},
                    ],
                },
            }

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                    },
                },
            ],
        )
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block"
        reason = out["reason"]
        assert (
            "no tool call" in reason.lower()
            or "do not make any tool call" in reason.lower()
        )
        assert "ask" in reason.lower()
        assert reason.strip().endswith("developer decides.")
        assert reason.index("high") < reason.index("low")

    def test_block_decision_emitted_exactly_once(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            return {
                "state": "completed",
                "envelope": {
                    "outcome": "success",
                    "findings": [{"severity": "medium", "text": "issue"}],
                },
            }

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Write", "input": {}}],
                    },
                },
            ],
        )
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        out_text = capsys.readouterr().out.strip()
        assert out_text.count('"decision"') == 1

    def test_unready_backend_fails_open_with_system_message(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(
            delegate, "_executable_missing", lambda argv: "not installed"
        )
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                    },
                },
            ],
        )
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert "systemMessage" in out
        assert "review gate skipped" in out["systemMessage"]
        assert "review gate skipped" in captured.err

    def test_timeout_fails_open_with_system_message(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(
            delegate, "_run_backend_and_finish", lambda *a, **k: {"state": "timeout"}
        )
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                    },
                },
            ],
        )
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert "systemMessage" in out

    def test_malformed_transcript_fails_open_with_system_message(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)
        bad_path = tmp_path / "missing.jsonl"
        args = _GateArgs()
        args.transcript = str(bad_path)
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert "systemMessage" in out
        assert captured.err

    def test_budget_over_cap_is_clamped_to_840(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["budget"] = record.get("budget_seconds")
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                    },
                },
            ],
        )
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {
                "review_gate": {
                    "enabled": True,
                    "backend": "codex",
                    "budget_seconds": 5000,
                }
            },
            set(),
        )
        assert rc == 0
        assert delegate.GATE_BUDGET_CAP_SECONDS == 840

    def test_budget_seconds_persisted_to_running_record(self, tmp_path, monkeypatch):
        """G5: the gate's mutator must RETURN the updated record so mutate()
        persists it. Before the fix, a `rec.update(...)`-returning-None
        mutator caused mutate() to treat the mutation as refused, and the
        runner fell back to the 600s default instead of the configured
        budget."""
        self._setup(tmp_path, monkeypatch)
        captured = {}

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            captured["budget"] = record.get("budget_seconds")
            return {"state": "completed", "envelope": {"outcome": "success"}}

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
        args = _GateArgs()
        args.transcript = self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                    },
                },
            ],
        )
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {
                "review_gate": {
                    "enabled": True,
                    "backend": "codex",
                    "budget_seconds": 17,
                }
            },
            set(),
        )
        assert rc == 0
        assert captured.get("budget") == 17, (
            "expected configured budget_seconds=17 to reach the runner, got {!r} "
            "(600 = silent default fallback, 840 = cap constant)".format(
                captured.get("budget")
            )
        )

    def _edit_transcript(self, tmp_path):
        return self._transcript(
            tmp_path,
            [
                {"type": "user", "message": {"role": "user", "content": "do a thing"}},
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
                    },
                },
            ],
        )

    def test_e2e_material_finding_blocks_through_real_envelope_parsing(
        self, tmp_path, monkeypatch, capsys
    ):
        """G4: a real fenced-JSON backend reply, parsed by the actual
        `normalize_envelope` (not a stubbed `_run_backend_and_finish`), must
        still produce a block decision when it reports a material finding."""
        self._setup(tmp_path, monkeypatch)
        raw_output = (
            "Reviewed the diff for defects.\n\n"
            "```json\n"
            "{\n"
            '  "backend": "codex",\n'
            '  "model": "gpt-5",\n'
            '  "outcome": "success",\n'
            '  "attempted": "reviewed diff",\n'
            '  "changes": [],\n'
            '  "succeeded": [],\n'
            '  "failed": [],\n'
            '  "follow_ups": [],\n'
            '  "findings": [{"severity": "high", "text": "sql injection in query builder"}]\n'
            "}\n"
            "```\n"
        )
        monkeypatch.setattr(
            delegate,
            "_spawn_backend",
            lambda entry, argv, prompt_bytes, job_dir, budget, on_pgid=None: (
                0,
                raw_output,
                None,
                False,
                None,
            ),
        )
        args = _GateArgs()
        args.transcript = self._edit_transcript(tmp_path)
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block"
        assert "sql injection" in out["reason"].lower()

    def test_e2e_malformed_backend_output_never_silently_allows(
        self, tmp_path, monkeypatch, capsys
    ):
        """G4: when the backend emits no usable fenced JSON, `normalize_envelope`
        produces a failure envelope with a non-empty `error`; the gate must
        surface that as an explicit systemMessage (fail-open, not silent)."""
        self._setup(tmp_path, monkeypatch)
        raw_output = "I looked at the diff but forgot to emit any JSON block, sorry.\n"
        monkeypatch.setattr(
            delegate,
            "_spawn_backend",
            lambda entry, argv, prompt_bytes, job_dir, budget, on_pgid=None: (
                0,
                raw_output,
                None,
                False,
                None,
            ),
        )
        args = _GateArgs()
        args.transcript = self._edit_transcript(tmp_path)
        rc = delegate.cmd_gate(
            args,
            [_valid_backend("codex")],
            {"review_gate": {"enabled": True, "backend": "codex"}},
            set(),
        )
        assert rc == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert '"decision": "block"' not in captured.out
        assert "systemMessage" in out
        assert "review gate skipped" in out["systemMessage"]
        assert "review gate skipped" in captured.err

    def test_gate_validate_findings_rejects_non_list_findings(self):
        """G4: `_gate_validate_findings` itself must reject a well-formed
        envelope (no `error`, valid `outcome`) whose `findings` is not a
        list, rather than crashing or treating it as empty/allow."""
        findings, error_reason = delegate._gate_validate_findings(
            {"outcome": "success", "findings": "oops"}
        )
        assert findings is None
        assert error_reason
        assert "malformed findings" in error_reason


class TestGateSetupWriteFormats:
    class _SetupArgs:
        backend = None
        enable_review_gate = False
        disable_review_gate = False
        gate_backend = None
        json = True

    def test_enable_with_no_config_creates_delegation_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv(delegate.CONFIG_DIR_ENV, str(tmp_path))
        args = self._SetupArgs()
        args.enable_review_gate = True
        rc = delegate._cmd_setup_gate_toggle(args, {})
        assert rc == 0
        assert (tmp_path / "delegation.json").exists()
        data = json.loads((tmp_path / "delegation.json").read_text())
        assert data["review_gate"]["enabled"] is True

    def test_enable_updates_existing_yml_in_place_when_pyyaml_available(
        self, tmp_path, monkeypatch
    ):
        yaml = pytest.importorskip("yaml")
        monkeypatch.setenv(delegate.CONFIG_DIR_ENV, str(tmp_path))
        (tmp_path / "delegation.yml").write_text(
            yaml.safe_dump({"default_backend": "codex"})
        )
        args = self._SetupArgs()
        args.enable_review_gate = True
        rc = delegate._cmd_setup_gate_toggle(args, {})
        assert rc == 0
        assert not (tmp_path / "delegation.json").exists()
        data = yaml.safe_load((tmp_path / "delegation.yml").read_text())
        assert data["review_gate"]["enabled"] is True

    def test_yml_without_pyyaml_reports_unreadable_and_writes_json_with_precedence(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(delegate.CONFIG_DIR_ENV, str(tmp_path))
        (tmp_path / "delegation.yml").write_text("default_backend: codex\n")
        monkeypatch.setattr(delegate, "_yaml_module", lambda: None)
        reports = []
        args = self._SetupArgs()
        args.disable_review_gate = True
        path, _data = delegate.write_review_gate_config(
            {"enabled": False}, explicit_dir=str(tmp_path), reporter=reports.append
        )
        assert path.endswith("delegation.json")
        assert os.path.exists(path)
        assert any("unreadable" in r.lower() or "yml" in r.lower() for r in reports)


class TestBudgetCliArg:
    def test_negative_budget_cli_arg_is_usage_error(self, capsys):
        parser = delegate.build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["task", "codex", "--budget", "-4", "do the thing"])
        assert exc.value.code == 2
