#!/usr/bin/env python3
"""Per-module unit tests for agents.config.

Tests Config, ServiceConfig, Logger, and RateLimiter in isolation.
No external agent connections required.
"""

import asyncio
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = str(REPO_ROOT / "configs" / "claude" / "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from agents.config import Config, Logger, RateLimiter, ServiceConfig

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_config_when_file_missing(self, tmp_path):
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        assert isinstance(config.config, dict)
        assert "rate_limits" in config.config
        assert "model_tiers" in config.config

    def test_default_config_has_claude_tiers(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        assert "haiku" in config.config["model_tiers"]["claude"]
        assert "sonnet" in config.config["model_tiers"]["claude"]
        assert "opus" in config.config["model_tiers"]["claude"]

    def test_default_config_has_gemini_tiers(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        assert "flash" in config.config["model_tiers"]["gemini"]
        assert "pro" in config.config["model_tiers"]["gemini"]

    def test_get_dot_notation(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        result = config.get("model_tiers.claude.haiku")
        # Assert the lookup mechanism, not the pin. This test is about dot
        # notation resolving to the right leaf; hardcoding a model ID here made
        # it fail on every model refresh for a reason unrelated to what it
        # covers. The nested-access comparison still catches a wrong key or a
        # None return (the .startswith would raise on None).
        assert result == config.config["model_tiers"]["claude"]["haiku"]
        assert result.startswith("claude-haiku-")

    def test_get_returns_default_for_missing_key(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        result = config.get("nonexistent.key", "fallback")
        assert result == "fallback"

    def test_get_returns_none_when_no_default(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        result = config.get("nonexistent.key")
        assert result is None

    def test_load_from_yaml_file(self, tmp_path):
        config_file = tmp_path / "config.yml"
        config_file.write_text("rate_limits:\n  claude:\n    requests_per_minute: 30\n")
        config = Config(config_path=str(config_file))
        assert config.get("rate_limits.claude.requests_per_minute") == 30

    def test_default_timeouts(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        assert config.get("timeouts.default") == 120
        assert config.get("timeouts.review") == 600

    def test_default_consensus_thresholds(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        thresholds = config.get("validation.consensus_threshold")
        assert thresholds["high"] == 0.80
        assert thresholds["medium"] == 0.50


# ---------------------------------------------------------------------------
# ServiceConfig
# ---------------------------------------------------------------------------


class TestServiceConfig:
    def test_defaults_when_file_missing(self, tmp_path):
        svc = ServiceConfig(config_path=str(tmp_path / "none.yml"))
        assert svc.is_enabled("claude") is True
        assert svc.is_enabled("gemini") is True

    def test_minimum_agents_default(self, tmp_path):
        svc = ServiceConfig(config_path=str(tmp_path / "none.yml"))
        assert svc.minimum_agents == 2

    def test_is_enabled_from_yaml(self, tmp_path):
        cfg = tmp_path / "services.yml"
        cfg.write_text("services:\n  claude:\n    enabled: false\n")
        svc = ServiceConfig(config_path=str(cfg))
        assert svc.is_enabled("claude") is False

    def test_check_minimum_agents_ok(self, tmp_path):
        svc = ServiceConfig(config_path=str(tmp_path / "none.yml"))
        assert svc.check_minimum_agents(2) is None

    def test_check_minimum_agents_warning(self, tmp_path):
        svc = ServiceConfig(config_path=str(tmp_path / "none.yml"))
        warning = svc.check_minimum_agents(1)
        assert warning is not None
        assert "Warning" in warning

    def test_unknown_service_defaults_enabled(self, tmp_path):
        svc = ServiceConfig(config_path=str(tmp_path / "none.yml"))
        assert svc.is_enabled("unknown_service") is True

    def test_service_absent_from_yaml_falls_back_to_roster_default(
        self, tmp_path, monkeypatch
    ):
        """A services.yml written before an agent existed must not silently
        ENABLE that agent. Without the roster fallback, every machine that has
        not re-bootstrapped would put an opt-in, login-gated agent into the
        panel un-asked — and an unauthenticated agent errors rather than
        abstaining, which drags the consensus metric down.
        """
        roster = tmp_path / "agent_roster.yml"
        roster.write_text(
            "agents:\n"
            "  devin:\n"
            "    name: devin\n"
            "    enabled_default: false\n"
            "  cursor:\n"
            "    name: cursor\n"
            "    enabled_default: true\n"
        )
        monkeypatch.setenv("MANIFEST_CONFIG_DIR", str(tmp_path))

        cfg = tmp_path / "services.yml"
        cfg.write_text("services:\n  claude:\n    enabled: true\n")
        svc = ServiceConfig(config_path=str(cfg))

        assert svc.is_enabled("devin") is False  # roster says opt-in
        assert svc.is_enabled("cursor") is True  # roster says default-on
        assert svc.is_enabled("claude") is True  # explicit in services.yml

    def test_explicit_services_yml_entry_beats_roster_default(
        self, tmp_path, monkeypatch
    ):
        """The roster is only the fallback: a user who turned devin ON in
        services.yml keeps it on."""
        roster = tmp_path / "agent_roster.yml"
        roster.write_text(
            "agents:\n  devin:\n    name: devin\n    enabled_default: false\n"
        )
        monkeypatch.setenv("MANIFEST_CONFIG_DIR", str(tmp_path))

        cfg = tmp_path / "services.yml"
        cfg.write_text("services:\n  devin:\n    enabled: true\n")
        assert ServiceConfig(config_path=str(cfg)).is_enabled("devin") is True


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------


class TestLogger:
    def test_logger_creation(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        logger = Logger(config)
        assert logger is not None

    def test_correlation_id(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        logger = Logger(config)
        logger.set_correlation_id("test-123")
        assert logger.correlation_id == "test-123"

    def test_logging_methods_do_not_raise(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        logger = Logger(config)
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")
        logger.debug("debug message")


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_creation_with_defaults(self):
        limiter = RateLimiter()
        assert limiter.rpm == 60
        assert limiter.burst_size == 5
        assert limiter.tokens == 5

    def test_creation_with_custom_values(self):
        limiter = RateLimiter(requests_per_minute=30, burst_size=3)
        assert limiter.rpm == 30
        assert limiter.burst_size == 3

    def test_acquire_decrements_tokens(self):
        limiter = RateLimiter(burst_size=5)
        asyncio.run(limiter.acquire())
        assert limiter.tokens == 4

    def test_acquire_all_tokens(self):
        limiter = RateLimiter(burst_size=3)
        for _ in range(3):
            asyncio.run(limiter.acquire())
        assert limiter.tokens == 0

    def test_ignores_extra_kwargs(self):
        limiter = RateLimiter(tokens_per_minute=1000, unknown_param="value")
        assert limiter.rpm == 60


# ---------------------------------------------------------------------------
# cli_agents config block
# ---------------------------------------------------------------------------

REPO_YAML = REPO_ROOT / "configs" / "claude" / "config" / "parallel_agent.yml"


class TestCliAgentsConfig:
    def test_default_config_has_cli_agents(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        for provider in ("cursor", "codex", "antigravity"):
            spec = config.get(f"cli_agents.{provider}")
            assert spec is not None, f"missing cli_agents.{provider}"
            assert "binary" in spec
            assert "base_args" in spec
            assert "model_args" in spec
            assert spec.get("output") in ("stdout", "file_then_stdout")

    def test_cursor_uses_cursor_agent_binary_headless(self, tmp_path):
        """cursor backend must invoke cursor-agent headless+read-only."""
        spec = Config(config_path=str(tmp_path / "none.yml")).get("cli_agents.cursor")
        assert spec["binary"] == "cursor-agent"
        assert "--print" in spec["base_args"]
        assert spec["base_args"][spec["base_args"].index("--mode") + 1] == "ask"

    def test_default_config_has_antigravity_entries(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        assert config.get("rate_limits.antigravity.requests_per_minute") == 100
        assert config.get("credit_fallback.antigravity") == [
            "advanced",
            "flash",
            "mini",
        ]
        tiers = config.get("model_tiers.antigravity")
        assert set(tiers) == {"mini", "flash", "advanced"}

    def test_defaults_match_repo_yaml(self, tmp_path):
        """config.py defaults and parallel_agent.yml must never disagree."""
        with open(REPO_YAML) as f:
            repo = yaml.safe_load(f)
        defaults = Config(config_path=str(tmp_path / "none.yml")).config
        for section in (
            "cli_agents",
            "model_tiers",
            "credit_fallback",
            "rate_limits",
            "cddl_invoke",
            "skillclaw_evolve",
        ):
            assert repo[section] == defaults[section], (
                f"{section} drifted between parallel_agent.yml and "
                f"config.py _default_config()"
            )


class TestSynthesisConfig:
    def test_default_config_has_synthesis_backend(self, tmp_path):
        config = Config(config_path=str(tmp_path / "none.yml"))
        assert config.get("synthesis.backend") == "auto"
        assert config.get("synthesis.enabled") is True
        assert config.get("synthesis.threshold") == 0.50

    def test_synthesis_defaults_match_repo_yaml(self, tmp_path):
        with open(REPO_YAML) as f:
            repo = yaml.safe_load(f)
        defaults = Config(config_path=str(tmp_path / "none.yml")).config
        assert repo["synthesis"] == defaults["synthesis"]


class TestConfigLoadFailures:
    """What happens when parallel_agent.yml exists but cannot be used.

    The split is deliberate: an EMPTY file states no intent, so defaults are the
    honest reading; a MALFORMED file states an intent that could not be parsed,
    and silently substituting defaults there would hand the user a running
    system that ignores the config they just edited (CON-007 — a caught error is
    never dropped).
    """

    def test_empty_file_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / "parallel_agent.yml"
        path.write_text("", encoding="utf-8")
        config = Config(config_path=str(path))
        assert config.config["model_tiers"]["claude"]["opus"]

    def test_whitespace_and_comments_only_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / "parallel_agent.yml"
        path.write_text("# just a comment\n\n   \n", encoding="utf-8")
        config = Config(config_path=str(path))
        assert "model_tiers" in config.config

    def test_malformed_yaml_raises_naming_the_file(self, tmp_path):
        path = tmp_path / "parallel_agent.yml"
        path.write_text("model_tiers:\n  claude: [unclosed\n", encoding="utf-8")
        with pytest.raises(ValueError) as excinfo:
            Config(config_path=str(path))
        assert str(path) in str(excinfo.value)
        assert excinfo.value.__cause__ is not None, "original parse error was discarded"

    def test_non_mapping_yaml_raises(self, tmp_path):
        """A list parses fine but every later .get() would fail far from here."""
        path = tmp_path / "parallel_agent.yml"
        path.write_text("- one\n- two\n", encoding="utf-8")
        with pytest.raises(ValueError) as excinfo:
            Config(config_path=str(path))
        assert str(path) in str(excinfo.value)

    def test_valid_file_is_still_loaded_verbatim(self, tmp_path):
        path = tmp_path / "parallel_agent.yml"
        path.write_text(
            "model_tiers:\n  claude:\n    opus: probe-model\n", encoding="utf-8"
        )
        config = Config(config_path=str(path))
        assert config.get("model_tiers.claude.opus") == "probe-model"
