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
import time
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


class TestAutomaticFallbackExecution(_FallbackPendingMixin):
    """Automatic fallback attempts preserve only current-attempt state."""

    def test_auto_fail_then_success_clears_failure_and_retains_attempts(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        args.model = "advanced"
        args.model_chain = "flash"
        args.model_fallback = "auto"
        args.skill_path = None
        args.expected_version = None
        args.fallback_decision = None
        args.replacement_tier = None
        args.replacement_mode = None
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        monkeypatch.setattr(delegate.config, "load_model_policy", lambda: {})
        success = {
            "backend": "codex",
            "model": "flash",
            "outcome": "success",
            "attempted": "fallback",
            "changes": [],
            "succeeded": [],
            "failed": [],
            "follow_ups": [],
        }
        responses = iter(
            (
                (1, "", "HTTP 429 rate limit", None, False, None, False),
                (
                    0,
                    "```json\n" + json.dumps(success) + "\n```\n",
                    "",
                    None,
                    False,
                    None,
                    False,
                ),
            )
        )
        monkeypatch.setattr(
            delegate.process, "_spawn_backend", lambda *a, **k: next(responses)
        )

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 0
        output = json.loads(capsys.readouterr().out)
        store = delegate.JobStore()
        record = store.read(output["job_id"])
        assert record["state"] == "completed"
        assert [row["tier"] for row in record["model_attempts"]] == [
            "advanced",
            "flash",
        ]
        assert "failure_summary" not in record
        assert record["envelope"]["outcome"] == "success"
        assert record["model"] == "flash"
        assert record["envelope"]["model"] == "flash"
        assert output["model"] == "flash"

    def test_failed_attempt_session_is_used_for_fallback_resume(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        args.model = "advanced"
        args.model_chain = "flash"
        args.model_fallback = "auto"
        args.skill_path = None
        args.expected_version = None
        args.fallback_decision = None
        args.replacement_tier = None
        args.replacement_mode = None
        entry = _valid_backend("codex")
        entry["resume"] = ["codex", "resume", "{session_ref}"]
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        monkeypatch.setattr(delegate.config, "load_model_policy", lambda: {})
        invocations = []
        success = {
            "backend": "codex",
            "model": "flash",
            "outcome": "success",
            "attempted": "resumed fallback",
            "changes": [],
            "succeeded": [],
            "failed": [],
            "follow_ups": [],
        }

        def spawn(_entry, argv, *_args, **_kwargs):
            invocations.append(argv)
            if len(invocations) == 1:
                return 1, "", "HTTP 429 rate limit", None, False, "thread-first", False
            return (
                0,
                "```json\n" + json.dumps(success) + "\n```\n",
                "",
                None,
                False,
                "thread-final",
                False,
            )

        monkeypatch.setattr(delegate.process, "_spawn_backend", spawn)

        assert delegate.cmd_task(args, [entry], {}, set()) == 0
        output = json.loads(capsys.readouterr().out)
        record = delegate.JobStore().read(output["job_id"])

        assert "thread-first" not in invocations[0]
        assert "thread-first" in invocations[1]
        assert record["session_ref"] == "thread-final"

    def test_fallback_attempts_share_one_delegation_budget(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        args.model = "advanced"
        args.model_chain = "flash"
        args.model_fallback = "auto"
        args.skill_path = None
        args.expected_version = None
        args.fallback_decision = None
        args.replacement_tier = None
        args.replacement_mode = None
        args.budget = 1
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        monkeypatch.setattr(delegate.config, "load_model_policy", lambda: {})
        budgets = []
        success = {
            "backend": "codex",
            "model": "flash",
            "outcome": "success",
            "attempted": "bounded fallback",
            "changes": [],
            "succeeded": [],
            "failed": [],
            "follow_ups": [],
        }

        def spawn(_entry, _argv, _prompt, _job_dir, budget, **_kwargs):
            budgets.append(budget)
            if len(budgets) == 1:
                time.sleep(0.2)
                return 1, "", "HTTP 429 rate limit", None, False, None, False
            return (
                0,
                "```json\n" + json.dumps(success) + "\n```\n",
                "",
                None,
                False,
                None,
                False,
            )

        monkeypatch.setattr(delegate.process, "_spawn_backend", spawn)

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 0
        capsys.readouterr()

        assert budgets[0] <= 1
        assert budgets[1] < 0.9


class TestConfirmedFallbackExecution(_FallbackPendingMixin):
    """Confirmed fallbacks preserve their versioned recovery contract."""

    def test_foreground_confirmation_retries_without_pending_recovery(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        args.json = False
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
        monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
        success = {
            "backend": "codex",
            "model": "flash",
            "outcome": "success",
            "attempted": "confirmed fallback",
            "changes": [],
            "succeeded": [],
            "failed": [],
            "follow_ups": [],
        }
        responses = iter(
            (
                (1, "", "HTTP 429 rate limit", None, False, None, False),
                (
                    0,
                    "```json\n" + json.dumps(success) + "\n```\n",
                    "",
                    None,
                    False,
                    None,
                    False,
                ),
            )
        )
        monkeypatch.setattr(
            delegate.process, "_spawn_backend", lambda *a, **k: next(responses)
        )

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 0
        output = capsys.readouterr().out
        job_id = next(
            line.split(": ", 1)[1]
            for line in output.splitlines()
            if line.startswith("job_id:")
        )
        store = delegate.JobStore()
        record = store.read(job_id)
        assert record["state"] == "completed"
        assert len(record["model_attempts"]) == 2
        assert not (Path(store.job_dir(job_id)) / "recovery.json").exists()

    def test_fallback_pending_status_prints_text_recovery(
        self, tmp_path, monkeypatch, capsys
    ):
        _args, _store, pending = self._first_pending(tmp_path, monkeypatch, capsys)
        status_args = type(
            "StatusArgs",
            (),
            {
                "job_id": pending["job_id"],
                "json": False,
                "wait": False,
                "timeout": None,
            },
        )()

        assert delegate.cmd_status(status_args) == 0
        output = capsys.readouterr().out
        assert "state: fallback_pending" in output
        assert "recovery_id:" in output
        assert "next_tier: flash" in output

    def test_approve_requires_version_and_resupplied_task_then_continues(
        self, tmp_path, monkeypatch, capsys
    ):
        args, store, pending = self._first_pending(tmp_path, monkeypatch, capsys)
        success = {
            "backend": "codex",
            "model": "flash",
            "outcome": "success",
            "attempted": "continued",
            "changes": [],
            "succeeded": [],
            "failed": [],
            "follow_ups": [],
        }
        monkeypatch.setattr(
            delegate.process,
            "_spawn_backend",
            lambda *a, **k: (
                0,
                "```json\n" + json.dumps(success) + "\n```\n",
                "",
                None,
                False,
                None,
                False,
            ),
        )
        args.resume = pending["job_id"]
        args.prompt = "resupplied private task"
        args.expected_version = pending["version"]
        args.fallback_decision = "approve"

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 0
        final = store.read(pending["job_id"])
        assert final["state"] == "completed"
        assert len(final["model_attempts"]) == 2
        assert "resupplied private task" not in json.dumps(final)


class TestFallbackTimeoutExecution:
    """Timeouts from later attempts replace earlier failure diagnostics."""

    def test_fallback_timeout_replaces_prior_failure_class(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        args.model = "advanced"
        args.model_chain = "flash"
        args.model_fallback = "auto"
        args.skill_path = None
        args.expected_version = None
        args.fallback_decision = None
        args.replacement_tier = None
        args.replacement_mode = None
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        monkeypatch.setattr(delegate.config, "load_model_policy", lambda: {})
        responses = iter(
            (
                (1, "", "HTTP 429 rate limit", None, False, None, False),
                (-9, "", "", None, True, None, False),
            )
        )
        monkeypatch.setattr(
            delegate.process, "_spawn_backend", lambda *a, **k: next(responses)
        )

        assert delegate.cmd_task(args, [_valid_backend("codex")], {}, set()) == 1
        output = json.loads(capsys.readouterr().out)
        record = delegate.JobStore().read(output["job_id"])

        assert record["state"] == "timeout"
        assert [row["tier"] for row in record["model_attempts"]] == [
            "advanced",
            "flash",
        ]
        assert record["envelope"]["failure_class"] == "timeout"
        assert record["envelope"]["error"] == "provider attempt failed"
