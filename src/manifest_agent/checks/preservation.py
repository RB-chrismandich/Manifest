"""Validate and evaluate supported check-preservation invariants."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import CheckResult, CheckSpec
from .status import executed_status

_SUPPORTED = frozenset({"shared-checks.exit-status"})


def load_invariants(path: Path) -> tuple[str, ...]:
    try:
        document: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"preservation is unavailable or invalid: {error}") from error
    invariants = document.get("invariants") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != 1
        or not isinstance(invariants, list)
    ):
        raise ValueError("unsupported preservation policy")
    ids = [item.get("id") if isinstance(item, dict) else None for item in invariants]
    if not all(isinstance(item, str) and item in _SUPPORTED for item in ids) or len(
        ids
    ) != len(set(ids)):
        raise ValueError("preservation has malformed or unsupported invariants")
    if any(
        not isinstance(item.get("description"), str) or not item["description"]
        for item in invariants
    ):
        raise ValueError("preservation has malformed invariants")
    return tuple(ids)


def evaluate_invariants(
    invariants: tuple[str, ...],
    checks: tuple[CheckSpec, ...],
    results: list[CheckResult],
) -> list[str]:
    by_id = {check.id: check for check in checks}
    errors: list[str] = []
    if "shared-checks.exit-status" in invariants:
        for result in results:
            check = by_id.get(result.id)
            if check is None:
                errors.append(f"preservation result has unknown check: {result.id}")
            elif (
                result.returncode is not None
                and result.status
                != executed_status(result.returncode, check.honors_status_contract)
            ) or (result.returncode is None and result.status != "BLOCKED"):
                errors.append(f"preservation exit-status violated for {result.id}")
    return errors
