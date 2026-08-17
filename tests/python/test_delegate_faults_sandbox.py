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
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "plugins" / "manifest-delegate" / "scripts" / "delegate.py"


def _load_delegate():
    spec = importlib.util.spec_from_file_location("delegate_faults", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


delegate = _load_delegate()


_SANDBOX_STUB = textwrap.dedent(
    """\
    import json
    import sys

    prompt = sys.stdin.read()
    denied_reason = None
    if "/outside/workspace" in prompt:
        denied_reason = "sandbox denied: target path is outside the workspace root"
    elif "force-push" in prompt or "rm -rf" in prompt:
        denied_reason = "sandbox denied: destructive command blocked by write sandbox"

    envelope = {
        "backend": "codex",
        "model": None,
        "outcome": "failure" if denied_reason else "success",
        "attempted": prompt[:80],
        "changes": [],
        "succeeded": [],
        "failed": [],
        "follow_ups": [],
    }
    if denied_reason:
        envelope["error"] = denied_reason

    print("```json")
    print(json.dumps(envelope))
    print("```")
    sys.exit(1 if denied_reason else 0)
    """
)


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


def _make_sandbox_stub(tmp_path):
    stub_path = tmp_path / "sandbox_stub.py"
    stub_path.write_text(_SANDBOX_STUB)
    stub_path.chmod(stub_path.stat().st_mode | stat.S_IEXEC)
    backend = _valid_backend("codex")
    backend["invoke"] = [sys.executable, str(stub_path)]
    backend["input"] = {
        "transport": "stdin",
        "max_payload_bytes": 1_000_000,
        "max_context_bytes": None,
    }
    return backend


class TestSandboxFaultPair:
    def test_outside_workspace_write_is_denied_never_approved(
        self, tmp_path, monkeypatch, capsys
    ):
        backend = _make_sandbox_stub(tmp_path)
        args = _make_args(tmp_path, monkeypatch)
        args.write = True
        args.prompt = "please write results to /outside/workspace/notes.txt"
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)

        rc = delegate.cmd_task(args, [backend], {}, set())
        out = capsys.readouterr().out
        envelope = json.loads(out)

        assert rc == 1, (
            "an outside-workspace write must never be approved (rc must signal failure)"
        )
        assert envelope["outcome"] == "failure"
        assert envelope["backend"] == "codex"
        assert "outside the workspace" in envelope["error"]
        _assert_explicit_attributed_actionable(
            json.dumps(envelope),
            backend_id="codex",
            actionable_markers=("outside the workspace",),
        )

    def test_destructive_command_is_denied_never_approved(
        self, tmp_path, monkeypatch, capsys
    ):
        backend = _make_sandbox_stub(tmp_path)
        args = _make_args(tmp_path, monkeypatch)
        args.write = True
        args.prompt = "run git push --force to origin main (force-push)"
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)

        rc = delegate.cmd_task(args, [backend], {}, set())
        out = capsys.readouterr().out
        envelope = json.loads(out)

        assert rc == 1, (
            "a destructive command must never be approved (rc must signal failure)"
        )
        assert envelope["outcome"] == "failure"
        assert envelope["backend"] == "codex"
        assert "destructive command blocked" in envelope.get("error", "")
        _assert_explicit_attributed_actionable(
            json.dumps(envelope),
            backend_id="codex",
            actionable_markers=("destructive command blocked",),
        )


class TestBackendIndependentRecoveryCli:
    def _pending(self, tmp_path, monkeypatch):
        monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
        monkeypatch.chdir(tmp_path)
        store = delegate.JobStore()
        record = store.create("missing-backend")
        recovery = {
            "recovery_id": "recovery-cli",
            "next_tier": "flash",
            "next_index": 1,
            "requires_task_resubmission": True,
        }
        store.write_recovery(record["job_id"], recovery)
        pending = store.mutate(
            record["job_id"],
            lambda current: {
                **current,
                "state": "fallback_pending",
                "fallback_pending": True,
                "recovery": recovery,
            },
        )
        return store, pending, recovery

    def test_cli_reject_skips_registry_and_config(self, tmp_path, monkeypatch):
        store, pending, recovery = self._pending(tmp_path, monkeypatch)
        monkeypatch.setattr(
            delegate.registry,
            "load_registry_or_exit",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("registry")),
        )
        monkeypatch.setattr(
            delegate.config,
            "load_user_config",
            lambda: (_ for _ in ()).throw(AssertionError("user config")),
        )
        monkeypatch.setattr(
            delegate.config,
            "load_services_disabled",
            lambda: (_ for _ in ()).throw(AssertionError("services")),
        )

        rc = delegate.main(
            [
                "task",
                "--resume",
                pending["job_id"],
                "--expected-version",
                str(pending["version"]),
                "--recovery-id",
                recovery["recovery_id"],
                "--fallback-decision",
                "reject",
            ]
        )

        assert rc == 0
        assert store.read(pending["job_id"])["state"] == "fallback_rejected"

    def test_cli_cancel_skips_registry_and_config(self, tmp_path, monkeypatch):
        store, pending, recovery = self._pending(tmp_path, monkeypatch)
        monkeypatch.setattr(
            delegate.registry,
            "load_registry_or_exit",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("registry")),
        )
        monkeypatch.setattr(
            delegate.config,
            "load_user_config",
            lambda: (_ for _ in ()).throw(AssertionError("user config")),
        )

        rc = delegate.main(
            [
                "cancel",
                pending["job_id"],
                "--expected-version",
                str(pending["version"]),
                "--recovery-id",
                recovery["recovery_id"],
            ]
        )

        assert rc == 0
        assert store.read(pending["job_id"])["state"] == "fallback_rejected"
