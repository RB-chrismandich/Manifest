#!/usr/bin/env python3
"""Per-module unit tests for agents.synthesis.

Tests SynthesisEngine in isolation — no external agent connections required.
"""

import asyncio
import sys
from pathlib import Path

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

    def test_triggers_synthesis_below_threshold_without_sdk(self, tmp_path):
        """Synthesis returns None gracefully when Anthropic SDK is unavailable."""
        from agents import synthesis as synth_module

        original = synth_module.HAS_ANTHROPIC
        synth_module.HAS_ANTHROPIC = False
        try:
            engine = _make_engine(tmp_path)
            engine.synthesis_template = "Template: {ORIGINAL_TASK}"
            consensus = {"consensus_score": 10}
            result = asyncio.run(engine.synthesize("test", {}, consensus))
            assert result is None
        finally:
            synth_module.HAS_ANTHROPIC = original


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
