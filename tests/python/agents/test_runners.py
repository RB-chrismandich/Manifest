#!/usr/bin/env python3
"""Per-module unit tests for agents.runners.

Tests BaseAgent and CodexAgent in isolation — no external agent connections required.
"""

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = str(REPO_ROOT / "configs" / "claude" / "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from agents.config import Config, RateLimiter
from agents.runners import BaseAgent, CodexAgent


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
# CodexAgent
# ---------------------------------------------------------------------------


class TestCodexAgent:
    def test_resolve_model_auto(self, tmp_path):
        agent = CodexAgent(model="auto", rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        assert agent.model_name is None

    def test_resolve_model_named_tier(self, tmp_path):
        agent = CodexAgent(model="mini", rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        assert agent.model_name == "o4-mini"

    def test_resolve_model_custom(self, tmp_path):
        agent = CodexAgent(model="o3", rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        assert agent.model_name == "o3"

    def test_execute_missing_codex(self, tmp_path, monkeypatch):
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: None)
        agent = CodexAgent(model="auto", rate_limiter=_make_limiter(), config=_make_config(tmp_path))
        result = asyncio.run(agent.execute("test"))
        assert result["status"] == "missing"
