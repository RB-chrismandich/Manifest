"""T024 — US2: consensus threshold mapping (FR-034, SC-013)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from orchestrator import consensus  # noqa: E402

T = {"high": 0.80, "medium": 0.50, "low": 0.0}


def test_bands_map_to_thresholds():
    assert consensus.map_consensus(1.0, T) == "high"
    assert consensus.map_consensus(0.80, T) == "high"
    assert consensus.map_consensus(0.79, T) == "medium"
    assert consensus.map_consensus(0.50, T) == "medium"
    assert consensus.map_consensus(0.49, T) == "low"
    assert consensus.map_consensus(0.0, T) == "low"


def test_gate_outcomes():
    assert consensus.gate_outcome("high") == "proceed"
    assert consensus.gate_outcome("medium") == "proceed_flagged"
    assert consensus.gate_outcome("low") == "escalate"


def test_tally_fraction():
    assert consensus.tally([True, True, True, True]) == 1.0
    assert consensus.tally([True, False]) == 0.5
    assert consensus.tally([]) == 0.0


def test_low_consensus_always_escalates():  # SC-013
    res = consensus.evaluate([True, False, False], thresholds=T)  # 0.33
    assert res.band == "low"
    assert res.escalate is True
    assert res.proceed is False


def test_thresholds_load_from_command_config():
    loaded = consensus.load_thresholds()
    assert loaded["high"] == 0.80 and loaded["medium"] == 0.50


def test_summary_shape():
    res = consensus.evaluate([True, True, False], thresholds=T)  # 0.66 → medium
    s = res.to_summary()
    assert s["band"] == "medium" and s["outcome"] == "proceed_flagged"
