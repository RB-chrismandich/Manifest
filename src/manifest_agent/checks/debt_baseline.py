"""Read explicit baseline records."""

from __future__ import annotations

import json
from pathlib import Path


def load_baseline(path: Path) -> frozenset[str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"debt baseline is unavailable or invalid: {error}") from error
    findings = document.get("findings") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != 1
        or not isinstance(findings, list)
    ):
        raise ValueError("unsupported debt baseline")
    ids = [item.get("id") if isinstance(item, dict) else None for item in findings]
    if not all(isinstance(item, str) and item for item in ids) or len(ids) != len(
        set(ids)
    ):
        raise ValueError("debt baseline has malformed findings")
    return frozenset(ids)
