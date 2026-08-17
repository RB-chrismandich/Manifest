"""SC-004 fault-injection matrix for the delegate dispatcher.

Every dispatcher failure path must be explicit (states what happened),
attributed (names the backend/limit/layer responsible), and actionable
(names what to check or do next). This file drives one test per fault in
the matrix via delegate.py's public functions only; delegate.py itself is
never modified or read in full (see module docstring conventions in
test_delegate_dispatcher.py, which this file mirrors).
"""

import importlib.util
import json
import stat
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "plugins" / "manifest-delegate" / "scripts" / "delegate.py"


def _load_delegate():
    spec = importlib.util.spec_from_file_location("delegate_faults", SCRIPT_PATH)
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
        "sandbox": {"read_only_args": ["--read-only"], "write_args": ["--write"]},
        "prompting_ref": f"skills/delegate/references/{id_}.md",
        "services_key": id_,
    }


class _TaskArgs:
    backend = None
    background = False
    wait = True
    write = False
    model = None
    budget = None
    resume = None
    resume_last = False
    fresh = False
    second_opinion = False
    of = None
    task_file = None
    prompt_file = None
    prompt = "do the thing"
    json = True
    recovery_id = None


def _assert_explicit_attributed_actionable(
    message, backend_id=None, actionable_markers=()
):
    """Shared SC-004 assertion: message is non-empty/specific, names the
    backend/limit/layer responsible, and points at what to check/do next.
    """
    assert message and message.strip(), "failure message must not be empty"
    if backend_id is not None:
        assert backend_id in message, (
            f"message must attribute the failure to backend {backend_id!r}: {message!r}"
        )
    assert actionable_markers, "must supply at least one actionable marker to check for"
    assert any(marker in message for marker in actionable_markers), (
        f"message must be actionable (contain one of {actionable_markers!r}): {message!r}"
    )


def _make_args(tmp_path, monkeypatch, backend="codex"):
    monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
    monkeypatch.chdir(tmp_path)
    args = _TaskArgs()
    args.backend = backend
    return args


# ---------------------------------------------------------------------------
# 1. unknown backend
# ---------------------------------------------------------------------------


class _FallbackPendingMixin:
    def _first_pending(self, tmp_path, monkeypatch, capsys):
        args = _make_args(tmp_path, monkeypatch)
        args.model = "advanced"
        args.model_chain = "flash"
        args.model_fallback = "confirm"
        args.skill_path = None
        args.expected_version = None
        args.fallback_decision = None
        args.replacement_tier = None
        args.replacement_mode = None
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        monkeypatch.setattr(delegate.config, "load_model_policy", lambda: {})
        monkeypatch.setattr(
            delegate.process,
            "_spawn_backend",
            lambda *a, **k: (
                1,
                "assistant answer",
                "HTTP 429 rate limit",
                None,
                False,
                None,
                False,
            ),
        )

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 0
        emitted = json.loads(capsys.readouterr().out.splitlines()[-1])
        assert emitted["outcome"] == "fallback_pending"
        assert emitted["recovery"]["requires_task_resubmission"] is True
        store = delegate.JobStore()
        record = next(
            store.read(job_id)
            for job_id in store.list_job_ids()
            if store.read(job_id)["state"] == "fallback_pending"
        )
        assert record["state"] == "fallback_pending"
        assert record["failure_summary"]["provider"] == "codex"
        assert "assistant answer" not in json.dumps(record)
        recovery_path = Path(store.job_dir(record["job_id"])) / "recovery.json"
        assert stat.S_IMODE(recovery_path.stat().st_mode) == 0o600
        assert "do the thing" not in recovery_path.read_text(encoding="utf-8")
        args.recovery_id = record["recovery"]["recovery_id"]
        return args, store, record


class TestFallbackPendingRecovery(_FallbackPendingMixin):
    def test_foreground_spawn_failure_restores_pending_and_recovery(
        self, tmp_path, monkeypatch, capsys
    ):
        args, store, pending = self._first_pending(tmp_path, monkeypatch, capsys)
        args.resume = pending["job_id"]
        args.prompt = "resupplied private task"
        args.expected_version = pending["version"]
        args.fallback_decision = "approve"
        monkeypatch.setattr(
            delegate.worker,
            "_run_backend_foreground",
            lambda *a, **k: (_ for _ in ()).throw(OSError("spawn failed secret")),
        )

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 1

        restored = store.read(pending["job_id"])
        assert restored["state"] == "fallback_pending"
        assert restored["recovery"] == pending["recovery"]
        assert store.read_recovery(pending["job_id"]) == pending["recovery"]
        assert "spawn failed secret" not in capsys.readouterr().err

    def test_background_worker_spawn_failure_restores_pending_and_recovery(
        self, tmp_path, monkeypatch, capsys
    ):
        args, store, pending = self._first_pending(tmp_path, monkeypatch, capsys)
        args.resume = pending["job_id"]
        args.prompt = "resupplied private task"
        args.expected_version = pending["version"]
        args.fallback_decision = "approve"
        args.background = True
        monkeypatch.setattr(
            delegate.worker,
            "_spawn_worker",
            lambda *a, **k: (_ for _ in ()).throw(OSError("spawn failed secret")),
        )

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 1

        restored = store.read(pending["job_id"])
        assert restored["state"] == "fallback_pending"
        assert store.read_recovery(pending["job_id"]) == pending["recovery"]

    def test_pending_publication_clears_secret_bearing_output(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        args.model = "advanced"
        args.model_chain = "flash"
        args.model_fallback = "confirm"
        args.skill_path = None
        args.expected_version = None
        args.fallback_decision = None
        args.replacement_tier = None
        args.replacement_mode = None
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        monkeypatch.setattr(delegate.config, "load_model_policy", lambda: {})

        def fail_with_output(_entry, _argv, _prompt, job_dir, _budget, **_kwargs):
            Path(job_dir, "output.txt").write_text(
                "token=secret-before-pending", encoding="utf-8"
            )
            return 1, "", "HTTP 429 rate limit", None, False, None, False

        monkeypatch.setattr(delegate.process, "_spawn_backend", fail_with_output)

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 0
        emitted = json.loads(capsys.readouterr().out)
        store = delegate.JobStore()
        output = Path(store.job_dir(emitted["job_id"])) / "output.txt"
        assert output.read_text(encoding="utf-8") == ""

    def test_readiness_failure_leaves_pending_record_and_recovery_unchanged(
        self, tmp_path, monkeypatch, capsys
    ):
        args, store, pending = self._first_pending(tmp_path, monkeypatch, capsys)
        recovery_path = Path(store.job_dir(pending["job_id"])) / "recovery.json"
        recovery_before = recovery_path.read_bytes()
        args.resume = pending["job_id"]
        args.prompt = "resubmitted task"
        args.expected_version = pending["version"]
        args.fallback_decision = "approve"
        monkeypatch.setattr(
            delegate.backend,
            "_executable_missing",
            lambda argv: "binary 'codex' not found on PATH",
        )

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 3

        assert store.read(pending["job_id"]) == pending
        assert recovery_path.read_bytes() == recovery_before

    def test_payload_failure_leaves_pending_record_and_recovery_unchanged(
        self, tmp_path, monkeypatch, capsys
    ):
        args, store, pending = self._first_pending(tmp_path, monkeypatch, capsys)
        recovery_path = Path(store.job_dir(pending["job_id"])) / "recovery.json"
        recovery_before = recovery_path.read_bytes()
        args.resume = pending["job_id"]
        args.prompt = "resubmitted task exceeds the tiny transport limit"
        args.expected_version = pending["version"]
        args.fallback_decision = "approve"
        backend = _valid_backend("codex")
        backend["input"]["max_payload_bytes"] = 8

        assert delegate.cmd_task(args, [backend], {}, set()) == 2

        assert store.read(pending["job_id"]) == pending
        assert recovery_path.read_bytes() == recovery_before

    def test_stale_version_is_rejected_and_current_version_can_reject(
        self, tmp_path, monkeypatch, capsys
    ):
        args, store, pending = self._first_pending(tmp_path, monkeypatch, capsys)
        args.resume = pending["job_id"]
        args.prompt = "resupplied task"
        args.fallback_decision = "reject"
        args.expected_version = pending["version"] - 1

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 2
        assert "stale job version" in capsys.readouterr().err
        assert store.read(pending["job_id"])["state"] == "fallback_pending"

        args.expected_version = pending["version"]
        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 0
        assert store.read(pending["job_id"])["state"] == "fallback_rejected"

    def test_reject_is_task_free_idempotent_and_skips_backend_validation(
        self, tmp_path, monkeypatch, capsys
    ):
        args, store, pending = self._first_pending(tmp_path, monkeypatch, capsys)
        args.resume = pending["job_id"]
        args.prompt = None
        args.prompt_file = str(tmp_path / "missing-task.txt")
        args.expected_version = pending["version"]
        args.fallback_decision = "reject"

        assert delegate.cmd_task(args, [], {}, {"codex"}) == 0
        rejected = store.read(pending["job_id"])
        assert rejected["state"] == "fallback_rejected"
        assert rejected["recovery_audit"]["action"] == "reject"

        assert delegate.cmd_task(args, [], {}, {"codex"}) == 0
        assert store.read(pending["job_id"])["version"] == rejected["version"]

        args.fallback_decision = "approve"
        assert delegate.cmd_task(args, [], {}, {"codex"}) == 2
        assert "conflicting action" in capsys.readouterr().err

    def test_replacement_tier_auto_mode_and_cancel_are_versioned(
        self, tmp_path, monkeypatch, capsys
    ):
        args, store, pending = self._first_pending(tmp_path, monkeypatch, capsys)
        cancel_args = type(
            "CancelArgs",
            (),
            {
                "job_id": pending["job_id"],
                "expected_version": pending["version"] - 1,
                "recovery_id": pending["recovery"]["recovery_id"],
                "json": True,
            },
        )()
        assert delegate.cmd_cancel(cancel_args) == 2
        assert "stale job version" in capsys.readouterr().err
        cancel_args.expected_version = pending["version"]
        assert delegate.cmd_cancel(cancel_args) == 0
        assert store.read(pending["job_id"])["state"] == "fallback_rejected"

        args, store, pending = self._first_pending(tmp_path, monkeypatch, capsys)
        invoked_models = []
        success = {
            "backend": "codex",
            "model": "mini",
            "outcome": "success",
            "attempted": "replacement",
            "changes": [],
            "succeeded": [],
            "failed": [],
            "follow_ups": [],
        }

        def replacement_spawn(entry, argv, *rest, **kwargs):
            del entry, rest, kwargs
            invoked_models.extend(argv)
            return (
                0,
                "```json\n" + json.dumps(success) + "\n```\n",
                "",
                None,
                False,
                None,
                False,
            )

        monkeypatch.setattr(delegate.process, "_spawn_backend", replacement_spawn)
        args.resume = pending["job_id"]
        args.prompt = "resupplied replacement task"
        args.expected_version = pending["version"]
        args.fallback_decision = "auto"
        args.replacement_tier = "mini"
        args.replacement_mode = "auto"

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 0
        final = store.read(pending["job_id"])
        assert final["state"] == "completed"
        assert final["fallback_mode"] == "auto"
        assert final["model_attempts"][-1]["tier"] == "mini"
        assert "--model" in invoked_models
