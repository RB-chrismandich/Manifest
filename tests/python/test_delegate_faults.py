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
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

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
        "id": id_, "aliases": aliases or [], "display_name": id_.title(), "binary": id_,
        "invoke": [id_, "exec", "{prompt}"], "resume": None, "model_args": ["--model", "{model}"],
        "tier_source": id_, "default_tier": "auto", "session_id_capture": {"mode": "none"},
        "input": {"transport": "stdin", "max_payload_bytes": 1000000, "max_context_bytes": None},
        "readiness": {
            "version_cmd": [id_, "--version"], "auth_probe_cmd": [id_, "whoami"],
            "install_fix": f"install {id_}", "login_fix": f"login {id_}",
        },
        "sandbox": {"read_only_args": ["--read-only"], "write_args": ["--write"]},
        "prompting_ref": f"skills/delegate/references/{id_}.md", "services_key": id_,
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
    prompt_file = None
    prompt = "do the thing"
    json = True


def _assert_explicit_attributed_actionable(message, backend_id=None, actionable_markers=()):
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


class TestUnknownBackendFault:
    def test_unknown_backend_message_is_explicit_attributed_actionable(self, tmp_path, monkeypatch, capsys):
        args = _make_args(tmp_path, monkeypatch, backend="not-a-real-backend")
        rc = delegate.cmd_task(args, [_valid_backend("codex"), _valid_backend("claude")], {}, set())
        err = capsys.readouterr().err
        assert rc == 2
        assert "not-a-real-backend" in err
        _assert_explicit_attributed_actionable(
            err, backend_id="not-a-real-backend", actionable_markers=("known:", "codex", "claude")
        )


# ---------------------------------------------------------------------------
# 2. disabled-by-workspace / 3. disabled-by-user
# ---------------------------------------------------------------------------


class TestDisabledByLayerFaults:
    def test_disabled_by_workspace_outranks_and_names_layer(self, tmp_path, monkeypatch, capsys):
        args = _make_args(tmp_path, monkeypatch)
        backends = [_valid_backend("codex")]
        # Both workspace-disabled AND user-enabled: workspace must win and be named.
        user_config = {"backends": {"codex": {"enabled": True}}}
        rc = delegate.cmd_task(args, backends, user_config, {"codex"})
        err = capsys.readouterr().err
        assert rc == 3
        _assert_explicit_attributed_actionable(
            err, backend_id="codex", actionable_markers=("workspace services.yml", "delegate.py setup")
        )

    def test_disabled_by_user_names_layer_and_remediation(self, tmp_path, monkeypatch, capsys):
        args = _make_args(tmp_path, monkeypatch)
        backends = [_valid_backend("codex")]
        user_config = {"backends": {"codex": {"enabled": False}}}
        rc = delegate.cmd_task(args, backends, user_config, set())
        err = capsys.readouterr().err
        assert rc == 3
        _assert_explicit_attributed_actionable(
            err, backend_id="codex", actionable_markers=("user delegation config", "delegate.py setup")
        )


# ---------------------------------------------------------------------------
# 4. missing binary
# ---------------------------------------------------------------------------


class TestMissingBinaryFault:
    def test_missing_binary_message_is_explicit_attributed_actionable(self, tmp_path, monkeypatch, capsys):
        args = _make_args(tmp_path, monkeypatch)
        backends = [_valid_backend("codex")]
        monkeypatch.setattr(delegate, "_executable_missing", lambda argv: "binary 'codex' not found on PATH")
        rc = delegate.cmd_task(args, backends, {}, set())
        err = capsys.readouterr().err
        assert rc == 3
        _assert_explicit_attributed_actionable(
            err,
            backend_id="codex",
            actionable_markers=("delegate.py setup", "not found on PATH"),
        )


# ---------------------------------------------------------------------------
# 5. unauthenticated (probe_backend_readiness surface)
# ---------------------------------------------------------------------------


class TestUnauthenticatedFault:
    def test_unauthenticated_state_names_login_fix(self, monkeypatch):
        entry = _valid_backend("codex")

        def fake_probe(argv, timeout=10):
            if argv == entry["readiness"]["version_cmd"]:
                return (0, "1.0.0")
            if argv == entry["readiness"]["auth_probe_cmd"]:
                return (1, "")
            return (1, "")

        monkeypatch.setattr(delegate, "_run_readiness_probe", fake_probe)
        row = delegate.probe_backend_readiness(entry, {}, set())
        assert row["state"] == "not_authenticated"
        assert row["backend"] == "codex"
        _assert_explicit_attributed_actionable(
            f"{row['backend']}: {row['state']} ({row['fix']})",
            backend_id="codex",
            actionable_markers=("login codex",),
        )
        assert row["fix"] == "login codex"


# ---------------------------------------------------------------------------
# 6/7. oversize context vs transport bound AND vs model-context bound
# ---------------------------------------------------------------------------


class TestOversizeContextFaults:
    def test_oversize_vs_transport_bound_names_specific_limit(self, tmp_path, monkeypatch, capsys):
        args = _make_args(tmp_path, monkeypatch)
        args.prompt = "x" * 2_000_000
        backend = _valid_backend("codex")
        backend["input"]["max_payload_bytes"] = 1_000_000
        monkeypatch.setattr(delegate, "_executable_missing", lambda argv: None)
        rc = delegate.cmd_task(args, [backend], {}, set())
        err = capsys.readouterr().err
        assert rc == 2
        assert "max_payload_bytes" in err
        assert "1000000" in err or "1_000_000" in err
        assert "2000000" in err
        _assert_explicit_attributed_actionable(
            err, backend_id=None, actionable_markers=("max_payload_bytes",)
        )
        # Never truncated/generic: the *other* limit name must not appear.
        assert "max_context_bytes" not in err

    def test_oversize_vs_model_context_bound_names_specific_limit(self, tmp_path, monkeypatch, capsys):
        args = _make_args(tmp_path, monkeypatch)
        args.prompt = "y" * 500_000
        backend = _valid_backend("codex")
        backend["input"]["max_payload_bytes"] = 1_000_000
        backend["input"]["max_context_bytes"] = 100_000
        monkeypatch.setattr(delegate, "_executable_missing", lambda argv: None)
        rc = delegate.cmd_task(args, [backend], {}, set())
        err = capsys.readouterr().err
        assert rc == 2
        assert "max_context_bytes" in err
        assert "100000" in err
        assert "500000" in err
        _assert_explicit_attributed_actionable(
            err, backend_id=None, actionable_markers=("max_context_bytes",)
        )
        # This is the model-context bound, not the transport bound: distinct message.
        assert "max_payload_bytes" not in err


# ---------------------------------------------------------------------------
# 8. timeout
# ---------------------------------------------------------------------------


class TestTimeoutFault:
    def test_timeout_message_is_explicit_attributed_actionable(self, tmp_path, monkeypatch, capsys):
        args = _make_args(tmp_path, monkeypatch)
        backend = _valid_backend("codex")
        monkeypatch.setattr(delegate, "_executable_missing", lambda argv: None)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            envelope = delegate.normalize_envelope("", entry["id"], record.get("model"))
            return {"state": "timeout", "envelope": envelope, "job_id": job_id}

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
        rc = delegate.cmd_task(args, [backend], {}, set())
        out = capsys.readouterr().out
        assert rc == 1
        envelope = json.loads(out)
        assert envelope["backend"] == "codex"
        assert envelope["outcome"] == "failure"
        _assert_explicit_attributed_actionable(
            json.dumps(envelope),
            backend_id="codex",
            actionable_markers=("error", "raw_output"),
        )


# ---------------------------------------------------------------------------
# 9. malformed output
# ---------------------------------------------------------------------------


class TestMalformedOutputFault:
    def test_no_parseable_json_is_explicit_attributed_actionable(self):
        envelope = delegate.normalize_envelope("not json at all, just prose", "claude", "sonnet")
        assert envelope["outcome"] == "failure"
        assert envelope["backend"] == "claude"
        assert envelope["error"] == "backend returned nothing usable"
        assert envelope["raw_output"] == "not json at all, just prose"
        _assert_explicit_attributed_actionable(
            json.dumps(envelope), backend_id="claude", actionable_markers=("raw_output", "error")
        )

    def test_missing_required_fields_names_them(self):
        raw = '```json\n{"outcome": "success"}\n```'
        envelope = delegate.normalize_envelope(raw, "codex", None)
        assert envelope["outcome"] == "failure"
        assert envelope["backend"] == "codex"
        assert "missing required fields" in envelope["error"]
        _assert_explicit_attributed_actionable(
            envelope["error"], backend_id=None, actionable_markers=("missing required fields",)
        )

    def test_cmd_task_surfaces_malformed_output_end_to_end(self, tmp_path, monkeypatch, capsys):
        args = _make_args(tmp_path, monkeypatch)
        backend = _valid_backend("codex")
        monkeypatch.setattr(delegate, "_executable_missing", lambda argv: None)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            envelope = delegate.normalize_envelope("garbage output", entry["id"], record.get("model"))
            return {"state": "failed", "envelope": envelope, "job_id": job_id}

        monkeypatch.setattr(delegate, "_run_backend_and_finish", fake_run)
        rc = delegate.cmd_task(args, [backend], {}, set())
        out = capsys.readouterr().out
        assert rc == 1
        envelope = json.loads(out)
        assert envelope["backend"] == "codex"
        assert envelope["error"] == "backend returned nothing usable"
        _assert_explicit_attributed_actionable(
            json.dumps(envelope), backend_id="codex", actionable_markers=("raw_output", "error")
        )


# ---------------------------------------------------------------------------
# 10/11. sandbox fault pair (D8): outside-workspace write, destructive command.
#
# delegate.py's registry `sandbox` field only appends read_only_args/write_args
# to argv; enforcement is the backend's own job. These tests build a real stub
# "backend" script (the sandbox stub referenced by the task) and run it through
# the REAL cmd_task -> _run_backend_and_finish -> _spawn_backend pipeline (no
# mocking of the backend call itself) to prove delegate.py surfaces a denial
# from the backend sandbox stub as a failure and never silently approves it.
# ---------------------------------------------------------------------------


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


def _make_sandbox_stub(tmp_path):
    stub_path = tmp_path / "sandbox_stub.py"
    stub_path.write_text(_SANDBOX_STUB)
    stub_path.chmod(stub_path.stat().st_mode | stat.S_IEXEC)
    backend = _valid_backend("codex")
    backend["invoke"] = [sys.executable, str(stub_path)]
    backend["input"] = {"transport": "stdin", "max_payload_bytes": 1_000_000, "max_context_bytes": None}
    return backend


class TestPromptFileFault:
    """K4: a bad --prompt-file must exit 2 with an explicit message, never
    traceback (D3: never crash on bad input)."""

    def test_nonexistent_prompt_file_exits_2_with_message(self, tmp_path, monkeypatch, capsys):
        args = _make_args(tmp_path, monkeypatch)
        args.prompt = None
        args.prompt_file = str(tmp_path / "does-not-exist.txt")
        rc = delegate.cmd_task(args, [_valid_backend("codex")], {}, set())
        err = capsys.readouterr().err
        assert rc == 2
        assert "delegate: cannot read --prompt-file" in err
        assert args.prompt_file in err

    def test_directory_as_prompt_file_exits_2_with_message(self, tmp_path, monkeypatch, capsys):
        args = _make_args(tmp_path, monkeypatch)
        args.prompt = None
        args.prompt_file = str(tmp_path)
        rc = delegate.cmd_task(args, [_valid_backend("codex")], {}, set())
        err = capsys.readouterr().err
        assert rc == 2
        assert "delegate: cannot read --prompt-file" in err
        assert "directory" in err


class TestSandboxFaultPair:
    def test_outside_workspace_write_is_denied_never_approved(self, tmp_path, monkeypatch, capsys):
        backend = _make_sandbox_stub(tmp_path)
        args = _make_args(tmp_path, monkeypatch)
        args.write = True
        args.prompt = "please write results to /outside/workspace/notes.txt"
        monkeypatch.setattr(delegate, "_executable_missing", lambda argv: None)

        rc = delegate.cmd_task(args, [backend], {}, set())
        out = capsys.readouterr().out
        envelope = json.loads(out)

        assert rc == 1, "an outside-workspace write must never be approved (rc must signal failure)"
        assert envelope["outcome"] == "failure"
        assert envelope["backend"] == "codex"
        assert "outside the workspace" in envelope["error"]
        _assert_explicit_attributed_actionable(
            json.dumps(envelope), backend_id="codex", actionable_markers=("outside the workspace",)
        )

    def test_destructive_command_is_denied_never_approved(self, tmp_path, monkeypatch, capsys):
        backend = _make_sandbox_stub(tmp_path)
        args = _make_args(tmp_path, monkeypatch)
        args.write = True
        args.prompt = "run git push --force to origin main (force-push)"
        monkeypatch.setattr(delegate, "_executable_missing", lambda argv: None)

        rc = delegate.cmd_task(args, [backend], {}, set())
        out = capsys.readouterr().out
        envelope = json.loads(out)

        assert rc == 1, "a destructive command must never be approved (rc must signal failure)"
        assert envelope["outcome"] == "failure"
        assert envelope["backend"] == "codex"
        assert "destructive command blocked" in envelope.get("error", "")
        _assert_explicit_attributed_actionable(
            json.dumps(envelope), backend_id="codex", actionable_markers=("destructive command blocked",)
        )
