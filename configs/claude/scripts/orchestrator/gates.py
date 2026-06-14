"""Gate evaluation: the two gates that bracket code generation.

- Pre-implementation analysis gate (FR-017/018/019): fail-closed — ANY finding
  blocks implementation.
- Post-implementation verification gate (FR-030/031/032/033): Tier 1 findings
  block PR-open; Tier 2 findings are advisory. Verdict labels (APPROVED /
  NEEDS_REVIEW / BLOCKED) follow validation_criteria.yml — referenced, not
  redefined (Constitution III).

These are deterministic functions over already-classified findings (the engine /
consensus layer assigns severity and tier); they are the testable core the gate
skill prompts mirror.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
VERIFY_DIMENSIONS = ("design_intent", "functionality", "standards")
_DEFAULT_TIER2_THRESHOLD = 0.60


def load_tier2_threshold() -> float:
    """Read tier2_acceptable_threshold from validation_criteria.yml (fail-safe)."""
    try:
        import yaml
        data = yaml.safe_load((CONFIG_DIR / "validation_criteria.yml").read_text(encoding="utf-8")) or {}
        # threshold may live under a scoring/verdict block; probe common locations
        for key in ("tier2_acceptable_threshold",):
            if key in data:
                return float(data[key])
        scoring = data.get("scoring", data)
        return float(scoring.get("tier2_acceptable_threshold", _DEFAULT_TIER2_THRESHOLD))
    except Exception:
        return _DEFAULT_TIER2_THRESHOLD


# --------------------------------------------------------------------------- #
# Phase 4 — pre-implementation analysis gate (fail-closed)
# --------------------------------------------------------------------------- #
def evaluate_analysis_gate(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Any finding (error/warning/regression) blocks implementation (FR-017/019)."""
    fixes = [
        {
            "finding": f["finding"],
            "severity": f.get("severity", "warning"),
            "file": f.get("file"),
            "fix_directive": f.get("fix_directive", "address the finding"),
        }
        for f in findings
    ]
    clean = not fixes
    return {
        "gate": "clean" if clean else "blocked",
        "required_fixes": fixes,
        "implement_approved": clean,
    }


# --------------------------------------------------------------------------- #
# Phase 5 — post-implementation verification gate (Tier 1 blocks, Tier 2 advisory)
# --------------------------------------------------------------------------- #
def tier2_score(findings: list[dict[str, Any]]) -> float:
    """Deterministic Tier 2 quality proxy in [0,1]: 1.0 with no Tier 2 findings,
    decaying 0.2 each. Only affects APPROVED vs NEEDS_REVIEW labeling, never the
    block decision (which is Tier-1-only)."""
    n = sum(1 for f in findings if f.get("tier") == 2)
    return max(0.0, 1.0 - 0.2 * n)


def verdict_label(tier1_count: int, t2_score: float, threshold: float | None = None) -> str:
    """Map to APPROVED / NEEDS_REVIEW / BLOCKED per validation_criteria.yml."""
    thr = load_tier2_threshold() if threshold is None else threshold
    if tier1_count > 0:
        return "BLOCKED"
    return "APPROVED" if t2_score >= thr else "NEEDS_REVIEW"


def evaluate_verification_gate(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Tier 1 blocks PR-open; Tier 2 is advisory (FR-031). A dimension fails if it
    carries any Tier 1 finding. Fail-closed at Tier 1 (FR-033)."""
    tier1 = [f for f in findings if f.get("tier") == 1]
    dims = {
        d: ("fail" if any(f.get("dimension") == d and f.get("tier") == 1 for f in findings) else "pass")
        for d in VERIFY_DIMENSIONS
    }
    pr_open = not tier1
    return {
        "verdict": "verified" if pr_open else "blocked",
        "dimensions": dims,
        "findings": [
            {
                "dimension": f.get("dimension", "standards"),
                "tier": f.get("tier", 2),
                "detail": f.get("detail", ""),
                "remediation": f.get("remediation"),
            }
            for f in findings
        ],
        "pr_open_approved": pr_open,
    }


def advisory_verdict_label(findings: list[dict[str, Any]]) -> str:
    """APPROVED / NEEDS_REVIEW / BLOCKED label for the PR annotation / audit
    (advisory — NOT part of the schema-bound gate payload)."""
    tier1 = sum(1 for f in findings if f.get("tier") == 1)
    return verdict_label(tier1, tier2_score(findings))
