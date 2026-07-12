#!/usr/bin/env python3
"""
Pytest tests for .claude/scripts/parallel_agent.py (Python parallel agent).

Tests cover:
- Config class: loading, default config, dot-notation access
- RateLimiter: creation, token management
- ValidationEngine: tier1/tier2 checks, verdict computation
- SynthesisEngine: template loading, high-consensus skip
- BaseAgent: credit exhaustion detection
- Orchestrator: consensus calculation
- Argument parsing via main()

Run with: pytest tests/python/test_parallel_agent.py -v
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

# Add the scripts directory to path so we can import the module.
# In the repo the source lives at configs/claude/scripts/, not .claude/scripts/.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = str(REPO_ROOT / "configs" / "claude" / "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from agents.config import Config, Logger, RateLimiter, ServiceConfig
from agents.orchestrator import Orchestrator, check_credits
from agents.runners import BaseAgent, CLIAgent
from agents.synthesis import SynthesisEngine
from agents.validation import ValidationEngine

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfig:
    """Test the Config configuration manager."""

    def test_default_config_when_file_missing(self, tmp_path):
        """Config falls back to defaults when YAML file does not exist."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        assert isinstance(config.config, dict)
        # Defaults should include rate_limits and model_tiers
        assert "rate_limits" in config.config
        assert "model_tiers" in config.config

    def test_default_config_has_claude_tiers(self, tmp_path):
        """Default config includes Claude model tier mappings."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        tiers = config.get("model_tiers.claude")
        assert tiers is not None
        assert "haiku" in tiers
        assert "sonnet" in tiers
        assert "opus" in tiers

    def test_default_config_has_gemini_tiers(self, tmp_path):
        """Default config includes Gemini model tier mappings."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        tiers = config.get("model_tiers.gemini")
        assert tiers is not None
        assert "flash" in tiers
        assert "pro" in tiers

    def test_get_dot_notation(self, tmp_path):
        """Config.get supports dot-notation key access."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        rpm = config.get("rate_limits.claude.requests_per_minute")
        assert rpm == 60

    def test_get_returns_default_for_missing_key(self, tmp_path):
        """Config.get returns the default value for a missing key."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        value = config.get("this.key.does.not.exist", "fallback")
        assert value == "fallback"

    def test_get_returns_none_when_no_default(self, tmp_path):
        """Config.get returns None when key is missing and no default given."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        value = config.get("missing.key")
        assert value is None

    def test_load_from_yaml_file(self, tmp_path):
        """Config loads values from an actual YAML file."""
        yaml_content = "custom_key: custom_value\nnested:\n  inner: 42\n"
        config_file = tmp_path / "test_config.yml"
        config_file.write_text(yaml_content)

        config = Config(config_path=str(config_file))
        assert config.get("custom_key") == "custom_value"
        assert config.get("nested.inner") == 42

    def test_default_timeouts(self, tmp_path):
        """Default config includes timeout settings."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        assert config.get("timeouts.default") == 120
        assert config.get("timeouts.review") == 600

    def test_default_consensus_thresholds(self, tmp_path):
        """Default config includes consensus threshold settings."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        thresholds = config.get("validation.consensus_threshold")
        assert thresholds is not None
        assert thresholds["high"] == 0.80
        assert thresholds["medium"] == 0.50


# ---------------------------------------------------------------------------
# RateLimiter tests
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Test the token bucket rate limiter."""

    def test_creation_with_defaults(self):
        """RateLimiter initializes with correct defaults."""
        limiter = RateLimiter()
        assert limiter.rpm == 60
        assert limiter.burst_size == 5
        assert limiter.tokens == 5

    def test_creation_with_custom_values(self):
        """RateLimiter accepts custom rpm and burst_size."""
        limiter = RateLimiter(requests_per_minute=120, burst_size=10)
        assert limiter.rpm == 120
        assert limiter.burst_size == 10
        assert limiter.tokens == 10

    @pytest.mark.asyncio
    async def test_acquire_decrements_tokens(self):
        """Acquiring a token decrements the token count."""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        await limiter.acquire()
        assert limiter.tokens == 4

    @pytest.mark.asyncio
    async def test_acquire_all_tokens(self):
        """All burst tokens can be acquired."""
        limiter = RateLimiter(requests_per_minute=60, burst_size=3)
        for _ in range(3):
            await limiter.acquire()
        assert limiter.tokens == 0

    def test_ignores_extra_kwargs(self):
        """RateLimiter ignores unknown kwargs (e.g., tokens_per_minute)."""
        limiter = RateLimiter(
            requests_per_minute=60,
            burst_size=5,
            tokens_per_minute=10000,
            unknown_param="ignored",
        )
        assert limiter.rpm == 60


# ---------------------------------------------------------------------------
# ValidationEngine tests
# ---------------------------------------------------------------------------


class TestValidationEngine:
    """Test the validation engine's tier1/tier2 checks and verdict logic."""

    def _make_config(self, tmp_path):
        """Create a Config with no real file."""
        return Config(config_path=str(tmp_path / "nonexistent.yml"))

    def test_security_check_detects_hardcoded_secret(self, tmp_path):
        """Tier1 security check flags hardcoded API keys."""
        config = self._make_config(tmp_path)
        validator = ValidationEngine(config)

        results = {
            "claude": {
                "status": "complete",
                "output": 'Found api_key = "sk-secret-12345" in source',
            }
        }
        check = validator._check_security(results, {})
        assert not check["passed"]
        assert len(check["issues"]) > 0

    def test_security_check_passes_clean_code(self, tmp_path):
        """Tier1 security check passes when no issues are found."""
        config = self._make_config(tmp_path)
        validator = ValidationEngine(config)

        results = {
            "claude": {
                "status": "complete",
                "output": "Code uses environment variables for all secrets.",
            }
        }
        check = validator._check_security(results, {})
        assert check["passed"]
        assert len(check["issues"]) == 0

    def test_error_handling_detects_bare_except(self, tmp_path):
        """Tier1 error handling check detects bare except clauses."""
        config = self._make_config(tmp_path)
        validator = ValidationEngine(config)

        results = {
            "gemini": {
                "status": "complete",
                "output": "Found bare except: clause on line 42",
            }
        }
        check = validator._check_error_handling(results, {})
        assert not check["passed"]
        assert any("except" in issue.lower() for issue in check["issues"])

    def test_bug_detection_scores_null_references(self, tmp_path):
        """Tier2 bug detection lowers score for null reference mentions."""
        config = self._make_config(tmp_path)
        validator = ValidationEngine(config)

        results = {
            "cursor": {
                "status": "complete",
                "output": "Warning: potential null reference on line 55",
            }
        }
        check = validator._check_bugs(results, {})
        assert check["score"] < 1.0
        assert len(check["concerns"]) > 0

    def test_performance_check_detects_quadratic(self, tmp_path):
        """Tier2 performance check flags O(n^2) complexity."""
        config = self._make_config(tmp_path)
        validator = ValidationEngine(config)

        results = {
            "claude": {
                "status": "complete",
                "output": "This nested loop results in O(n^2) complexity",
            }
        }
        check = validator._check_performance(results, {})
        assert check["score"] < 1.0

    def test_verdict_approved(self, tmp_path):
        """Verdict is APPROVED when tier1 passes and tier2 >= 0.60."""
        config = self._make_config(tmp_path)
        validator = ValidationEngine(config)

        tier1 = {"passed": True, "score": 1.0}
        tier2 = {"score": 0.75}
        assert validator._compute_verdict(tier1, tier2, {}) == "APPROVED"

    def test_verdict_needs_review(self, tmp_path):
        """Verdict is NEEDS_REVIEW when tier1 passes but tier2 < 0.60."""
        config = self._make_config(tmp_path)
        validator = ValidationEngine(config)

        tier1 = {"passed": True, "score": 1.0}
        tier2 = {"score": 0.45}
        assert validator._compute_verdict(tier1, tier2, {}) == "NEEDS_REVIEW"

    def test_verdict_blocked(self, tmp_path):
        """Verdict is BLOCKED when tier1 fails."""
        config = self._make_config(tmp_path)
        validator = ValidationEngine(config)

        tier1 = {"passed": False, "score": 0.0}
        tier2 = {"score": 0.90}
        assert validator._compute_verdict(tier1, tier2, {}) == "BLOCKED"

    def test_verdict_with_custom_threshold_override(self, tmp_path):
        """Verdict respects tier2_threshold from overrides."""
        config = self._make_config(tmp_path)
        validator = ValidationEngine(config)

        tier1 = {"passed": True, "score": 1.0}
        tier2 = {"score": 0.55}

        # Without override: NEEDS_REVIEW (0.55 < 0.60)
        assert validator._compute_verdict(tier1, tier2, {}) == "NEEDS_REVIEW"

        # With override: APPROVED (0.55 >= 0.50)
        overrides = {"tier2_threshold": 0.50}
        assert validator._compute_verdict(tier1, tier2, overrides) == "APPROVED"

    def test_skips_incomplete_agents(self, tmp_path):
        """Validation checks skip agents with non-complete status."""
        config = self._make_config(tmp_path)
        validator = ValidationEngine(config)

        results = {
            "claude": {
                "status": "failed",
                "output": 'api_key = "secret"',  # Would trigger if status were complete
            }
        }
        check = validator._check_security(results, {})
        # Failed agent should be skipped, so no issues detected
        assert check["passed"]


# ---------------------------------------------------------------------------
# SynthesisEngine tests
# ---------------------------------------------------------------------------


class TestSynthesisEngine:
    """Test the synthesis engine."""

    def test_creation(self, tmp_path):
        """SynthesisEngine can be created without errors."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        synthesizer = SynthesisEngine(config)
        assert synthesizer.config is not None

    @pytest.mark.asyncio
    async def test_skips_synthesis_when_consensus_high(self, tmp_path):
        """Synthesis is skipped when consensus is above threshold."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        synthesizer = SynthesisEngine(config)

        results = {
            "gemini": {"status": "complete", "output": "Approach A"},
            "claude": {"status": "complete", "output": "Approach A"},
        }
        consensus = {"consensus_score": 90}  # Well above default 50% threshold

        result = await synthesizer.synthesize("Test task", results, consensus)
        assert result is None  # No synthesis needed

    def test_template_is_string(self, tmp_path):
        """Synthesis template loads as a string (empty if file missing)."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        synthesizer = SynthesisEngine(config)
        assert isinstance(synthesizer.synthesis_template, str)


# ---------------------------------------------------------------------------
# BaseAgent tests
# ---------------------------------------------------------------------------


class TestBaseAgent:
    """Test BaseAgent credit exhaustion detection."""

    def _make_agent(self, tmp_path):
        """Create a minimal BaseAgent subclass for testing."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()

        class StubAgent(BaseAgent):
            async def _execute_impl(self, prompt, mode):
                return {"status": "complete", "output": "stub"}

        return StubAgent("test", "test-model", 60, limiter, config)

    def test_credit_exhaustion_detection_quota(self, tmp_path):
        """Detects quota-related credit exhaustion errors."""
        agent = self._make_agent(tmp_path)
        assert agent._is_credit_exhaustion_error("quota exceeded for model")

    def test_credit_exhaustion_detection_rate_limit(self, tmp_path):
        """Detects rate limit errors."""
        agent = self._make_agent(tmp_path)
        assert agent._is_credit_exhaustion_error("rate limit exceeded")

    def test_credit_exhaustion_detection_429(self, tmp_path):
        """Detects HTTP 429 errors."""
        agent = self._make_agent(tmp_path)
        assert agent._is_credit_exhaustion_error("received 429 too many requests")

    def test_no_false_positive_on_normal_error(self, tmp_path):
        """Normal errors are not flagged as credit exhaustion."""
        agent = self._make_agent(tmp_path)
        assert not agent._is_credit_exhaustion_error("connection timed out")
        assert not agent._is_credit_exhaustion_error("invalid model name")

    @pytest.mark.asyncio
    async def test_execute_returns_result(self, tmp_path):
        """BaseAgent.execute returns a result dict from _execute_impl."""
        agent = self._make_agent(tmp_path)
        result = await agent.execute("test prompt")
        assert result["status"] == "complete"
        assert result["output"] == "stub"
        assert "duration_seconds" in result

    @pytest.mark.asyncio
    async def test_execute_timeout(self, tmp_path):
        """BaseAgent.execute handles timeout gracefully."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()

        class SlowAgent(BaseAgent):
            async def _execute_impl(self, prompt, mode):
                await asyncio.sleep(10)
                return {"status": "complete", "output": "never reached"}

        agent = SlowAgent(
            "slow", "model", timeout=1, rate_limiter=limiter, config=config
        )
        result = await agent.execute("test")
        assert result["status"] == "failed"
        assert "timeout" in result["error"]


# ---------------------------------------------------------------------------
# Orchestrator consensus tests
# ---------------------------------------------------------------------------


class TestOrchestratorConsensus:
    """Test the consensus calculation logic."""

    def _make_orchestrator(self, tmp_path, agents=None):
        """Create an Orchestrator with no real agents."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        return Orchestrator(agents or [], config, streaming=False)

    def test_consensus_with_similar_outputs(self, tmp_path):
        """High consensus when outputs share many common words."""
        orch = self._make_orchestrator(tmp_path)

        results = {
            "claude": {
                "status": "complete",
                "output": "The code has proper error handling and input validation.",
            },
            "gemini": {
                "status": "complete",
                "output": "The code includes error handling and proper input validation.",
            },
        }
        consensus = orch._calculate_consensus(results)
        assert consensus["consensus_score"] > 0
        assert consensus["agent_count"] == 2

    def test_consensus_with_single_agent(self, tmp_path):
        """Consensus returns low score with only one agent."""
        orch = self._make_orchestrator(tmp_path)

        results = {
            "claude": {"status": "complete", "output": "Some analysis output."},
        }
        consensus = orch._calculate_consensus(results)
        assert consensus["consensus_score"] == 0
        assert consensus["agent_count"] == 1
        assert consensus["confidence"] == "low"

    def test_consensus_with_no_complete_agents(self, tmp_path):
        """Consensus handles all-failed agents gracefully."""
        orch = self._make_orchestrator(tmp_path)

        results = {
            "claude": {"status": "failed", "output": ""},
            "gemini": {"status": "failed", "output": ""},
        }
        consensus = orch._calculate_consensus(results)
        assert consensus["consensus_score"] == 0
        assert consensus["confidence"] == "low"

    def test_confidence_levels(self, tmp_path):
        """Confidence level is computed from consensus score thresholds."""
        orch = self._make_orchestrator(tmp_path)

        # Build outputs with controlled overlap
        # Use many unique long words so score can vary
        common = "authentication authorization middleware validation"
        results_high = {
            "a": {"status": "complete", "output": common + " extra1"},
            "b": {"status": "complete", "output": common + " extra2"},
        }
        consensus_high = orch._calculate_consensus(results_high)
        # Most words are shared, so confidence should be medium or high
        assert consensus_high["confidence"] in ("medium", "high")


# ---------------------------------------------------------------------------
# Logger tests
# ---------------------------------------------------------------------------


class TestLogger:
    """Test the Logger class."""

    def test_logger_creation(self, tmp_path):
        """Logger can be created without errors."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        logger = Logger(config)
        assert logger.logger is not None

    def test_correlation_id(self, tmp_path):
        """Correlation ID can be set and read back."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        logger = Logger(config)
        logger.set_correlation_id("test-123")
        assert logger.correlation_id == "test-123"

    def test_logging_methods_do_not_raise(self, tmp_path):
        """All logging methods execute without raising exceptions."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        logger = Logger(config)
        logger.set_correlation_id("test")

        # None of these should raise
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")


# ---------------------------------------------------------------------------
# JSON output format tests
# ---------------------------------------------------------------------------


class TestJSONOutputFormat:
    """Test that the expected JSON output schema is well-formed."""

    def test_mock_fixture_matches_schema(self):
        """The mock_agent_output.json fixture has the expected structure."""
        fixture_path = (
            Path(__file__).resolve().parent.parent
            / "fixtures"
            / "mock_agent_output.json"
        )
        if not fixture_path.exists():
            pytest.skip("Fixture file not found")

        with open(fixture_path) as f:
            data = json.load(f)

        # Top-level keys
        assert "timestamp" in data
        assert "mode" in data
        assert "prompt" in data
        assert "agents" in data
        assert "cross_verification" in data

        # Agent sub-keys
        for agent_name in ("cursor", "gemini", "claude"):
            agent = data["agents"][agent_name]
            assert "status" in agent
            assert "validated" in agent
            assert "output" in agent

        # Cross-verification
        cv = data["cross_verification"]
        assert "consensus_score" in cv
        assert "confidence" in cv
        assert "agent_count" in cv
        assert isinstance(cv["consensus_score"], int)


# ---------------------------------------------------------------------------
# ServiceConfig tests
# ---------------------------------------------------------------------------


class TestServiceConfig:
    """Test the ServiceConfig class for services.yml loading."""

    def test_defaults_when_file_missing(self, tmp_path):
        """ServiceConfig falls back to all-enabled defaults."""
        sc = ServiceConfig(config_path=str(tmp_path / "nonexistent.yml"))
        assert sc.is_enabled("claude") is True
        assert sc.is_enabled("gemini") is True
        assert sc.is_enabled("cursor") is True
        assert sc.is_enabled("codex") is True

    def test_minimum_agents_default(self, tmp_path):
        """Default minimum_agents is 2."""
        sc = ServiceConfig(config_path=str(tmp_path / "nonexistent.yml"))
        assert sc.minimum_agents == 2

    def test_is_enabled_from_yaml(self, tmp_path):
        """ServiceConfig reads enabled state from YAML."""
        yaml_content = (
            "services:\n"
            "  claude:\n"
            "    enabled: true\n"
            "  gemini:\n"
            "    enabled: false\n"
            "  cursor:\n"
            "    enabled: true\n"
            "  codex:\n"
            "    enabled: false\n"
            "minimum_agents: 3\n"
        )
        config_file = tmp_path / "services.yml"
        config_file.write_text(yaml_content)

        sc = ServiceConfig(config_path=str(config_file))
        assert sc.is_enabled("claude") is True
        assert sc.is_enabled("gemini") is False
        assert sc.is_enabled("cursor") is True
        assert sc.is_enabled("codex") is False
        assert sc.minimum_agents == 3

    def test_check_minimum_agents_ok(self, tmp_path):
        """No warning when agent count meets minimum."""
        sc = ServiceConfig(config_path=str(tmp_path / "nonexistent.yml"))
        assert sc.check_minimum_agents(2) is None
        assert sc.check_minimum_agents(3) is None

    def test_check_minimum_agents_warning(self, tmp_path):
        """Warning returned when agent count is below minimum."""
        sc = ServiceConfig(config_path=str(tmp_path / "nonexistent.yml"))
        warning = sc.check_minimum_agents(1)
        assert warning is not None
        assert "1 agent" in warning

    def test_unknown_service_defaults_enabled(self, tmp_path):
        """Unknown service names default to enabled."""
        sc = ServiceConfig(config_path=str(tmp_path / "nonexistent.yml"))
        assert sc.is_enabled("unknown_agent") is True


# ---------------------------------------------------------------------------
# Codex-via-CLIAgent regression tests
# ---------------------------------------------------------------------------


class TestCodexViaCLIAgent:
    """Codex behavior through the generic CLIAgent (regression for the refactor)."""

    def test_resolve_model_auto(self, tmp_path):
        """Auto tier resolves to None (let codex choose)."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()
        agent = CLIAgent("codex", "auto", 60, limiter, config=config)
        assert agent.model_name is None

    def test_resolve_model_named_tier(self, tmp_path):
        """Named tier resolves to correct model from config."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()
        agent = CLIAgent("codex", "mini", 60, limiter, config=config)
        assert agent.model_name == "gpt-5.4-mini"

    def test_resolve_model_custom(self, tmp_path):
        """Custom model name passes through as-is."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()
        agent = CLIAgent("codex", "custom-model-123", 60, limiter, config=config)
        assert agent.model_name == "custom-model-123"

    @pytest.mark.asyncio
    async def test_execute_missing_codex(self, tmp_path, monkeypatch):
        """Returns 'missing' status when codex is not installed."""
        import shutil

        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()
        agent = CLIAgent("codex", "auto", 60, limiter, config=config)

        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        result = await agent._execute_impl("test prompt", "prompt")
        assert result["status"] == "missing"


# ---------------------------------------------------------------------------
# Default config codex entries tests
# ---------------------------------------------------------------------------


class TestDefaultConfigCodex:
    """Test that default config includes codex entries."""

    def test_default_config_has_codex_rate_limits(self, tmp_path):
        """Default config includes codex rate limits."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        codex_rl = config.get("rate_limits.codex")
        assert codex_rl is not None
        assert codex_rl["requests_per_minute"] == 100

    def test_default_config_has_codex_model_tiers(self, tmp_path):
        """Default config includes codex model tier mappings."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        tiers = config.get("model_tiers.codex")
        assert tiers is not None
        assert "mini" in tiers
        assert "flash" in tiers
        assert "advanced" in tiers

    def test_default_config_has_codex_credit_fallback(self, tmp_path):
        """Default config includes codex credit fallback chain."""
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        fallback = config.get("credit_fallback.codex")
        assert fallback is not None
        assert fallback == ["advanced", "flash", "mini"]


# ---------------------------------------------------------------------------
# File existence validation tests (--review / --analyze / --improve)
# ---------------------------------------------------------------------------


class TestFileExistenceValidation:
    """Test that --review, --analyze, and --improve fail fast on missing files."""

    SCRIPT = str(REPO_ROOT / "configs" / "claude" / "scripts" / "parallel_agent.py")

    def _run(self, flag: str, path: str):
        import subprocess

        return subprocess.run(
            [sys.executable, self.SCRIPT, flag, path],
            capture_output=True,
            text=True,
        )

    def test_review_nonexistent_file_exits_nonzero(self, tmp_path):
        """--review with a missing file must exit 1 before contacting any agent."""
        result = self._run("--review", str(tmp_path / "missing.py"))
        assert result.returncode == 1

    def test_review_nonexistent_file_prints_error(self, tmp_path):
        """--review with a missing file must print an error message to stderr."""
        result = self._run("--review", str(tmp_path / "missing.py"))
        assert (
            "file not found" in result.stderr.lower()
            or "error" in result.stderr.lower()
        )

    def test_analyze_nonexistent_file_exits_nonzero(self, tmp_path):
        """--analyze with a missing file must exit 1 before contacting any agent."""
        result = self._run("--analyze", str(tmp_path / "missing.py"))
        assert result.returncode == 1

    def test_analyze_nonexistent_file_prints_error(self, tmp_path):
        """--analyze with a missing file must print an error message to stderr."""
        result = self._run("--analyze", str(tmp_path / "missing.py"))
        assert (
            "file not found" in result.stderr.lower()
            or "error" in result.stderr.lower()
        )

    def test_improve_nonexistent_file_exits_nonzero(self, tmp_path):
        """--improve with a missing file must exit 1 before contacting any agent."""
        result = self._run("--improve", str(tmp_path / "missing.py"))
        assert result.returncode == 1

    def test_improve_nonexistent_file_prints_error(self, tmp_path):
        """--improve with a missing file must print an error message to stderr."""
        result = self._run("--improve", str(tmp_path / "missing.py"))
        assert (
            "file not found" in result.stderr.lower()
            or "error" in result.stderr.lower()
        )


# ---------------------------------------------------------------------------
# Antigravity agent wiring
# ---------------------------------------------------------------------------


class TestAntigravityAgent:
    def test_antigravity_tier_resolution(self, tmp_path):
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        limiter = RateLimiter()
        agent = CLIAgent("antigravity", "advanced", 60, limiter, config=config)
        assert agent.name == "antigravity"
        assert agent.model_name == "Claude Opus 4.6 (Thinking)"
        assert agent.binary == "agy"

    @pytest.mark.asyncio
    async def test_antigravity_missing_binary(self, tmp_path, monkeypatch):
        monkeypatch.setattr("agents.runners.shutil.which", lambda cmd: None)
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        agent = CLIAgent("antigravity", "flash", 60, RateLimiter(), config=config)
        result = await agent._execute_impl("test", "prompt")
        assert result["status"] == "missing"

    def test_services_default_includes_antigravity(self, tmp_path):
        sc = ServiceConfig(config_path=str(tmp_path / "nonexistent.yml"))
        assert sc.is_enabled("antigravity") is True

    @pytest.mark.asyncio
    async def test_check_credits_antigravity_available(self, tmp_path, monkeypatch):
        """check_credits probes agy (codex-style) and marks it available on rc=0."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setattr(
            "agents.orchestrator.shutil.which",
            lambda cmd: "/usr/local/bin/agy" if cmd == "agy" else None,
        )

        class FakeProc:
            returncode = 0

            async def communicate(self):
                return (b"OK", b"")

        async def fake_exec(*args, **kwargs):
            return FakeProc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        results = await check_credits(config)
        assert results["antigravity"] == {"status": "available"}

    @pytest.mark.asyncio
    async def test_check_credits_antigravity_not_installed(self, tmp_path, monkeypatch):
        """check_credits marks antigravity not_installed when agy is absent."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setattr("agents.orchestrator.shutil.which", lambda cmd: None)
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        results = await check_credits(config)
        assert results["antigravity"] == {"status": "not_installed"}

    @pytest.mark.asyncio
    async def test_check_credits_antigravity_quota_exceeded(
        self, tmp_path, monkeypatch
    ):
        """check_credits classifies agy stderr mentioning quota/unauthorized as
        quota_exceeded, mirroring the codex probe's classification."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setattr(
            "agents.orchestrator.shutil.which",
            lambda cmd: "/usr/local/bin/agy" if cmd == "agy" else None,
        )

        class FakeProc:
            returncode = 1

            async def communicate(self):
                return (b"", b"Error: unauthorized, please run agy login")

        async def fake_exec(*args, **kwargs):
            return FakeProc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        results = await check_credits(config)
        assert results["antigravity"]["status"] == "quota_exceeded"

    @pytest.mark.asyncio
    async def test_check_credits_antigravity_hang_times_out(
        self, tmp_path, monkeypatch
    ):
        """Mirrors test_check_credits_codex_hang_times_out: the timeout must
        cover communicate(), not just the spawn, for the agy probe too."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setattr(
            "agents.orchestrator.shutil.which",
            lambda cmd: "/usr/local/bin/agy" if cmd == "agy" else None,
        )

        class HangingProc:
            def __init__(self):
                self.killed = False
                self.returncode = None

            async def communicate(self):
                await asyncio.sleep(3600)

            def kill(self):
                self.killed = True

            async def wait(self):
                return 0

        proc = HangingProc()

        async def fake_exec(*args, **kwargs):
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        results = await check_credits(config, probe_timeout=0.1)
        assert results["antigravity"]["status"] == "error"
        assert "timed out" in results["antigravity"]["error"]
        assert proc.killed is True

    @pytest.mark.asyncio
    async def test_check_credits_codex_hang_times_out(self, tmp_path, monkeypatch):
        """Issue #307: the timeout must cover communicate(), not just the spawn —
        a codex blocked on auth/TTY hung --check-credits forever."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setattr(
            "agents.orchestrator.shutil.which",
            lambda cmd: "/usr/local/bin/codex" if cmd == "codex" else None,
        )

        class HangingProc:
            def __init__(self):
                self.killed = False
                self.returncode = None

            async def communicate(self):
                await asyncio.sleep(3600)

            def kill(self):
                self.killed = True

            async def wait(self):
                return 0

        proc = HangingProc()

        async def fake_exec(*args, **kwargs):
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        config = Config(config_path=str(tmp_path / "nonexistent.yml"))
        results = await check_credits(config, probe_timeout=0.1)
        assert results["codex"]["status"] == "error"
        assert "timed out" in results["codex"]["error"]
        assert proc.killed is True


class TestCLIFlagsAntigravity:
    """The CLI surface advertises antigravity flags."""

    SCRIPT = str(REPO_ROOT / "configs" / "claude" / "scripts" / "parallel_agent.py")

    def test_help_lists_antigravity_flags(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, self.SCRIPT, "--help"],
            capture_output=True,
            text=True,
        )
        assert "--antigravity-model" in result.stdout
        assert "--antigravity-only" in result.stdout
        assert "--no-antigravity" in result.stdout
