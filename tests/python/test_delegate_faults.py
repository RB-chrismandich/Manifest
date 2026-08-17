"""SC-004 fault-injection matrix for the delegate dispatcher.

Every dispatcher failure path must be explicit (states what happened),
attributed (names the backend/limit/layer responsible), and actionable
(names what to check or do next). This file drives one test per fault in
the matrix via delegate.py's public functions only; delegate.py itself is
never modified or read in full (see module docstring conventions in
test_delegate_dispatcher.py, which this file mirrors).
"""

import importlib.util
import io
import json
import re
import sys
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


def test_skill_frontmatter_uses_backend_id_when_tier_source_is_registry_key(
    tmp_path, monkeypatch
):
    args = _make_args(tmp_path, monkeypatch)
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "---\n"
        "name: demo\n"
        "models:\n"
        "  codex: [advanced, flash]\n"
        "model_fallback:\n"
        "  mode: auto\n"
        "---\n"
        "Do the work.\n",
        encoding="utf-8",
    )
    args.skill_path = str(skill)
    backend = _valid_backend("codex")
    backend["tier_source"] = "model_tiers"
    monkeypatch.setattr(
        delegate.config,
        "load_model_policy",
        lambda: {
            "model_tiers": {
                "codex": {"advanced": "gpt-advanced", "flash": "gpt-flash"}
            },
            "cli_agents": {"codex": {"model_args": ["--model", "{model}"]}},
            "model_fallback": {"mode": "confirm"},
        },
    )

    plan, error = delegate.task.resolve_task_model_plan(
        delegate.JobStore(), args, backend, {}, None
    )

    assert error is None
    assert [(item.tier, item.model_id) for item in plan.chain] == [
        ("advanced", "gpt-advanced"),
        ("flash", "gpt-flash"),
    ]
    assert plan.fallback_mode.value == "auto"


# ---------------------------------------------------------------------------
# 1. unknown backend
# ---------------------------------------------------------------------------


class TestUnknownBackendFault:
    def test_unknown_backend_message_is_explicit_attributed_actionable(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch, backend="not-a-real-backend")
        rc = delegate.cmd_task(
            args, [_valid_backend("codex"), _valid_backend("claude")], {}, set()
        )
        err = capsys.readouterr().err
        assert rc == 2
        assert "not-a-real-backend" in err
        _assert_explicit_attributed_actionable(
            err,
            backend_id="not-a-real-backend",
            actionable_markers=("known:", "codex", "claude"),
        )


# ---------------------------------------------------------------------------
# 2. disabled-by-workspace / 3. disabled-by-user
# ---------------------------------------------------------------------------


class TestDisabledByLayerFaults:
    def test_disabled_by_workspace_outranks_and_names_layer(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        backends = [_valid_backend("codex")]
        # Both workspace-disabled AND user-enabled: workspace must win and be named.
        user_config = {"backends": {"codex": {"enabled": True}}}
        rc = delegate.cmd_task(args, backends, user_config, {"codex"})
        err = capsys.readouterr().err
        assert rc == 3
        _assert_explicit_attributed_actionable(
            err,
            backend_id="codex",
            actionable_markers=("workspace services.yml", "delegate.py setup"),
        )

    def test_disabled_by_user_names_layer_and_remediation(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        backends = [_valid_backend("codex")]
        user_config = {"backends": {"codex": {"enabled": False}}}
        rc = delegate.cmd_task(args, backends, user_config, set())
        err = capsys.readouterr().err
        assert rc == 3
        _assert_explicit_attributed_actionable(
            err,
            backend_id="codex",
            actionable_markers=("user delegation config", "delegate.py setup"),
        )


# ---------------------------------------------------------------------------
# 4. missing binary
# ---------------------------------------------------------------------------


class TestMissingBinaryFault:
    def test_missing_binary_message_is_explicit_attributed_actionable(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        backends = [_valid_backend("codex")]
        monkeypatch.setattr(
            delegate.backend,
            "_executable_missing",
            lambda argv: "binary 'codex' not found on PATH",
        )
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

        monkeypatch.setattr(delegate.readiness, "_run_readiness_probe", fake_probe)
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
    def test_oversize_vs_transport_bound_names_specific_limit(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        args.prompt = "x" * 2_000_000
        backend = _valid_backend("codex")
        backend["input"]["max_payload_bytes"] = 1_000_000
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        rc = delegate.cmd_task(args, [backend], {}, set())
        err = capsys.readouterr().err
        assert rc == 2
        assert "1 MiB task limit" in err
        assert "1048576" in err

    def test_stdin_is_bounded_before_backend_limits(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        args.prompt = "-"
        monkeypatch.setattr(
            sys,
            "stdin",
            io.TextIOWrapper(io.BytesIO(b"x" * (1024 * 1024 + 1))),
        )

        rc = delegate.cmd_task(args, [_valid_backend("codex")], {}, set())

        err = capsys.readouterr().err
        assert rc == 2
        assert "stdin exceeds the 1 MiB task limit" in err
        assert "1048576" in err
        assert "max_payload_bytes" not in err
        assert "max_context_bytes" not in err

    def test_oversize_vs_model_context_bound_names_specific_limit(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        args.prompt = "y" * 500_000
        backend = _valid_backend("codex")
        backend["input"]["max_payload_bytes"] = 1_000_000
        backend["input"]["max_context_bytes"] = 100_000
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        rc = delegate.cmd_task(args, [backend], {}, set())
        err = capsys.readouterr().err
        assert rc == 2
        assert "max_context_bytes" in err
        assert "100000" in err
        size = re.search(r"\((\d+) > 100000\)", err)
        assert size and int(size.group(1)) > len(args.prompt)
        _assert_explicit_attributed_actionable(
            err, backend_id=None, actionable_markers=("max_context_bytes",)
        )
        # This is the model-context bound, not the transport bound: distinct message.
        assert "max_payload_bytes" not in err


# ---------------------------------------------------------------------------
# 8. timeout
# ---------------------------------------------------------------------------


class TestTimeoutFault:
    def test_timeout_message_is_explicit_attributed_actionable(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        backend = _valid_backend("codex")
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            envelope = delegate.normalize_envelope("", entry["id"], record.get("model"))
            return {"state": "timeout", "envelope": envelope, "job_id": job_id}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
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
        envelope = delegate.normalize_envelope(
            "not json at all, just prose", "claude", "sonnet"
        )
        assert envelope["outcome"] == "failure"
        assert envelope["backend"] == "claude"
        assert envelope["error"] == "backend returned nothing usable"
        assert envelope["raw_output"] == "not json at all, just prose"
        _assert_explicit_attributed_actionable(
            json.dumps(envelope),
            backend_id="claude",
            actionable_markers=("raw_output", "error"),
        )

    def test_missing_required_fields_names_them(self):
        raw = '```json\n{"outcome": "success"}\n```'
        envelope = delegate.normalize_envelope(raw, "codex", None)
        assert envelope["outcome"] == "failure"
        assert envelope["backend"] == "codex"
        assert "missing required fields" in envelope["error"]
        _assert_explicit_attributed_actionable(
            envelope["error"],
            backend_id=None,
            actionable_markers=("missing required fields",),
        )

    def test_cmd_task_surfaces_malformed_output_end_to_end(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        backend = _valid_backend("codex")
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)

        def fake_run(store_, job_id, entry, record, prompt_bytes):
            envelope = delegate.normalize_envelope(
                "garbage output", entry["id"], record.get("model")
            )
            return {"state": "failed", "envelope": envelope, "job_id": job_id}

        monkeypatch.setattr(delegate.worker, "_run_backend_and_finish", fake_run)
        rc = delegate.cmd_task(args, [backend], {}, set())
        out = capsys.readouterr().out
        assert rc == 1
        envelope = json.loads(out)
        assert envelope["backend"] == "codex"
        assert envelope["error"] == "backend returned nothing usable"
        _assert_explicit_attributed_actionable(
            json.dumps(envelope),
            backend_id="codex",
            actionable_markers=("raw_output", "error"),
        )

    def test_zero_exit_empty_provider_output_blocks_end_to_end(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        monkeypatch.setattr(delegate.backend, "_executable_missing", lambda argv: None)
        monkeypatch.setattr(
            delegate.process,
            "_spawn_backend",
            lambda *args, **kwargs: (0, "", "", None, False, None, False),
        )

        rc = delegate.cmd_task(args, [_valid_backend("codex")], {}, set())

        envelope = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert envelope["outcome"] == "failure"
        assert envelope["error"] == "provider attempt failed"
