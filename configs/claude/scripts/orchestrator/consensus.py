"""Gate cross-verification over parallel_agent.py (FR-034).

Consumes the canonical `parallel_agent.py` (Constitution II/IV — never modified)
to obtain N independent verdicts at the two gates, and maps the agreement ratio
to the bands OWNED by command_config.yml (Constitution III — referenced, not
redefined here):

    >=high   -> auto-proceed
    >=medium -> proceed with disagreements highlighted (advisory)
    <medium  -> escalate to human (needs_escalation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# config dir resolves the same in-repo (configs/claude/config) and deployed
# (~/.claude/config): both sit two parents above this package's parent.
CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

_DEFAULT_THRESHOLDS = {"high": 0.80, "medium": 0.50, "low": 0.0}


def load_thresholds() -> dict[str, float]:
    """Read consensus thresholds from command_config.yml (FR-034). Falls back to
    the documented defaults if the file/keys are unavailable (fail-safe)."""
    path = CONFIG_DIR / "command_config.yml"
    try:
        import yaml  # lazy: only needed when running live
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        c = data.get("consensus", {})
        return {
            "high": float(c.get("high", _DEFAULT_THRESHOLDS["high"])),
            "medium": float(c.get("medium", _DEFAULT_THRESHOLDS["medium"])),
            "low": float(c.get("low", _DEFAULT_THRESHOLDS["low"])),
        }
    except Exception:
        return dict(_DEFAULT_THRESHOLDS)


def tally(votes: list[bool]) -> float:
    """Fraction of agents that agree with the proposed gate decision (0.0–1.0)."""
    if not votes:
        return 0.0
    return sum(1 for v in votes if v) / len(votes)


def map_consensus(agreement_ratio: float, thresholds: dict[str, float] | None = None) -> str:
    """Map an agreement ratio to a band: high | medium | low (FR-034)."""
    t = thresholds or load_thresholds()
    if agreement_ratio >= t["high"]:
        return "high"
    if agreement_ratio >= t["medium"]:
        return "medium"
    return "low"


def gate_outcome(band: str) -> str:
    """Translate a consensus band into a gate action."""
    return {"high": "proceed", "medium": "proceed_flagged", "low": "escalate"}[band]


@dataclass
class ConsensusResult:
    agreement_ratio: float
    band: str
    votes: list[bool] = field(default_factory=list)
    disagreements: list[str] = field(default_factory=list)

    @property
    def escalate(self) -> bool:
        return self.band == "low"

    @property
    def proceed(self) -> bool:
        return self.band in ("high", "medium")

    def to_summary(self) -> dict[str, Any]:
        return {
            "agreement_ratio": round(self.agreement_ratio, 4),
            "band": self.band,
            "outcome": gate_outcome(self.band),
            "disagreements": self.disagreements,
        }


def evaluate(votes: list[bool], disagreements: list[str] | None = None,
             thresholds: dict[str, float] | None = None) -> ConsensusResult:
    """Aggregate agent votes into a ConsensusResult (FR-034)."""
    ratio = tally(votes)
    band = map_consensus(ratio, thresholds)
    return ConsensusResult(ratio, band, list(votes), list(disagreements or []))


def cross_verify(decision: dict[str, Any], *, agents: int = 3) -> ConsensusResult:  # pragma: no cover
    """Live cross-verification: ask `parallel_agent.py` for N independent verdicts
    on `decision` and aggregate. Network/LLM path — exercised in integration, not
    unit tests (which call `evaluate` with deterministic votes)."""
    raise NotImplementedError(
        "Live cross_verify wires parallel_agent.py at integration time; "
        "unit logic is covered by consensus.evaluate()."
    )
