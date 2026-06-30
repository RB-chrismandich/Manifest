#!/usr/bin/env python3
"""Per-module unit tests for agents.validation.

Tests ValidationEngine in isolation — no external connections required.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = str(REPO_ROOT / "configs" / "claude" / "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from agents.config import Config
from agents.validation import ValidationEngine


def _make_engine(tmp_path):
    config = Config(config_path=str(tmp_path / "none.yml"))
    return ValidationEngine(config)


def _complete(output: str) -> dict:
    return {"status": "complete", "output": output}


def _incomplete() -> dict:
    return {"status": "failed", "output": ""}


class TestValidationEngine:
    def test_security_check_detects_hardcoded_secret(self, tmp_path):
        engine = _make_engine(tmp_path)
        results = {"agent1": _complete("api_key = 'abc123'")}
        result = engine._check_security(results, {})
        assert result["passed"] is False
        assert len(result["issues"]) > 0

    def test_security_check_passes_clean_code(self, tmp_path):
        engine = _make_engine(tmp_path)
        results = {"agent1": _complete("def hello(): return 'world'")}
        result = engine._check_security(results, {})
        assert result["passed"] is True

    def test_error_handling_detects_bare_except(self, tmp_path):
        engine = _make_engine(tmp_path)
        results = {"agent1": _complete("try:\n  pass\nexcept:\n  pass")}
        result = engine._check_error_handling(results, {})
        assert result["passed"] is False

    def test_bug_detection_scores_null_references(self, tmp_path):
        engine = _make_engine(tmp_path)
        results = {"agent1": _complete("found null reference in the code")}
        result = engine._check_bugs(results, {})
        assert result["score"] < 1.0

    def test_performance_check_detects_quadratic(self, tmp_path):
        engine = _make_engine(tmp_path)
        results = {"agent1": _complete("this has O(n^2) complexity")}
        result = engine._check_performance(results, {})
        assert result["score"] < 1.0

    def test_verdict_approved(self, tmp_path):
        engine = _make_engine(tmp_path)
        tier1 = {"passed": True, "score": 1.0, "checks": {}, "failures": []}
        tier2 = {"score": 0.9, "checks": {}, "concerns": []}
        verdict = engine._compute_verdict(tier1, tier2, {})
        assert verdict == "APPROVED"

    def test_verdict_needs_review(self, tmp_path):
        engine = _make_engine(tmp_path)
        tier1 = {"passed": True, "score": 1.0, "checks": {}, "failures": []}
        tier2 = {"score": 0.3, "checks": {}, "concerns": []}
        verdict = engine._compute_verdict(tier1, tier2, {})
        assert verdict == "NEEDS_REVIEW"

    def test_verdict_blocked(self, tmp_path):
        engine = _make_engine(tmp_path)
        tier1 = {"passed": False, "score": 0.0, "checks": {}, "failures": ["fail"]}
        tier2 = {"score": 0.9, "checks": {}, "concerns": []}
        verdict = engine._compute_verdict(tier1, tier2, {})
        assert verdict == "BLOCKED"

    def test_verdict_with_custom_threshold_override(self, tmp_path):
        engine = _make_engine(tmp_path)
        tier1 = {"passed": True, "score": 1.0, "checks": {}, "failures": []}
        tier2 = {"score": 0.5, "checks": {}, "concerns": []}
        verdict = engine._compute_verdict(tier1, tier2, {"tier2_threshold": 0.4})
        assert verdict == "APPROVED"

    def test_skips_incomplete_agents(self, tmp_path):
        engine = _make_engine(tmp_path)
        results = {
            "agent1": _complete("api_key = 'abc'"),
            "agent2": _incomplete(),
        }
        result = engine._check_security(results, {})
        # Only agent1 is checked; agent2 is skipped
        assert any("agent1" in issue for issue in result["issues"])
        assert not any("agent2" in issue for issue in result["issues"])
