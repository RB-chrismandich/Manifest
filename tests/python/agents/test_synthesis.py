#!/usr/bin/env python3
"""Per-module unit tests for agents.synthesis.

Tests SynthesisEngine in isolation — no external agent connections required.
"""

import asyncio
import sys
from pathlib import Path

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
        result = asyncio.run(
            engine.synthesize("test task", {}, consensus)
        )
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

    def test_skips_synthesis_at_threshold_boundary(self, tmp_path):
        engine = _make_engine(tmp_path)
        # Default threshold is 0.50; score of 50 → 50/100 = 0.50 >= threshold → skip
        consensus = {"consensus_score": 50}
        result = asyncio.run(
            engine.synthesize("test", {}, consensus)
        )
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
            result = asyncio.run(
                engine.synthesize("test", {}, consensus)
            )
            assert result is None
        finally:
            synth_module.HAS_ANTHROPIC = original
