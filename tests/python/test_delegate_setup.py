#!/usr/bin/env python3
"""Backend readiness probes and the `setup` command.

Split out of the former test_delegate_dispatcher.py, which had grown past the
500-line file ceiling; the split follows the manifest_delegate package's own
module boundaries. Shared loader and registry-entry factory live in
_delegate_inproc.py.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_setup.py -q
"""

from _delegate_inproc import _valid_backend, delegate

# ---------------------------------------------------------------------------
# Readiness probing (T018, US2)
# ---------------------------------------------------------------------------


class TestBackendReadinessProbe:
    """What state a single backend reports: ready, not installed, not
    authenticated, retired, or disabled — and that probing never prompts."""

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

        monkeypatch.setattr(delegate.readiness, "_run_readiness_probe", fake_probe)
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

        monkeypatch.setattr(delegate.readiness, "_run_readiness_probe", fake_probe)
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

        monkeypatch.setattr(delegate.readiness.subprocess, "run", fake_run)
        delegate._run_readiness_probe(["codex", "--version"], timeout=5)
        assert captured.get("stdin") == delegate.readiness.subprocess.DEVNULL
        assert captured.get("timeout") == 5


class TestSetupCommand:
    """The `setup` command over the whole registry: probes run in parallel, an
    unknown backend exits 2, and a bare run never writes config as a side
    effect."""

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

        monkeypatch.setattr(delegate.readiness, "probe_backend_readiness", fake_probe)

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

        monkeypatch.setattr(delegate.readiness, "probe_backend_readiness", fake_probe)

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
