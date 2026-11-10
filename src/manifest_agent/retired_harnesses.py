"""Receipt handling for harnesses whose Manifest support was removed.

Receipts written before a removal may still name the retired harness. Such a
record is pruned when the receipt is read, so it never reaches validation,
adapters, or identity checks, and it disappears on the next receipt write.
Every lifecycle report notes the pruning so it is never silent. Only names in
RETIRED_HARNESSES get this treatment: any other unknown harness name is still
rejected by receipt validation.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol, TypeVar

from manifest_agent.models import InstallationReceipt

RETIRED_HARNESSES = frozenset({"gemini"})
_REMOVAL_NOTICE = {"gemini": "Gemini CLI support was removed"}


class _HasReceiptPath(Protocol):
    receipt_path: Path


_Report = TypeVar("_Report")


def without_retired_harnesses(receipt: InstallationReceipt) -> InstallationReceipt:
    """Return the receipt with every retired harness record dropped."""
    if not RETIRED_HARNESSES.intersection(receipt.harnesses):
        return receipt
    return replace(
        receipt,
        harnesses={
            name: harness
            for name, harness in receipt.harnesses.items()
            if name not in RETIRED_HARNESSES
        },
    )


def retired_receipt_harnesses(path: Path) -> tuple[str, ...]:
    """Name the retired harness records the on-disk receipt still carries.

    A read-only reporting probe: a missing or malformed receipt yields no names
    because read_receipt is the authority that reports those errors.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    harnesses = document.get("harnesses") if isinstance(document, dict) else None
    if not isinstance(harnesses, dict):
        return ()
    return tuple(sorted(RETIRED_HARNESSES.intersection(harnesses)))


def retired_harness_notes(
    before: tuple[str, ...], after: tuple[str, ...]
) -> tuple[str, ...]:
    """Describe each retired record seen before an operation and its outcome."""
    notes = []
    for name in before:
        outcome = (
            "ignored; it is pruned on the next receipt write"
            if name in after
            else "pruned from the receipt"
        )
        notes.append(
            f"{name}: retired harness record {outcome} ({_REMOVAL_NOTICE[name]})"
        )
    return tuple(notes)


def notes_retired_harnesses(
    operation: Callable[..., _Report],
) -> Callable[..., _Report]:
    """Append retired-harness notes to a lifecycle method's report."""

    @functools.wraps(operation)
    def run(service: _HasReceiptPath, *args: Any, **kwargs: Any) -> _Report:
        before = retired_receipt_harnesses(service.receipt_path)
        result = operation(service, *args, **kwargs)
        if not before:
            return result
        after = retired_receipt_harnesses(service.receipt_path)
        notes = retired_harness_notes(before, after)
        return replace(result, notes=(*result.notes, *notes))  # type: ignore[type-var]

    return run


__all__ = [
    "RETIRED_HARNESSES",
    "notes_retired_harnesses",
    "retired_harness_notes",
    "retired_receipt_harnesses",
    "without_retired_harnesses",
]
