"""Per-run pipeline state machine.

The decision engine is stateless (FR-006); the state it is forbidden to hold —
attempt counts, the selected issue, the current phase, pause status — lives here
in a compact per-run JSON file so the pipeline is resumable (FR-027, FR-035).
This module also holds the deterministic gating helpers: no-automation exclusion
and dependency-cycle detection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

PHASE_ORDER = [1, 2, 3, 4, 5, 6]
BLOCK_LABEL = "no-automation"


@dataclass
class PipelineState:
    run_id: str
    selected_issue: str | None = None
    current_phase: int = 1
    attempt_counts: dict[str, int] = field(default_factory=dict)
    last_status: str | None = None
    paused: bool = False

    # -- persistence ------------------------------------------------------- #
    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "PipelineState":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))

    # -- attempt cap (FR-027) ---------------------------------------------- #
    def record_attempt(self, phase: int) -> int:
        key = str(phase)
        self.attempt_counts[key] = self.attempt_counts.get(key, 0) + 1
        return self.attempt_counts[key]

    def should_escalate(self, phase: int, cap: int = 2) -> bool:
        """True once a phase has failed `cap` times (FR-027)."""
        return self.attempt_counts.get(str(phase), 0) >= cap

    # -- resource pause (FR-035): never increments attempts ---------------- #
    def pause_for_resource(self) -> None:
        self.paused = True
        self.last_status = "blocked"

    def resume(self) -> None:
        self.paused = False

    def advance(self) -> int | None:
        """Move to the next phase; returns the new phase or None if complete."""
        idx = PHASE_ORDER.index(self.current_phase)
        if idx + 1 < len(PHASE_ORDER):
            self.current_phase = PHASE_ORDER[idx + 1]
            return self.current_phase
        return None


# --------------------------------------------------------------------------- #
# no-automation kill-switch (FR-037)
# --------------------------------------------------------------------------- #
def is_blocked(issue: dict[str, Any], block_label: str = BLOCK_LABEL) -> bool:
    """True if the issue carries the kill-switch label."""
    return block_label in issue.get("labels", [])


def filter_automatable(issues: list[dict[str, Any]], block_label: str = BLOCK_LABEL) -> list[dict[str, Any]]:
    """Exclude issues bearing the kill-switch label from the candidate set."""
    return [i for i in issues if not is_blocked(i, block_label)]


def block_check(issue: dict[str, Any], block_label: str = BLOCK_LABEL) -> str | None:
    """Return a halt reason if the issue must not advance, else None (FR-037).

    Re-evaluated before EVERY phase advance so that applying the label
    mid-pipeline halts the active issue before implementation or PR-open.
    """
    if is_blocked(issue, block_label):
        return f"issue held by '{block_label}' label; halting before next phase advance"
    return None


# --------------------------------------------------------------------------- #
# Dependency-cycle detection (edge case: circular dependencies)
# --------------------------------------------------------------------------- #
def detect_cycle(issues: list[dict[str, Any]]) -> list[str] | None:
    """Return a cycle (list of issue ids) if the depends_on graph has one, else None."""
    graph = {i["id"]: list(i.get("depends_on", [])) for i in issues}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for nxt in graph.get(node, []):
            if nxt not in color:          # dangling dep — ignore for cycle purposes
                continue
            if color[nxt] == GRAY:
                return stack[stack.index(nxt):] + [nxt]
            if color[nxt] == WHITE:
                found = dfs(nxt)
                if found:
                    return found
        color[node] = BLACK
        stack.pop()
        return None

    for n in graph:
        if color[n] == WHITE:
            found = dfs(n)
            if found:
                return found
    return None
