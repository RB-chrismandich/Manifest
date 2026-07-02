"""Legacy weekly report generator for the demo dashboard."""

from src.models import Score


def weekly_report(scores: list[Score]) -> str:
    total = sum(s.value for s in scores)
    lines = [f"{s.game_id}: {s.value:.1f}" for s in scores]
    lines.append(f"TOTAL: {total:.1f}")
    return "\n".join(lines)
