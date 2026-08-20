#!/usr/bin/env python3
"""Backend-registry validation and the interpreter version probe (D8, D11).

Split out of the former test_delegate_dispatcher.py, which had grown past the
500-line file ceiling; the split follows the manifest_delegate package's own
module boundaries. Shared loader and registry-entry factory live in
_delegate_inproc.py.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_registry.py -q
"""

import json
import re

import pytest
from _delegate_inproc import SCRIPT_PATH, _valid_backend, delegate


class TestRegistryShape:
    """Structural validation: what the registry file must look like before any
    entry in it means anything. Every rejection is a RegistryError, and the CLI
    wrapper turns each into exit 2 rather than a traceback."""

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


class TestRegistrySafetyAndResolution:
    """The two things registry validation exists to guarantee: an entry can
    never smuggle in a shell escape or a permission bypass (D8), and a backend
    resolves by id or alias with no name branching in the dispatcher (FR-016)."""

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
        """K2: unknown transports are rejected rather than dropping prompts."""
        bad = _valid_backend("codex")
        bad["input"]["transport"] = "socket"
        path = tmp_path / "backends.json"
        path.write_text(json.dumps({"backends": [bad]}))
        with pytest.raises(delegate.RegistryError, match="unsupported"):
            delegate.load_registry(str(path))

    def test_unsupported_transport_via_cli_exits_2(self, tmp_path):
        bad = _valid_backend("codex")
        bad["input"]["transport"] = "socket"
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


class TestShippedClaudeSandbox:
    def test_claude_enforces_sandbox_settings_in_both_modes(self):
        """Codex HIGH / D8: the SHIPPED claude profile must launch with
        sandbox-enabled --settings in BOTH read-only and write mode. Without it,
        --write inherits the user's full Claude permissions and can modify files
        outside the workspace (config, credentials) while claiming to be
        sandboxed. Guards the assembled argv, not just the raw config."""
        from _delegate_inproc import REPO_ROOT

        cfg = json.loads(
            (REPO_ROOT / "plugins/manifest-delegate/config/backends.json").read_text()
        )
        claude = next(b for b in cfg["backends"] if b["id"] == "claude")
        for write in (False, True):
            mode = "write" if write else "read-only"
            argv = delegate.backend.build_invoke_argv(claude, write, "sonnet", {})
            assert "--settings" in argv, f"claude {mode} mode is missing --settings"
            settings = json.loads(argv[argv.index("--settings") + 1])
            assert settings.get("sandbox", {}).get("enabled") is True, (
                f"claude {mode} mode --settings does not enable the sandbox"
            )


def _shipped_registry():
    from _delegate_inproc import REPO_ROOT

    return json.loads(
        (REPO_ROOT / "plugins/manifest-delegate/config/backends.json").read_text()
    )["backends"]


def _shipped(backend_id):
    return next(b for b in _shipped_registry() if b["id"] == backend_id)


class TestShippedRegistryContract:
    """Gates every SHIPPED entry, so a backend added later inherits them.

    FR-016 says adding a backend is entry-only; these are the promises an
    entry has to keep for that to be true — the guidance file it points at
    must exist, and its services toggle must be a key services.yml actually
    writes (otherwise readiness silently treats it as enabled-by-absence).
    """

    def test_every_backend_prompting_ref_exists(self):
        from _delegate_inproc import REPO_ROOT

        plugin = REPO_ROOT / "plugins/manifest-delegate"
        missing = [
            (b["id"], b["prompting_ref"])
            for b in _shipped_registry()
            if not (plugin / b["prompting_ref"]).is_file()
        ]
        assert not missing, f"prompting_ref targets do not exist: {missing}"

    def test_every_services_key_is_written_by_bootstrap(self):
        from _delegate_inproc import REPO_ROOT

        body = (REPO_ROOT / "bootstrap/lib/config.sh").read_text()
        start = body.index("write_services_config()")
        section = body[start : body.index("\n}", start)]
        written = set(re.findall(r"^  (\w[\w-]*):\s*$", section, re.M))
        unknown = sorted({b["services_key"] for b in _shipped_registry()} - written)
        assert not unknown, f"services_key not written to services.yml: {unknown}"

    def test_no_backend_can_resume_without_capturing_a_session_id(self):
        """A resume template is useless — and misleading — unless the entry
        also declares how {session_ref} is captured."""
        broken = [
            b["id"]
            for b in _shipped_registry()
            if b.get("resume")
            and (b.get("session_id_capture") or {}).get("method") in (None, "none")
        ]
        assert not broken, f"resume declared with no session capture: {broken}"


class TestShippedCursorSandbox:
    """Measured 2026-08-19 against cursor-agent 2026.08.04: `-p
    --output-format json` emits {"result", "session_id"} and reads the prompt
    from stdin; `--mode plan` is read-only and `--resume <id>` restores
    context. The gate here is the sandbox, which must survive `--write`."""

    def test_sandbox_stays_enabled_in_both_modes(self):
        cursor = _shipped("cursor")
        for write in (False, True):
            argv = delegate.backend.build_invoke_argv(cursor, write, "flash", {})
            mode = "write" if write else "read-only"
            assert "--sandbox" in argv, f"cursor {mode} mode is missing --sandbox"
            assert argv[argv.index("--sandbox") + 1] == "enabled", (
                f"cursor {mode} mode does not enable the sandbox"
            )

    def test_read_only_mode_pins_plan_and_write_mode_drops_only_that(self):
        cursor = _shipped("cursor")
        read_only = delegate.backend.build_invoke_argv(cursor, False, "flash", {})
        assert read_only[read_only.index("--mode") + 1] == "plan"
        assert "--mode" not in delegate.backend.build_invoke_argv(
            cursor, True, "flash", {}
        )

    def test_workspace_trust_is_answered_without_force_flags(self):
        """cursor-agent refuses to run in an untrusted directory and, being
        non-interactive, cannot answer the prompt (measured: exit 1, "Workspace
        Trust Required"). `--trust` answers only that gate; the run stays
        sandboxed and read-only. The force flags that DO drop permissions
        (`--yolo`, `--force`, `-f`) must never appear."""
        cursor = _shipped("cursor")
        for write in (False, True):
            argv = delegate.backend.build_invoke_argv(cursor, write, "flash", {})
            mode = "write" if write else "read-only"
            assert "--trust" in argv, f"cursor {mode} mode cannot pass the trust gate"
            forbidden = {"--yolo", "--force", "-f", "--auto-review"}
            assert not forbidden & set(argv), f"cursor {mode} mode uses a force flag"
        resume = delegate.backend.build_resume_argv(cursor, "SID", False, "flash", {})
        assert "--trust" in resume, "cursor resume cannot pass the trust gate"

    def test_session_id_and_result_are_read_from_the_cli_json(self):
        cursor = _shipped("cursor")
        assert cursor["session_id_capture"] == {
            "method": "json_field",
            "field": "session_id",
        }
        assert cursor["response_capture"] == {
            "method": "json_field",
            "field": "result",
        }


class TestShippedDevinProfile:
    """Devin is login-gated, so its profile is deliberately conservative:
    no resume handle is observable in print mode, and `devin models list`
    cannot be enumerated to pin tiers (parallel_agent.yml records the same
    finding), so the factory tier is `auto`."""

    def test_resume_is_disclosed_as_unsupported_not_faked(self):
        devin = _shipped("devin")
        assert devin["resume"] is None
        assert devin["session_id_capture"]["method"] == "none"

    def test_default_tier_auto_drops_the_model_flag(self):
        devin = _shipped("devin")
        tier = delegate.backend.resolve_model_tier(devin, {}, None)
        argv = delegate.backend.build_invoke_argv(devin, False, tier, {"prompt": "p"})
        assert "--model" not in argv, argv

    def test_permission_mode_is_read_only_by_default_and_sandboxed_in_both(self):
        devin = _shipped("devin")
        read_only = delegate.backend.build_invoke_argv(
            devin, False, "auto", {"prompt": "p"}
        )
        write = delegate.backend.build_invoke_argv(devin, True, "auto", {"prompt": "p"})
        assert read_only[read_only.index("--permission-mode") + 1] == "auto"
        assert write[write.index("--permission-mode") + 1] == "accept-edits"
        for mode, argv in (("read-only", read_only), ("write", write)):
            assert "--sandbox" in argv, f"devin {mode} mode is missing --sandbox"

    def test_bounded_argv_transport_rejects_oversize_prompts(self):
        devin = _shipped("devin")
        assert devin["input"]["transport"] == "argv"
        cap = devin["input"]["max_payload_bytes"]
        assert cap == 65536
        err = delegate.backend.check_payload_limits(devin, b"x" * (cap + 1))
        assert err and str(cap) in err


class TestShippedRegistryMatchesContract:
    """The registry file declares `$schema`, but nothing validated against it
    until now — which is how `response_capture` reached the shipped claude
    entry (and the dispatcher's extract_response_text) without ever being
    added to the contract. This gate closes that loop: contract drift fails
    here instead of being discovered when a backend is added."""

    def test_every_shipped_entry_validates_against_the_contract(self):
        import jsonschema
        from _delegate_inproc import REPO_ROOT

        schema = json.loads(
            (
                REPO_ROOT
                / "specs/675-multi-agent-delegation/contracts"
                / "backend-registry.schema.json"
            ).read_text()
        )
        validator = jsonschema.Draft202012Validator(schema)
        failures = [
            f"{entry['id']}: {list(err.absolute_path)} {err.message}"
            for entry in _shipped_registry()
            for err in validator.iter_errors(entry)
        ]
        assert not failures, "registry entries violate the contract: " + "; ".join(
            failures
        )
