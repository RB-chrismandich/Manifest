"""Tell contract-declared degradation apart from a real capability gap."""

from __future__ import annotations

from collections import Counter

from manifest_agent.models import HarnessResult, ResultState

_NON_CONVERGENT_STATUSES = frozenset(
    {
        "failed",
        "disabled",
        "conflicting",
        "unknown-transport",
        "observation-unavailable",
    }
)


def has_undeclared_degradation(result: HarnessResult) -> bool:
    """Return whether a DEGRADED result contains any non-contract degradation."""
    if result.state is not ResultState.DEGRADED:
        return False
    declared = Counter(result.declared_degradations)
    if not declared or Counter(result.errors) != declared:
        return True
    return any(
        status in _NON_CONVERGENT_STATUSES for status in result.capabilities.values()
    )
