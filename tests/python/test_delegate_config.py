#!/usr/bin/env python3
"""User configuration, services enable flags, and model tier behavior."""

import json
import os

import pytest
from _delegate_inproc import delegate


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
        monkeypatch.setattr(delegate.config, "_yaml_module", lambda: None)
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
        monkeypatch.setattr(
            delegate.constants, "HOME_CONFIG_DIR", str(tmp_path / "unused-home")
        )
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
        monkeypatch.setattr(
            delegate.constants, "HOME_CONFIG_DIR", str(tmp_path / "unused-home")
        )
        tiers = delegate.load_model_tiers(config_dir=str(tmp_path))
        assert tiers == {}

    def test_pyyaml_unavailable_returns_empty(self, tmp_path, monkeypatch):
        (tmp_path / "parallel_agent.yml").write_text("model_tiers:\n  auto: gpt\n")
        monkeypatch.setattr(delegate.config, "_yaml_module", lambda: None)
        tiers = delegate.load_model_tiers(config_dir=str(tmp_path))
        assert tiers == {}

    def test_auto_tier_omits_backend_model_override(self):
        entry = {
            "invoke": ["codex", "exec", "-"],
            "model_args": ["--model", "{model}"],
            "sandbox": {"read_only_args": [], "write_args": []},
        }

        argv = delegate.backend.build_invoke_argv(entry, False, "auto", {})

        assert argv == ["codex", "exec", "-"]


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
        monkeypatch.setattr(delegate.config, "_yaml_module", lambda: None)
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


class TestStageSixConfigMigration:
    """`~/.claude/config` is deleted by Stage 6 (#789). Config resolution must
    already prefer the XDG location, so that deletion degrades to the new home
    rather than silently reverting every user to factory defaults."""

    def test_xdg_config_is_searched_before_the_legacy_claude_home(
        self, tmp_path, monkeypatch
    ):
        xdg = tmp_path / "xdg"
        (xdg / "manifest").mkdir(parents=True)
        (xdg / "manifest" / "delegation.json").write_text(
            json.dumps({"default_backend": "claude"})
        )
        legacy = tmp_path / "home/.claude/config"
        legacy.mkdir(parents=True)
        (legacy / "delegation.json").write_text(
            json.dumps({"default_backend": "cursor"})
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.delenv("MANIFEST_CONFIG_DIR", raising=False)
        monkeypatch.setattr(delegate.constants, "XDG_CONFIG_DIR", str(xdg / "manifest"))
        monkeypatch.setattr(delegate.constants, "HOME_CONFIG_DIR", str(legacy))

        assert delegate.load_user_config()["default_backend"] == "claude"

    def test_legacy_claude_home_still_resolves_until_stage_six(
        self, tmp_path, monkeypatch
    ):
        """Bootstrap still deploys there today, so removing the fallback before
        the cutover would drop live user configuration."""
        legacy = tmp_path / "home/.claude/config"
        legacy.mkdir(parents=True)
        (legacy / "delegation.json").write_text(
            json.dumps({"default_backend": "cursor"})
        )
        monkeypatch.setattr(
            delegate.constants, "XDG_CONFIG_DIR", str(tmp_path / "absent")
        )
        monkeypatch.setattr(delegate.constants, "HOME_CONFIG_DIR", str(legacy))
        monkeypatch.delenv("MANIFEST_CONFIG_DIR", raising=False)

        assert delegate.load_user_config()["default_backend"] == "cursor"

    def test_explicit_dir_and_env_still_outrank_both(self, tmp_path, monkeypatch):
        explicit = tmp_path / "explicit"
        explicit.mkdir()
        (explicit / "delegation.json").write_text(
            json.dumps({"default_backend": "codex"})
        )
        monkeypatch.setattr(
            delegate.constants, "XDG_CONFIG_DIR", str(tmp_path / "absent")
        )
        monkeypatch.setattr(
            delegate.constants, "HOME_CONFIG_DIR", str(tmp_path / "absent2")
        )

        assert (
            delegate.load_user_config(explicit_dir=str(explicit))["default_backend"]
            == "codex"
        )


def test_xdg_config_dir_matches_the_coordinator_convention(monkeypatch):
    """`src/manifest_agent/paths.py` resolves `$XDG_CONFIG_HOME/manifest`; the
    bundle must not invent a second location for the same configuration."""
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg-probe")
    assert delegate.constants._xdg_config_dir() == os.path.join(
        "/tmp/xdg-probe", "manifest"
    )
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert delegate.constants._xdg_config_dir().endswith("/.config/manifest")
