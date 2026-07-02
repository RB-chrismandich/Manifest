"""Aggregation helpers for the demo dashboard."""

from src.models import Score


def mean_score(scores: list[Score]) -> float | None:
    """Mean of score values; None for an empty list (caller must handle)."""
    if not scores:
        return None
    return sum(s.value for s in scores) / len(scores)


def top_n(scores: list[Score], n: int) -> list[Score]:
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    return sorted(scores, key=lambda s: s.value, reverse=True)[:n]
