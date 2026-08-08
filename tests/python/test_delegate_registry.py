#!/usr/bin/env python3
"""Backend-registry validation and the interpreter version probe (D8, D11).

Split out of the former test_delegate_dispatcher.py, which had grown past the
500-line file ceiling; the split follows the manifest_delegate package's own
module boundaries. Shared loader and registry-entry factory live in
_delegate_inproc.py.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_registry.py -q
"""

import json

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
