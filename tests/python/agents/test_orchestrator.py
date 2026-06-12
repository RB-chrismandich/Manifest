#!/usr/bin/env python3
"""Per-module unit tests for agents.orchestrator.

Tests Orchestrator consensus calculation in isolation — no live agents required.
"""

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = str(REPO_ROOT / "configs" / "claude" / "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from agents.config import Config, RateLimiter
from agents.orchestrator import Orchestrator
from agents.runners import BaseAgent


def _make_config(tmp_path):
    return Config(config_path=str(tmp_path / "none.yml"))


def _make_orchestrator(tmp_path, agents=None):
    config = _make_config(tmp_path)
    return Orchestrator(agents or [], config)


class TestOrchestratorConsensus:
    def test_consensus_with_similar_outputs(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        results = {
            "agent1": {
                "status": "complete",
                "output": "the quick brown fox jumps over the lazy dog",
            },
            "agent2": {
                "status": "complete",
                "output": "the quick brown fox jumps over the lazy cat",
            },
        }
        consensus = orch._calculate_consensus(results)
        assert consensus["consensus_score"] > 0
        assert consensus["agent_count"] == 2

    def test_consensus_with_single_agent(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        results = {
            "agent1": {"status": "complete", "output": "some output here"},
        }
        consensus = orch._calculate_consensus(results)
        assert consensus["consensus_score"] == 0
        assert consensus["confidence"] == "low"

    def test_consensus_with_no_complete_agents(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        results = {
            "agent1": {"status": "failed", "output": ""},
        }
        consensus = orch._calculate_consensus(results)
        assert consensus["consensus_score"] == 0

    def test_confidence_levels_at_boundaries(self, tmp_path):
        """Issue #305: 0-100 score must be normalized against fractional
        thresholds (0.80/0.50) — previously every score >= 1 rated 'high'."""
        orch = _make_orchestrator(tmp_path)

        def confidence_for(score):
            common = ["word%05d" % i for i in range(score)]
            unique = ["only%05d" % i for i in range(100 - score)]
            results = {
                "a": {"status": "complete", "output": " ".join(common + unique)},
                "b": {"status": "complete", "output": " ".join(common)},
            }
            consensus = orch._calculate_consensus(results)
            assert consensus["consensus_score"] == score
            return consensus["confidence"]

        assert confidence_for(80) == "high"
        assert confidence_for(79) == "medium"
        assert confidence_for(50) == "medium"
        assert confidence_for(49) == "low"
        assert confidence_for(1) == "low"  # the old bug rated this 'high'

    def test_print_results_json(self, tmp_path, capsys):
        orch = _make_orchestrator(tmp_path)
        result = {
            "timestamp": "20260531_120000",
            "mode": "prompt",
            "prompt": "test",
            "duration_seconds": 1.0,
            "duration_formatted": "1s",
            "agents": {},
            "cross_verification": {
                "consensus_score": 75,
                "confidence": "medium",
                "agent_count": 2,
            },
            "validation": None,
            "output_files": {},
        }
        orch.print_results(result, json_output=True)
        captured = capsys.readouterr()
        import json
        parsed = json.loads(captured.out)
        assert parsed["mode"] == "prompt"
        assert "cross_verification" in parsed
