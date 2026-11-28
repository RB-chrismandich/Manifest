"""Evaluate findings without allowing a baseline to hide new debt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .debt_baseline import load_baseline


def _finding_ids(findings: list[dict[str, Any]]) -> set[str]:
    if not isinstance(findings, list):
        raise ValueError("debt findings must be a list")
    ids = [
        finding.get("id") if isinstance(finding, dict) else None for finding in findings
    ]
    if not all(isinstance(item, str) and item for item in ids) or len(ids) != len(
        set(ids)
    ):
        raise ValueError("debt findings are malformed")
    return set(ids)


def evaluate_findings(
    findings: list[dict[str, Any]], baseline_path: Path
) -> dict[str, Any]:
    known = load_baseline(baseline_path)
    new = sorted(_finding_ids(findings) - known)
    return {"status": "FAIL" if new else "PASS", "new_findings": new}
