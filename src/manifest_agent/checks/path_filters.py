"""Deterministic candidate-relative input selection."""

from __future__ import annotations

from .models import Candidate, CheckSpec


def filter_inputs(candidate: Candidate, check: CheckSpec) -> tuple[str, ...]:
    selected: list[str] = []
    for item in check.inputs:
        path = candidate.root / item
        if path.is_file():
            selected.append(item)
        elif path.is_dir():
            selected.extend(
                p.relative_to(candidate.root).as_posix()
                for p in sorted(path.rglob("*"))
                if p.is_file()
            )
    return tuple(selected)
