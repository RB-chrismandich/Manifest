#!/usr/bin/env python3
"""Per-module unit tests for agents.synthesis.

Tests SynthesisEngine in isolation — no external agent connections required.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = str(REPO_ROOT / "configs" / "claude" / "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from agents.config import Config
from agents.synthesis import SynthesisEngine


def _make_engine(tmp_path):
    config = Config(config_path=str(tmp_path / "none.yml"))
    return SynthesisEngine(config)


class TestSynthesisEngine:
    def test_creation(self, tmp_path):
        engine = _make_engine(tmp_path)
        assert engine is not None
        assert isinstance(engine.synthesis_template, str)

    def test_skips_synthesis_when_consensus_high(self, tmp_path):
        engine = _make_engine(tmp_path)
        consensus = {"consensus_score": 90}
        result = asyncio.run(engine.synthesize("test task", {}, consensus))
        assert result is None

    def test_template_is_string(self, tmp_path):
        engine = _make_engine(tmp_path)
        assert isinstance(engine.synthesis_template, str)

    def test_build_synthesis_prompt_empty_without_template(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.synthesis_template = ""
        prompt = engine._build_synthesis_prompt("task", {})
        assert prompt == ""

    def test_build_synthesis_prompt_replaces_task(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.synthesis_template = "Task: {ORIGINAL_TASK}"
        prompt = engine._build_synthesis_prompt("my task", {})
        assert "my task" in prompt

    def test_build_synthesis_prompt_replaces_agent_outputs(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.synthesis_template = "Gemini: {GEMINI_OUTPUT}"
        agent_results = {"gemini": {"output": "gemini says hello"}}
        prompt = engine._build_synthesis_prompt("task", agent_results)
        assert "gemini says hello" in prompt

    def test_build_synthesis_prompt_includes_all_agents(self, tmp_path):
        """Issue #309: codex/antigravity outputs must reach the synthesis prompt."""
        engine = _make_engine(tmp_path)
        engine.synthesis_template = "Outputs:\n{AGENT_OUTPUTS}"
        agent_results = {
            "gemini": {"output": "gemini view"},
            "claude": {"output": "claude view"},
            "cursor": {"output": "cursor view"},
            "codex": {"output": "codex view"},
            "antigravity": {"output": "antigravity view"},
        }
        prompt = engine._build_synthesis_prompt("task", agent_results)
        for view in agent_results.values():
            assert view["output"] in prompt
        assert "### Antigravity Output" in prompt
        assert "### Codex Output" in prompt

    def test_skips_synthesis_at_threshold_boundary(self, tmp_path):
        engine = _make_engine(tmp_path)
        # Default threshold is 0.50; score of 50 → 50/100 = 0.50 >= threshold → skip
        consensus = {"consensus_score": 50}
        result = asyncio.run(engine.synthesize("test", {}, consensus))
        assert result is None

    def test_triggers_synthesis_below_threshold_without_auth(self, tmp_path, monkeypatch):
        """No SDK, no CLI, no API key → auth error envelope (not a crash)."""
        from agents import synthesis as synth_module

        original = synth_module.HAS_ANTHROPIC
        synth_module.HAS_ANTHROPIC = False
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(synth_module.shutil, "which", lambda _: None)
        try:
            engine = _make_engine(tmp_path)
            engine.synthesis_template = "Template: {ORIGINAL_TASK}"
            consensus = {"consensus_score": 10}
            result = asyncio.run(engine.synthesize("test", {}, consensus))
            assert result is not None
            assert result["triggered"] is True
            assert "ANTHROPIC_API_KEY" in result["error"]
        finally:
            synth_module.HAS_ANTHROPIC = original


def _mock_anthropic_response(text: str):
    """Build a fake AsyncAnthropic client/response chain for synth_module."""
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


class TestSynthesizeWithSdk:
    """Exercise the HAS_ANTHROPIC=True branch with a stubbed client — no
    live network/CLI calls. anthropic may not be installed in this env, so
    both HAS_ANTHROPIC and AsyncAnthropic are patched onto the module."""

    def _engine_below_threshold(self, tmp_path, monkeypatch, client):
        from agents import synthesis as synth_module

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", True)
        monkeypatch.setattr(
            synth_module,
            "AsyncAnthropic",
            MagicMock(return_value=client),
            raising=False,
        )
        engine = _make_engine(tmp_path)
        engine.config.config.setdefault("synthesis", {})["backend"] = "sdk"
        engine.synthesis_template = "Task: {ORIGINAL_TASK}\n{AGENT_OUTPUTS}"
        return engine

    def test_successful_synthesis_returns_parsed_json(self, tmp_path, monkeypatch):
        client = _mock_anthropic_response('{"unified_recommendation": "do X"}')
        engine = self._engine_below_threshold(tmp_path, monkeypatch, client)
        agent_results = {"claude": {"output": "claude says X"}}
        result = asyncio.run(
            engine.synthesize("task", agent_results, {"consensus_score": 10})
        )
        assert result["triggered"] is True
        assert result["unified_recommendation"] == "do X"

    def test_synthesis_strips_markdown_json_fence(self, tmp_path, monkeypatch):
        text = '```json\n{"unified_recommendation": "fenced"}\n```'
        client = _mock_anthropic_response(text)
        engine = self._engine_below_threshold(tmp_path, monkeypatch, client)
        result = asyncio.run(
            engine.synthesize(
                "task", {"claude": {"output": "x"}}, {"consensus_score": 0}
            )
        )
        assert result["unified_recommendation"] == "fenced"

    def test_json_decode_error_falls_back_to_raw_text(self, tmp_path, monkeypatch):
        client = _mock_anthropic_response("not valid json at all")
        engine = self._engine_below_threshold(tmp_path, monkeypatch, client)
        result = asyncio.run(
            engine.synthesize(
                "task", {"claude": {"output": "x"}}, {"consensus_score": 0}
            )
        )
        assert result["triggered"] is True
        assert result["error"] == "json_parse_failed"
        assert result["unified_recommendation"] == "not valid json at all"

    def test_timeout_error_returns_timeout_result(self, tmp_path, monkeypatch):
        from agents import synthesis as synth_module

        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=TimeoutError())
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", True)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(
            synth_module,
            "AsyncAnthropic",
            MagicMock(return_value=client),
            raising=False,
        )
        engine = _make_engine(tmp_path)
        engine.config.config.setdefault("synthesis", {})["backend"] = "sdk"
        engine.synthesis_template = "Task: {ORIGINAL_TASK}"
        result = asyncio.run(
            engine.synthesize(
                "task", {"claude": {"output": "x"}}, {"consensus_score": 0}
            )
        )
        assert result["triggered"] is True
        assert result["error"] == "timeout"

    def test_generic_exception_is_captured(self, tmp_path, monkeypatch):
        from agents import synthesis as synth_module

        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", True)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(
            synth_module,
            "AsyncAnthropic",
            MagicMock(return_value=client),
            raising=False,
        )
        engine = _make_engine(tmp_path)
        engine.config.config.setdefault("synthesis", {})["backend"] = "sdk"
        engine.synthesis_template = "Task: {ORIGINAL_TASK}"
        result = asyncio.run(
            engine.synthesize(
                "task", {"claude": {"output": "x"}}, {"consensus_score": 0}
            )
        )
        assert result["triggered"] is True
        assert result["error"] == "boom"
        assert result["unified_recommendation"] == "Synthesis failed"

    def test_missing_prompt_short_circuits_before_sdk_call(self, tmp_path, monkeypatch):
        """Empty template -> empty prompt -> returns None without ever
        constructing the Anthropic client."""
        from agents import synthesis as synth_module

        client_factory = MagicMock()
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", True)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(
            synth_module, "AsyncAnthropic", client_factory, raising=False
        )
        engine = _make_engine(tmp_path)
        engine.config.config.setdefault("synthesis", {})["backend"] = "sdk"
        engine.synthesis_template = ""
        result = asyncio.run(engine.synthesize("task", {}, {"consensus_score": 0}))
        assert result is None
        client_factory.assert_not_called()


class TestBuildPromptEdgeCases:
    def test_single_agent_output(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.synthesis_template = "{AGENT_OUTPUTS}"
        prompt = engine._build_synthesis_prompt(
            "task", {"claude": {"output": "solo view"}}
        )
        assert prompt == "### Claude Output\n\nsolo view"

    def test_empty_agent_results_leaves_placeholder_section_empty(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.synthesis_template = "Before\n{AGENT_OUTPUTS}\nAfter"
        prompt = engine._build_synthesis_prompt("task", {})
        assert prompt == "Before\n\nAfter"

    def test_agent_with_missing_output_key_renders_na(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.synthesis_template = "{AGENT_OUTPUTS}"
        prompt = engine._build_synthesis_prompt("task", {"gemini": {}})
        assert "N/A" in prompt
        assert "### Gemini Output" in prompt

    def test_agent_with_empty_string_output_renders_na(self, tmp_path):
        """output='' is falsy, so the {AGENT_OUTPUTS} section falls back to N/A."""
        engine = _make_engine(tmp_path)
        engine.synthesis_template = "{AGENT_OUTPUTS}"
        prompt = engine._build_synthesis_prompt("task", {"gemini": {"output": ""}})
        assert "N/A" in prompt

    def test_no_placeholders_returns_template_unchanged(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.synthesis_template = "static content, no placeholders"
        prompt = engine._build_synthesis_prompt(
            "task", {"claude": {"output": "ignored"}}
        )
        assert prompt == "static content, no placeholders"


class TestSynthesisBackendResolution:
    def test_auto_prefers_cli_without_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr("agents.synthesis.shutil.which", lambda _: "/usr/bin/claude")
        engine = _make_engine(tmp_path)
        assert engine._resolve_synthesis_backend() == "cli"

    def test_auto_prefers_sdk_with_api_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr("agents.synthesis.shutil.which", lambda _: "/usr/bin/claude")
        from agents import synthesis as synth_module

        original = synth_module.HAS_ANTHROPIC
        synth_module.HAS_ANTHROPIC = True
        try:
            engine = _make_engine(tmp_path)
            assert engine._resolve_synthesis_backend() == "sdk"
        finally:
            synth_module.HAS_ANTHROPIC = original

    def test_auto_neither_cli_nor_key_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr("agents.synthesis.shutil.which", lambda _: None)
        from agents import synthesis as synth_module

        original = synth_module.HAS_ANTHROPIC
        synth_module.HAS_ANTHROPIC = True
        try:
            engine = _make_engine(tmp_path)
            assert engine._resolve_synthesis_backend() is None
        finally:
            synth_module.HAS_ANTHROPIC = original

    def test_backend_cli_forces_cli_even_with_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr("agents.synthesis.shutil.which", lambda _: "/usr/bin/claude")
        engine = _make_engine(tmp_path)
        engine.config.config.setdefault("synthesis", {})["backend"] = "cli"
        assert engine._resolve_synthesis_backend() == "cli"

    def test_backend_sdk_forces_sdk(self, tmp_path, monkeypatch):
        monkeypatch.setattr("agents.synthesis.shutil.which", lambda _: "/usr/bin/claude")
        from agents import synthesis as synth_module

        original = synth_module.HAS_ANTHROPIC
        synth_module.HAS_ANTHROPIC = True
        try:
            engine = _make_engine(tmp_path)
            engine.config.config.setdefault("synthesis", {})["backend"] = "sdk"
            assert engine._resolve_synthesis_backend() == "sdk"
        finally:
            synth_module.HAS_ANTHROPIC = original

    def test_invalid_backend_falls_back_to_auto(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr("agents.synthesis.shutil.which", lambda _: "/usr/bin/claude")
        engine = _make_engine(tmp_path)
        engine.config.config.setdefault("synthesis", {})["backend"] = "bogus"
        assert engine._resolve_synthesis_backend() == "cli"


class TestSynthesisCliInvoke:
    def _engine_with_template(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.synthesis_template = "Task: {ORIGINAL_TASK}"
        return engine

    def test_cli_success_parses_json(self, tmp_path, monkeypatch):
        from agents import synthesis as synth_module

        async def fake_exec(*cmd, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(
                return_value=(b'{"unified_recommendation": "merged"}', b"")
            )
            proc.returncode = 0
            proc.kill = MagicMock()
            proc.wait = AsyncMock()
            return proc

        monkeypatch.setattr(synth_module.asyncio, "create_subprocess_exec", fake_exec)
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(synth_module.shutil, "which", lambda _: "/usr/bin/claude")

        engine = self._engine_with_template(tmp_path)
        result = asyncio.run(
            engine.synthesize("task", {"claude": {"output": "x"}}, {"consensus_score": 0})
        )
        assert result["unified_recommendation"] == "merged"
        assert result["triggered"] is True

    def test_cli_nonzero_exit_returns_error(self, tmp_path, monkeypatch):
        from agents import synthesis as synth_module

        async def fake_exec(*cmd, **kwargs):
            proc = MagicMock()
            proc.communicate = AsyncMock(return_value=(b"", b"not logged in"))
            proc.returncode = 1
            proc.kill = MagicMock()
            proc.wait = AsyncMock()
            return proc

        monkeypatch.setattr(synth_module.asyncio, "create_subprocess_exec", fake_exec)
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(synth_module.shutil, "which", lambda _: "/usr/bin/claude")

        engine = self._engine_with_template(tmp_path)
        result = asyncio.run(
            engine.synthesize("task", {"claude": {"output": "x"}}, {"consensus_score": 0})
        )
        assert result["triggered"] is True
        assert "not logged in" in result["error"]

    def test_auto_neither_auth_returns_combined_error(self, tmp_path, monkeypatch):
        from agents import synthesis as synth_module

        client_factory = MagicMock()
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", True)
        monkeypatch.setattr(synth_module, "AsyncAnthropic", client_factory, raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(synth_module.shutil, "which", lambda _: None)

        engine = self._engine_with_template(tmp_path)
        result = asyncio.run(
            engine.synthesize("task", {"claude": {"output": "x"}}, {"consensus_score": 0})
        )
        assert result["triggered"] is True
        assert "ANTHROPIC_API_KEY" in result["error"]
        assert "claude" in result["error"].lower()
        client_factory.assert_not_called()

    def test_cli_cancelled_kills_child(self, tmp_path, monkeypatch):
        from agents import synthesis as synth_module

        proc = MagicMock()
        proc.communicate = AsyncMock(side_effect=asyncio.CancelledError())
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        async def fake_exec(*cmd, **kwargs):
            return proc

        monkeypatch.setattr(synth_module.asyncio, "create_subprocess_exec", fake_exec)
        engine = self._engine_with_template(tmp_path)

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(engine._invoke_claude_cli("prompt"))
        proc.kill.assert_called_once()
        proc.wait.assert_called_once()

    def test_cli_timeout_returns_timeout_error(self, tmp_path, monkeypatch):
        from agents import synthesis as synth_module

        async def fake_wait_for(coro, timeout):
            if hasattr(coro, "close"):
                coro.close()
            raise TimeoutError()

        monkeypatch.setattr(synth_module.asyncio, "wait_for", fake_wait_for)
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(synth_module.shutil, "which", lambda _: "/usr/bin/claude")

        engine = self._engine_with_template(tmp_path)
        result = asyncio.run(
            engine.synthesize("task", {"claude": {"output": "x"}}, {"consensus_score": 0})
        )
        assert result["error"] == "timeout"


class TestConsensusThreshold:
    def test_custom_threshold_from_config(self, tmp_path, monkeypatch):
        """A stricter configured threshold triggers synthesis at a score
        (0.70) that would be skipped under the 0.50 default — proven by
        actually driving the mocked SDK call, not just checking None."""
        from agents import synthesis as synth_module

        client = _mock_anthropic_response('{"unified_recommendation": "ran"}')
        monkeypatch.setattr(synth_module, "HAS_ANTHROPIC", True)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(
            synth_module,
            "AsyncAnthropic",
            MagicMock(return_value=client),
            raising=False,
        )

        engine = _make_engine(tmp_path)
        engine.config.config.setdefault("synthesis", {})["threshold"] = 0.90
        engine.config.config.setdefault("synthesis", {})["backend"] = "sdk"
        engine.synthesis_template = "{ORIGINAL_TASK}"

        consensus = {"consensus_score": 70}  # 0.70 < 0.90 custom threshold

        # Sanity: default threshold (0.50) would have skipped this score.
        default_engine = _make_engine(tmp_path)
        default_engine.synthesis_template = "{ORIGINAL_TASK}"
        assert asyncio.run(default_engine.synthesize("task", {}, consensus)) is None

        result = asyncio.run(engine.synthesize("task", {}, consensus))
        assert result["unified_recommendation"] == "ran"
        client.messages.create.assert_called_once()

    def test_missing_consensus_score_defaults_to_full_consensus(self, tmp_path):
        """consensus dict without 'consensus_score' defaults to 100 -> skip."""
        engine = _make_engine(tmp_path)
        result = asyncio.run(engine.synthesize("task", {}, {}))
        assert result is None


class TestTemplateResolution:
    """Resolution order: explicit param > SYNTHESIS_TEMPLATE env > deployed
    home copy > repo-relative fallback (issue #465 — fresh clones/CI must not
    silently disable synthesis)."""

    def test_explicit_template_path_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))  # no deployed copy
        monkeypatch.delenv("SYNTHESIS_TEMPLATE", raising=False)
        custom = tmp_path / "custom.md"
        custom.write_text("CUSTOM TEMPLATE")
        config = Config(config_path=str(tmp_path / "none.yml"))
        engine = SynthesisEngine(config, template_path=str(custom))
        assert engine.synthesis_template == "CUSTOM TEMPLATE"

    def test_env_var_used_when_no_param(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        envt = tmp_path / "envt.md"
        envt.write_text("ENV TEMPLATE")
        monkeypatch.setenv("SYNTHESIS_TEMPLATE", str(envt))
        engine = _make_engine(tmp_path)
        assert engine.synthesis_template == "ENV TEMPLATE"

    def test_deployed_home_copy_preferred_over_repo(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SYNTHESIS_TEMPLATE", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        dep = tmp_path / ".claude" / "prompts"
        dep.mkdir(parents=True)
        (dep / "synthesis.md").write_text("DEPLOYED TEMPLATE")
        engine = _make_engine(tmp_path)
        assert engine.synthesis_template == "DEPLOYED TEMPLATE"

    def test_repo_fallback_on_fresh_clone(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SYNTHESIS_TEMPLATE", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))  # empty fake home
        engine = _make_engine(tmp_path)
        repo_template = (
            REPO_ROOT / "configs" / "claude" / "prompts" / "synthesis.md"
        ).read_text()
        assert engine.synthesis_template == repo_template
        assert engine.synthesis_template != ""
