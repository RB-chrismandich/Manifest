#!/usr/bin/env python3
"""Per-module unit tests for agents.runners.

Tests BaseAgent and CLIAgent in isolation — no external agent connections required.
"""

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = str(REPO_ROOT / "configs" / "claude" / "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from agents.config import Config, RateLimiter
from agents.runners import BaseAgent, CLIAgent


def _make_config(tmp_path):
    return Config(config_path=str(tmp_path / "none.yml"))


def _make_limiter():
    return RateLimiter(requests_per_minute=1000, burst_size=100)


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------


class _ConcreteAgent(BaseAgent):
    """Minimal concrete implementation for testing BaseAgent."""

    async def _execute_impl(self, prompt: str, mode: str):
        return {"status": "complete", "output": "ok", "model": "test"}


class TestBaseAgent:
    def test_credit_exhaustion_detection_quota(self, tmp_path):
        agent = _ConcreteAgent(
            "test", "sonnet", 30, _make_limiter(), _make_config(tmp_path)
        )
        assert agent._is_credit_exhaustion_error("quota exceeded") is True

    def test_credit_exhaustion_detection_rate_limit(self, tmp_path):
        agent = _ConcreteAgent(
            "test", "sonnet", 30, _make_limiter(), _make_config(tmp_path)
        )
        assert agent._is_credit_exhaustion_error("rate limit reached") is True

    def test_credit_exhaustion_detection_429(self, tmp_path):
        agent = _ConcreteAgent(
            "test", "sonnet", 30, _make_limiter(), _make_config(tmp_path)
        )
        assert agent._is_credit_exhaustion_error("error 429 too many") is True

    def test_no_false_positive_on_normal_error(self, tmp_path):
        agent = _ConcreteAgent(
            "test", "sonnet", 30, _make_limiter(), _make_config(tmp_path)
        )
        assert agent._is_credit_exhaustion_error("connection refused") is False

    def test_execute_returns_result(self, tmp_path):
        agent = _ConcreteAgent(
            "test", "sonnet", 30, _make_limiter(), _make_config(tmp_path)
        )
        result = asyncio.run(agent.execute("hello"))
        assert result["status"] == "complete"
        assert "duration_seconds" in result

    def test_execute_timeout(self, tmp_path):
        class SlowAgent(BaseAgent):
            async def _execute_impl(self, prompt, mode):
                await asyncio.sleep(10)
                return {"status": "complete", "output": "late"}

        agent = SlowAgent(
            "slow", "sonnet", 1, _make_limiter(), _make_config(tmp_path)
        )
        result = asyncio.run(agent.execute("hello"))
        assert result["status"] == "failed"
        assert "timeout" in result["error"]


# ---------------------------------------------------------------------------
# CLIAgent
# ---------------------------------------------------------------------------


class TestCLIAgentCommandAssembly:
    def test_unknown_provider_raises(self, tmp_path):
        with pytest.raises(ValueError, match="no cli_agents config"):
            CLIAgent("nonexistent", model="flash",
                     rate_limiter=_make_limiter(), config=_make_config(tmp_path))

    def test_codex_auto_drops_model_args_atomically(self, tmp_path):
        agent = CLIAgent("codex", model="auto",
                         rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        cmd = agent._build_command("hello", output_file=str(tmp_path / "out.txt"))
        assert agent.model_name is None
        assert "--model" not in cmd          # no dangling flag
        assert cmd[0] == "codex"
        assert cmd[-1] == "hello"            # prompt is last
        assert str(tmp_path / "out.txt") in cmd  # {output_file} substituted

    def test_codex_tier_resolves_via_model_tiers(self, tmp_path):
        agent = CLIAgent("codex", model="mini",
                         rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        cmd = agent._build_command("hello", output_file=str(tmp_path / "out.txt"))
        i = cmd.index("--model")
        assert cmd[i + 1] == "o4-mini"

    def test_cursor_tier_resolves_via_model_tiers(self, tmp_path):
        # Deliberate behavior change: cursor now honors model_tiers.cursor
        # (the old CursorAgent passed the raw tier string through).
        agent = CLIAgent("cursor", model="flash",
                         rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        cmd = agent._build_command("hello")
        i = cmd.index("--model")
        assert cmd[i + 1] == "gpt-5.1-codex"

    def test_output_file_placeholder_dropped_when_no_file(self, tmp_path):
        # A stdout-strategy provider with a stray {output_file} placeholder
        # must not inject an empty argv element.
        config = _make_config(tmp_path)
        config.config["cli_agents"]["fake"] = {
            "binary": "fakecli",
            "base_args": ["--out", "{output_file}"],
            "model_args": ["--model", "{model}"],
            "output": "stdout",
        }
        agent = CLIAgent("fake", model="auto",
                         rate_limiter=_make_limiter(), config=config)
        cmd = agent._build_command("hello", output_file=None)
        assert "" not in cmd

    def test_missing_binary_field_raises_value_error(self, tmp_path):
        config = _make_config(tmp_path)
        config.config["cli_agents"]["broken"] = {
            "base_args": [],
            "model_args": ["--model", "{model}"],
            "output": "stdout",
        }
        with pytest.raises(ValueError, match="binary is required"):
            CLIAgent("broken", model="flash",
                     rate_limiter=_make_limiter(), config=config)

    def test_custom_model_passes_through(self, tmp_path):
        agent = CLIAgent("codex", model="custom-model-123",
                         rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        assert agent.model_name == "custom-model-123"

    def test_antigravity_command_shape(self, tmp_path):
        agent = CLIAgent("antigravity", model="flash",
                         rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        cmd = agent._build_command("hello")
        assert cmd[0] == "agy"
        assert cmd[1] == "--print"
        i = cmd.index("--model")
        assert cmd[i + 1] == "Gemini 3.5 Flash (High)"
        assert cmd[-1] == "hello"


class TestCLIAgentExecution:
    def test_missing_binary(self, tmp_path, monkeypatch):
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: None)
        agent = CLIAgent("codex", model="auto",
                         rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        result = asyncio.run(agent._execute_impl("test", "prompt"))
        assert result["status"] == "missing"
        assert "codex" in result["error"]

    def test_stdout_strategy_collects_stdout(self, tmp_path):
        agent = CLIAgent("cursor", model="flash",
                         rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        result = agent._collect_output(0, b"the answer\n", b"", None)
        assert result["status"] == "complete"
        assert result["output"] == "the answer"

    def test_file_strategy_prefers_file_over_stdout(self, tmp_path):
        agent = CLIAgent("codex", model="auto",
                         rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        out = tmp_path / "out.txt"
        out.write_text("from file\n")
        result = agent._collect_output(0, b"from stdout", b"", str(out))
        assert result["output"] == "from file"

    def test_file_strategy_falls_back_to_stdout(self, tmp_path):
        agent = CLIAgent("codex", model="auto",
                         rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        out = tmp_path / "empty.txt"
        out.write_text("")
        result = agent._collect_output(0, b"from stdout", b"", str(out))
        assert result["output"] == "from stdout"

    def test_no_output_nonzero_exit_is_failed(self, tmp_path):
        agent = CLIAgent("codex", model="auto",
                         rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        result = agent._collect_output(1, b"", b"boom", None)
        assert result["status"] == "failed"
        assert "boom" in result["error"]

    def test_real_subprocess_roundtrip(self, tmp_path):
        """End-to-end through create_subprocess_exec using /bin/echo as the binary."""
        config = _make_config(tmp_path)
        config.config["cli_agents"]["fake"] = {
            "binary": "echo",
            "base_args": ["prefix"],
            "model_args": ["--model", "{model}"],
            "output": "stdout",
        }
        config.config["model_tiers"]["fake"] = {"flash": "fake-model-1"}
        agent = CLIAgent("fake", model="flash",
                         rate_limiter=_make_limiter(), config=config)
        result = asyncio.run(agent._execute_impl("hello world", "prompt"))
        assert result["status"] == "complete"
        assert result["output"] == "prefix --model fake-model-1 hello world"
