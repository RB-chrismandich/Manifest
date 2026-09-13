"""Shared immutable data for toolchain provisioning."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

Fetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class ProvisionOutcome:
    """A single bundle's provision result and optional observed digest."""

    bundle: str
    status: str
    reason: str = ""
    digest: str | None = None


@dataclass(frozen=True)
class ProvisionContext:
    """The immutable arguments shared by every provisioning operation."""

    store: Path
    lock: Mapping
    platform: str
    fetcher: Fetcher = None  # type: ignore[assignment]
    repo_root: Path = field(default_factory=Path.cwd)
    env: Mapping[str, str] = field(default_factory=dict)
