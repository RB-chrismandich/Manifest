"""Core data model + tier semantics (T005, T010).

The catalog is manipulated as plain dicts (preserving unknown keys on round-trip),
while these dataclasses give the executor typed access. Tier selection is
*cumulative*: a test's tier is its minimum inclusion level, so a requested tier
runs that tier and all lower ones (FR-006).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Lite ⊆ Full ⊆ Full+Extra
TIER_RANK: dict[str, int] = {"Lite": 0, "Full": 1, "Full+Extra": 2}
TIERS: tuple[str, ...] = tuple(TIER_RANK)


def tier_rank(name: str) -> int:
    """Rank for a tier name; raises ValueError on an unknown tier."""
    try:
        return TIER_RANK[name]
    except KeyError:
        raise ValueError(
            f"unknown tier {name!r}; expected one of {', '.join(TIERS)}"
        ) from None


def select_by_tier(tests: list[dict], requested: str) -> list[dict]:
    """Cumulative selection: every test whose tier rank <= requested (FR-006)."""
    ceiling = tier_rank(requested)
    return [t for t in tests if tier_rank(t["tier"]) <= ceiling]


@dataclass
class StateValue:
    """A named datum captured from a step (FR-010)."""

    name: str
    value: Any
    scope: str = "run"  # "run" (in-memory) | "persisted"
    sensitive: bool = False


@dataclass
class StepResult:
    name: str
    status: str  # "passed" | "failed" | "blocked"
    message: str = ""
    duration_s: float = 0.0


@dataclass
class TestResult:
    id: str
    tier: str
    status: str  # "passed" | "failed" | "blocked"
    steps: list[StepResult] = field(default_factory=list)
    duration_s: float = 0.0


@dataclass
class RunReport:
    app: str
    tier: str
    results: list[TestResult] = field(default_factory=list)

    @property
    def selected(self) -> int:
        return len(self.results)

    @property
    def verdict(self) -> str:
        if self.selected == 0:
            return "EMPTY"
        return "FAIL" if any(r.status != "passed" for r in self.results) else "PASS"

    @property
    def exit_code(self) -> int:
        # 0 pass, 1 fail/blocked, 2 empty-selection (FR-007/FR-008)
        return {"PASS": 0, "FAIL": 1, "EMPTY": 2}[self.verdict]
