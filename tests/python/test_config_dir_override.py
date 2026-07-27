#!/usr/bin/env python3
"""T007/FR-020: MANIFEST_CONFIG_DIR override for the agents config loader.

Without an override every path in agents/config.py resolves to the *deployed*
``~/.claude/config``, so a repo-side YAML edit does nothing until bootstrap.sh
copies it out, and any test that does not pass an explicit path silently reads
the developer's real home. Both resolution modes are covered here, plus the
precedence rule between them.

Run with: pytest tests/python/test_config_dir_override.py -v
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from agents.config import (
    MANIFEST_CONFIG_DIR_ENV,
    Config,
    ServiceConfig,
    load_agent_roster,
    resolve_config_path,
)


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """A throwaway config dir wired in via the override."""
    d = tmp_path / "config"
    d.mkdir()
    monkeypatch.setenv(MANIFEST_CONFIG_DIR_ENV, str(d))
    return d


class TestResolveConfigPath:
    def test_default_resolves_to_deployed_home(self, monkeypatch):
        """With no override, the deployed home is still the answer."""
        monkeypatch.delenv(MANIFEST_CONFIG_DIR_ENV, raising=False)
        resolved = resolve_config_path("parallel_agent.yml")
        assert resolved == os.path.expanduser("~/.claude/config/parallel_agent.yml")

    def test_env_override_redirects(self, config_dir):
        resolved = resolve_config_path("parallel_agent.yml")
        assert resolved == str(config_dir / "parallel_agent.yml")

    def test_env_override_expands_user(self, monkeypatch):
        monkeypatch.setenv(MANIFEST_CONFIG_DIR_ENV, "~/somewhere/config")
        resolved = resolve_config_path("services.yml")
        assert resolved == os.path.expanduser("~/somewhere/config/services.yml")

    def test_explicit_argument_beats_the_environment(self, config_dir):
        """A caller that names a path is being specific.

        If the env won here, a test passing a fixture path would still depend on
        ambient environment state -- the exact coupling this override exists to
        remove.
        """
        resolved = resolve_config_path("services.yml", "/explicit/path.yml")
        assert resolved == "/explicit/path.yml"

    def test_empty_env_value_falls_back_rather_than_resolving_to_root(
        self, monkeypatch
    ):
        """An empty override must not produce "/parallel_agent.yml"."""
        monkeypatch.setenv(MANIFEST_CONFIG_DIR_ENV, "")
        resolved = resolve_config_path("parallel_agent.yml")
        assert resolved == os.path.expanduser("~/.claude/config/parallel_agent.yml")


class TestConfigHonoursOverride:
    def test_config_reads_the_overridden_dir(self, config_dir):
        (config_dir / "parallel_agent.yml").write_text("rate_limits:\n  claude: 999\n")
        cfg = Config()
        assert cfg.config_path == str(config_dir / "parallel_agent.yml")
        assert cfg.get("rate_limits.claude") == 999

    def test_explicit_path_still_wins_for_config(self, config_dir, tmp_path):
        other = tmp_path / "other.yml"
        other.write_text("rate_limits:\n  claude: 1\n")
        cfg = Config(config_path=str(other))
        assert cfg.config_path == str(other)
        assert cfg.get("rate_limits.claude") == 1

    def test_service_config_reads_the_overridden_dir(self, config_dir):
        (config_dir / "services.yml").write_text(
            "services:\n  claude:\n    enabled: false\n"
        )
        svc = ServiceConfig()
        assert svc.config_path == str(config_dir / "services.yml")
        assert svc._data["services"]["claude"]["enabled"] is False

    def test_agent_roster_reads_the_overridden_dir(self, config_dir):
        (config_dir / "agent_roster.yml").write_text(
            "agents:\n  claude:\n    home_dir: ~/.claude\n"
        )
        roster = load_agent_roster()
        assert "claude" in roster
        assert roster["claude"]["home_dir"] == "~/.claude"

    def test_missing_file_under_override_still_yields_defaults(self, config_dir):
        """The override redirects where we look, not whether we cope."""
        cfg = Config()
        assert "rate_limits" in cfg.config
        assert "model_tiers" in cfg.config

    def test_override_does_not_read_the_real_home(self, config_dir):
        """The point of the whole exercise: ambient home state is not consulted."""
        cfg = Config()
        assert os.path.expanduser("~/.claude/config") not in cfg.config_path
