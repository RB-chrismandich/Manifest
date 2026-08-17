"""Shared Codex adapter constants and boundary helpers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from manifest_agent.models import CommandResult, HarnessResult, ResultState
from manifest_agent.process import redact_text

MARKETPLACE = "manifest"
ADAPTER_VERSION = "1"
COMMIT = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
ADHD_PLUGIN = "manifest-i-have-adhd"


class CodexCommandExecutor(Protocol):
    """Execute native commands through the adapter's redacting boundary."""

    def _execute(
        self, argv: Sequence[str]
    ) -> tuple[CommandResult | None, HarnessResult | None]: ...


def blocked(error: str) -> HarnessResult:
    """Return a consistently redacted blocking Codex result."""
    return HarnessResult(
        "codex", ResultState.BLOCKED, (), {}, errors=(redact_text(error),)
    )


def resolved_path(value: str) -> str:
    """Normalize a path identity without requiring the target to exist."""
    return str(Path(value).expanduser().resolve(strict=False))
